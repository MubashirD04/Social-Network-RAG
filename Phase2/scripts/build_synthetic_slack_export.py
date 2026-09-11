"""
Builds a synthetic Slack export .zip for exercising `scripts/eval_conversation_linker.py`
without needing a real customer export.

Matches Slack's real export shape (confirmed against Slack's own "How to read
Slack data exports" help article and the message-object fields Slack's Web
API documents): a `users.json` at the root, a `channels.json`, and one JSON
file per channel *per day* nested under a per-channel folder
(`<channel>/YYYY-MM-DD.json`) — not one flat file per channel. `ts` is a
unix-timestamp-with-microseconds string, `thread_ts` on a reply points at the
thread root's `ts` (equal to a message's own `ts` just marks it as a thread
root), and `reactions` is a list of `{name, users, count}`.

The message set is hand-written, not random, so it exercises specific things:
- Two real Slack threads whose replies land on a *different calendar day*
  than their root (`flaky-pipeline` and `schema-migration` below) — this is
  exactly the case ChatParser.parse_slack used to get wrong by deriving the
  channel from the per-file stem instead of the per-channel folder.
- Plenty of topically-continuous messages posted with no `thread_ts` at all
  (the Figma sidebar chat, the dark-mode contrast chat, the coffee machine
  chat, the taco place chat) — this is the actual gap the inferred-link
  layer exists to fill, and the only way to construct a meaningful
  candidate set for it out of a real Slack export.
- Unrelated interleaved chatter (standup reminders, a QA-environment status
  check) so precision isn't measured against a trivially separable dataset.
- One `channel_join` subtype message, to confirm the parser's subtype skip
  still works inside the new per-channel grouping.

Usage:
    python Phase2/scripts/build_synthetic_slack_export.py
    python Phase2/scripts/build_synthetic_slack_export.py --output path/to/export.zip
"""
import argparse
import json
import sys
import uuid
import zipfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

USERS = [
    {
        "id": "U01ALICE", "team_id": "T01DEMO", "name": "achen", "deleted": False,
        "real_name": "Alice Chen", "tz": "America/Los_Angeles",
        "profile": {"real_name": "Alice Chen", "display_name": "achen", "email": "alice@example.com", "team": "T01DEMO"},
        "is_bot": False, "is_admin": True, "updated": 1704000000,
    },
    {
        "id": "U02BOB", "team_id": "T01DEMO", "name": "bmartinez", "deleted": False,
        "real_name": "Bob Martinez", "tz": "America/New_York",
        "profile": {"real_name": "Bob Martinez", "display_name": "bmartinez", "email": "bob@example.com", "team": "T01DEMO"},
        "is_bot": False, "is_admin": False, "updated": 1704000000,
    },
    {
        "id": "U03CHARLIE", "team_id": "T01DEMO", "name": "cokafor", "deleted": False,
        "real_name": "Charlie Okafor", "tz": "Europe/London",
        "profile": {"real_name": "Charlie Okafor", "display_name": "cokafor", "email": "charlie@example.com", "team": "T01DEMO"},
        "is_bot": False, "is_admin": False, "updated": 1704000000,
    },
    {
        "id": "U04DIANA", "team_id": "T01DEMO", "name": "dkowalski", "deleted": False,
        "real_name": "Diana Kowalski", "tz": "America/Chicago",
        "profile": {"real_name": "Diana Kowalski", "display_name": "dkowalski", "email": "diana@example.com", "team": "T01DEMO"},
        "is_bot": False, "is_admin": True, "updated": 1704000000,
    },
    {
        "id": "U05EVE", "team_id": "T01DEMO", "name": "etanaka", "deleted": False,
        "real_name": "Eve Tanaka", "tz": "Asia/Tokyo",
        "profile": {"real_name": "Eve Tanaka", "display_name": "etanaka", "email": "eve@example.com", "team": "T01DEMO"},
        "is_bot": False, "is_admin": False, "updated": 1704000000,
    },
    {
        "id": "U06FRANK", "team_id": "T01DEMO", "name": "fsilva", "deleted": False,
        "real_name": "Frank Silva", "tz": "America/Sao_Paulo",
        "profile": {"real_name": "Frank Silva", "display_name": "fsilva", "email": "frank@example.com", "team": "T01DEMO"},
        "is_bot": False, "is_admin": False, "updated": 1704000000,
    },
    {
        "id": "U07GRACE", "team_id": "T01DEMO", "name": "gnowak", "deleted": False,
        "real_name": "Grace Nowak", "tz": "America/Los_Angeles",
        "profile": {"real_name": "Grace Nowak", "display_name": "gnowak", "email": "grace@example.com", "team": "T01DEMO"},
        "is_bot": False, "is_admin": False, "updated": 1704000000,
    },
]

CHANNEL_META = {
    "engineering": {"id": "C01ENG", "purpose": "Engineering team discussion"},
    "watercooler": {"id": "C02WATER", "purpose": "Off-topic chat"},
}

# Each entry: (key, day "YYYY-MM-DD", "HH:MM", user_id, text, thread_of=<key or None>, reactions=[(emoji, [user_ids])])
ENGINEERING_MESSAGES = [
    ("flaky-pipeline-root", "2024-01-15", "09:00", "U01ALICE", "Morning team, quick heads up — the staging deploy pipeline is being flaky again", None, None),
    ("flaky-pipeline-r1", "2024-01-15", "09:02", "U02BOB", "ah yeah I saw that too, looks like the docker build step is timing out", "flaky-pipeline-root", None),
    ("flaky-pipeline-r2", "2024-01-15", "09:03", "U02BOB", "going to dig into it now", "flaky-pipeline-root", None),
    ("figma-root", "2024-01-15", "09:10", "U03CHARLIE", "on an unrelated note, has anyone looked at the new figma mockups for the dashboard?", None, None),
    ("figma-r1", "2024-01-15", "09:12", "U05EVE", "yes! I posted them yesterday, let me know what you think of the sidebar layout", None, None),
    ("figma-r2", "2024-01-15", "09:14", "U03CHARLIE", "the sidebar looks great, though I think the nav icons could be bigger", None, None),
    ("standup-reminder-1", "2024-01-15", "09:30", "U04DIANA", "standup in 30 — same link as always", None, None),
    ("flaky-pipeline-r3", "2024-01-15", "09:45", "U01ALICE", "found it — turns out it's a flaky npm registry mirror, switching us to the official one", "flaky-pipeline-root", None),
    ("flaky-pipeline-r4", "2024-01-15", "09:46", "U02BOB", "nice catch, that should fix it", "flaky-pipeline-root", [("thumbsup", ["U01ALICE", "U03CHARLIE"])]),
    ("qa-down-root", "2024-01-15", "10:15", "U06FRANK", "quick question — is the QA environment supposed to be down right now?", None, None),
    ("qa-down-r1", "2024-01-15", "10:17", "U01ALICE", "yeah taking it down briefly for the registry mirror fix, should be back in 10", None, None),
    ("qa-down-r2", "2024-01-15", "10:28", "U06FRANK", "confirmed it's back up, thanks", None, None),
    ("_join_grace", "2024-01-15", "11:00", "U07GRACE", "<@U07GRACE> has joined the channel", None, None),

    ("standup-moved", "2024-01-16", "09:00", "U04DIANA", "reminder: sprint planning moved to 2pm today", None, None),
    ("standup-moved-ack", "2024-01-16", "09:05", "U03CHARLIE", "noted, thanks", None, None),
    ("schema-migration-root", "2024-01-16", "10:00", "U02BOB", "the schema migration for the payments table is ready for review", None, None),
    ("schema-migration-r1", "2024-01-16", "10:05", "U01ALICE", "looking now", "schema-migration-root", None),
    ("darkmode-root", "2024-01-16", "11:00", "U05EVE", "does anyone have strong opinions on dark mode contrast ratios?", None, None),
    ("darkmode-r1", "2024-01-16", "11:02", "U03CHARLIE", "I'd lean towards WCAG AA at minimum", None, None),
    ("darkmode-r2", "2024-01-16", "11:03", "U05EVE", "agreed, I'll update the color tokens to hit that", None, None),
    ("schema-migration-r2", "2024-01-16", "14:30", "U01ALICE", "looks solid, just left one comment about the index", "schema-migration-root", None),

    # These two land the *next day*, threaded to schema-migration-root
    # (2024-01-16) — the deliberate cross-day-file thread case.
    ("schema-migration-r3", "2024-01-17", "09:00", "U02BOB", "addressed the index comment, should be good to merge now", "schema-migration-root", None),
    ("schema-migration-r4", "2024-01-17", "09:05", "U01ALICE", "merged, thanks for the quick turnaround", "schema-migration-root", [("tada", ["U02BOB", "U04DIANA"])]),
    ("regression-root", "2024-01-17", "09:30", "U06FRANK", "running the regression suite against staging now", None, None),
    ("regression-r1", "2024-01-17", "10:00", "U06FRANK", "all green, no regressions from the payments migration", None, None),
    ("regression-r2", "2024-01-17", "10:05", "U04DIANA", "awesome, nice work everyone", None, None),
    ("darkmode-r3", "2024-01-17", "13:00", "U03CHARLIE", "pushed the updated dark mode tokens, should be live on staging", None, None),
    ("darkmode-r4", "2024-01-17", "13:05", "U05EVE", "looks great, contrast checker is happy", None, None),
]

WATERCOOLER_MESSAGES = [
    ("coffee-root", "2024-01-15", "12:00", "U04DIANA", "is the coffee machine on 3 broken again?", None, None),
    ("coffee-r1", "2024-01-15", "12:03", "U06FRANK", "yeah someone needs to fix that thing, it's been leaking", None, None),
    ("coffee-r2", "2024-01-15", "12:05", "U04DIANA", "ugh, I already emailed facilities about it twice", None, None),
    ("taco-root", "2024-01-15", "12:30", "U02BOB", "totally unrelated but has anyone tried the new taco place on 5th?", None, None),
    ("taco-r1", "2024-01-15", "12:32", "U05EVE", "yes! got it yesterday, the al pastor is really good", "taco-root", None),
    ("taco-r2", "2024-01-15", "12:34", "U02BOB", "nice, adding it to the list", "taco-root", None),
    ("coffee-r3", "2024-01-15", "15:00", "U03CHARLIE", "facilities said they'll look at the coffee machine tomorrow morning", None, None),

    ("coffee-update-root", "2024-01-16", "09:15", "U04DIANA", "coffee machine update: still broken, opened a ticket", None, None),
    ("coffee-update-r1", "2024-01-16", "09:17", "U06FRANK", "at this point I'm just bringing my own french press", "coffee-update-root", None),
    ("anniversary-root", "2024-01-16", "16:00", "U01ALICE", "reminder there's cake in the kitchen for Eve's work anniversary!", None, None),
    ("anniversary-r1", "2024-01-16", "16:02", "U05EVE", "aw thank you everyone :)", None, [("heart", ["U01ALICE", "U03CHARLIE", "U04DIANA"])]),
    ("anniversary-r2", "2024-01-16", "16:05", "U03CHARLIE", "congrats Eve! time flies", None, None),
]

CHANNELS = {
    "engineering": ENGINEERING_MESSAGES,
    "watercooler": WATERCOOLER_MESSAGES,
}


def _to_ts(day: str, time_str: str) -> str:
    dt = datetime.strptime(f"{day} {time_str}", "%Y-%m-%d %H:%M")
    # Slack ts is seconds.microseconds — the trailing digits aren't a real
    # microsecond reading, just Slack's own de-duplication suffix, but the
    # shape (6 digits) is what a real export looks like.
    return f"{int(dt.timestamp())}.000100"


def _build_channel_days(messages):
    """Returns {day: [message_dict, ...]}, resolving thread_of references to
    the referenced message's ts and assigning a realistic client_msg_id."""
    ts_by_key = {}
    for key, day, time_str, *_ in messages:
        ts_by_key[key] = _to_ts(day, time_str)

    days = {}
    for key, day, time_str, user, text, thread_of, reactions in messages:
        msg = {
            "client_msg_id": str(uuid.uuid5(uuid.NAMESPACE_URL, key)),
            "type": "message",
            "user": user,
            "text": text,
            "ts": ts_by_key[key],
            "team": "T01DEMO",
        }
        if key.startswith("_join_"):
            msg["subtype"] = "channel_join"
        if thread_of:
            msg["thread_ts"] = ts_by_key[thread_of]
        if reactions:
            msg["reactions"] = [
                {"name": emoji, "users": user_ids, "count": len(user_ids)}
                for emoji, user_ids in reactions
            ]
        days.setdefault(day, []).append(msg)

    for day_msgs in days.values():
        day_msgs.sort(key=lambda m: float(m["ts"]))

    return days


def build_export(output_path: Path) -> dict:
    ground_truth_pairs = 0

    with zipfile.ZipFile(output_path, "w") as z:
        z.writestr("users.json", json.dumps(USERS, indent=2))

        # Grace only ever appears in engineering (her channel_join event), so
        # she's left out of watercooler's membership list.
        all_user_ids = [u["id"] for u in USERS]
        channels_json = [
            {
                "id": meta["id"],
                "name": channel_name,
                "created": int(datetime(2024, 1, 1).timestamp()),
                "creator": "U01ALICE",
                "is_archived": False,
                "members": all_user_ids if channel_name == "engineering" else [uid for uid in all_user_ids if uid != "U07GRACE"],
                "topic": {"value": "", "creator": "", "last_set": 0},
                "purpose": {"value": meta["purpose"], "creator": "U01ALICE", "last_set": int(datetime(2024, 1, 1).timestamp())},
            }
            for channel_name, meta in CHANNEL_META.items()
        ]
        z.writestr("channels.json", json.dumps(channels_json, indent=2))

        for channel_name, messages in CHANNELS.items():
            days = _build_channel_days(messages)
            for day, day_msgs in days.items():
                z.writestr(f"{channel_name}/{day}.json", json.dumps(day_msgs, indent=2))
            ground_truth_pairs += sum(1 for m in messages if m[5] is not None)

    return {
        "channels": list(CHANNELS.keys()),
        "messages": sum(len(m) for m in CHANNELS.values()),
        "ground_truth_thread_pairs": ground_truth_pairs,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--output", type=Path,
        default=Path(__file__).resolve().parent.parent.parent / "output" / "synthetic_slack_export.zip",
        help="Where to write the .zip (default: output/synthetic_slack_export.zip)"
    )
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)

    summary = build_export(args.output)
    print(f"Wrote synthetic Slack export to {args.output}")
    print(f"  Channels: {', '.join(summary['channels'])}")
    print(f"  Messages: {summary['messages']}")
    print(f"  Ground-truth thread_ts pairs: {summary['ground_truth_thread_pairs']}")
    print("  (includes 2 threads whose replies land on a later day than their root,")
    print("   to exercise the cross-day thread_ts resolution fix)")


if __name__ == "__main__":
    main()
