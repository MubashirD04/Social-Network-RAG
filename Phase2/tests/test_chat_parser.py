import pytest
import json
import zipfile
import os
from pathlib import Path
from datetime import datetime

from src.chat_parser import ChatParser

@pytest.fixture
def temp_workspace(tmp_path):
    return tmp_path

def test_parse_whatsapp(temp_workspace):
    file_path = temp_workspace / "whatsapp_chat.txt"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("01/01/2023, 10:00 - Alice: Hey everyone!\n")
        f.write("01/01/2023, 10:01 - Bob: Hi Alice.\n")
        f.write("Some multiline\n")
        f.write("text here.\n")
        f.write("01/01/2023, 10:05 - Charlie: How are you both?\n")

    messages = ChatParser.parse_file(file_path)
    
    assert len(messages) == 3
    assert messages[0].sender == "Alice"
    assert messages[0].content == "Hey everyone!"
    
    assert messages[1].sender == "Bob"
    assert "multiline" in messages[1].content

    assert messages[2].sender == "Charlie"


def test_parse_whatsapp_infers_implicit_replies(temp_workspace):
    """
    WhatsApp .txt exports carry no reply/thread metadata, so without a
    fallback the social graph built from them has no way to infer who's
    talking to whom (see IMPLICIT_REPLY_WINDOW in chat_parser.py). A message
    from a different sender than the previous one, arriving soon after and
    without an @mention, is treated as an implicit reply to it.
    """
    file_path = temp_workspace / "whatsapp_chat.txt"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("01/01/2023, 10:00 - Alice: Hey everyone!\n")
        f.write("01/01/2023, 10:01 - Bob: Hi Alice.\n")           # implicit reply to Alice
        f.write("01/01/2023, 10:01 - Bob: Also, how's it going?\n")  # same sender as previous -> no inferred reply
        f.write("01/01/2023, 10:02 - Charlie: @Bob good, thanks!\n")  # explicit mention -> no inferred reply_to
        f.write("01/01/2023, 11:00 - Diana: Morning all!\n")      # outside the window -> no inferred reply

    messages = ChatParser.parse_file(file_path)
    by_content = {m.content: m for m in messages}

    hi_alice = by_content["Hi Alice."]
    assert hi_alice.reply_to == messages[0].id

    also_how = by_content["Also, how's it going?"]
    assert also_how.reply_to is None

    mention_msg = by_content["@Bob good, thanks!"]
    assert mention_msg.reply_to is None

    morning = by_content["Morning all!"]
    assert morning.reply_to is None

def test_parse_telegram(temp_workspace):
    file_path = temp_workspace / "telegram_export.json"
    data = {
        "messages": [
            {
                "id": 1,
                "type": "message",
                "date": "2023-01-01T10:00:00",
                "from": "Alice",
                "text": "Hello Telegram"
            },
            {
                "id": 2,
                "type": "message",
                "date": "2023-01-01T10:05:00",
                "from": "Bob",
                "text": "Replying to Alice",
                "reply_to_message_id": 1
            }
        ]
    }
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f)
        
    messages = ChatParser.parse_file(file_path)
    
    assert len(messages) == 2
    assert messages[0].id == "1"
    assert messages[0].sender == "Alice"
    
    assert messages[1].reply_to == "1"
    assert messages[1].content == "Replying to Alice"

def test_parse_slack(temp_workspace):
    file_path = temp_workspace / "slack_export.zip"
    
    users = [
        {"id": "U1", "profile": {"real_name": "Alice"}},
        {"id": "U2", "name": "Bob"}
    ]
    
    channel_msgs = [
        {
            "type": "message",
            "user": "U1",
            "text": "Slack message",
            "ts": "1704067140.0",
            "client_msg_id": "msg1"
        },
        {
            "type": "message",
            "user": "U2",
            "text": "With reaction",
            "ts": "1704067150.0",
            "client_msg_id": "msg2",
            "reactions": [
                {"name": "thumbsup", "users": ["U1"]}
            ]
        },
        {
            # Slack addresses a reply's parent by the parent's `ts`
            # ("1704067140.0"), never by the parent's client_msg_id
            # ("msg1"). reply_to must resolve to "msg1" here, not be left
            # as the raw timestamp string — that's the bug this regression
            # test guards: a reply stored as a timestamp never matches any
            # node id downstream in the graph builder, so the REPLIED_TO
            # edge silently never gets drawn.
            "type": "message",
            "user": "U2",
            "text": "Replying to Alice's message",
            "ts": "1704067160.0",
            "thread_ts": "1704067140.0",
            "client_msg_id": "msg3"
        }
    ]

    with zipfile.ZipFile(file_path, 'w') as z:
        z.writestr('users.json', json.dumps(users))
        z.writestr('general/updates.json', json.dumps(channel_msgs))

    messages = ChatParser.parse_file(file_path)

    assert len(messages) == 3
    assert messages[0].sender == "Alice"
    assert messages[0].id == "msg1"

    assert messages[1].sender == "Bob"
    assert "Alice" in messages[1].reactions
    assert messages[1].content == "With reaction"
    assert messages[1].reply_to is None

    assert messages[2].reply_to == "msg1"

def test_parse_slack_resolves_channel_and_threads_across_multiple_daily_files(temp_workspace):
    """
    Regression test: a real Slack export nests one JSON file per day under a
    per-channel folder (e.g. "engineering/2024-01-15.json"). Deriving the
    channel from the per-file stem instead of the folder used to read each
    day as its own separate "channel" — fragmenting a multi-day channel and
    breaking thread_ts resolution for any thread whose reply landed on a
    different calendar day than its root, since the ts -> id lookup was
    rebuilt fresh per file instead of spanning the whole channel.
    """
    file_path = temp_workspace / "slack_export.zip"

    users = [{"id": "U1", "profile": {"real_name": "Alice"}}, {"id": "U2", "name": "Bob"}]

    day1_msgs = [
        {
            "type": "message", "user": "U1", "text": "Kicking off the migration today",
            "ts": "1704067140.0", "client_msg_id": "root1"
        },
    ]
    day2_msgs = [
        {
            # Reply lands the next day, threaded to a root from day1's file.
            "type": "message", "user": "U2", "text": "Sounds good, I'll start on the schema",
            "ts": "1704153600.0", "thread_ts": "1704067140.0", "client_msg_id": "reply1"
        },
    ]

    with zipfile.ZipFile(file_path, 'w') as z:
        z.writestr('users.json', json.dumps(users))
        z.writestr('engineering/2024-01-01.json', json.dumps(day1_msgs))
        z.writestr('engineering/2024-01-02.json', json.dumps(day2_msgs))

    messages = ChatParser.parse_file(file_path)

    assert len(messages) == 2
    assert all(m.channel == "engineering" for m in messages)

    reply = next(m for m in messages if m.id == "reply1")
    assert reply.reply_to == "root1"
