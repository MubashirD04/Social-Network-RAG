# Getting Your Chat Data

The `/analyse` endpoint (and the web UI's upload zone) accepts a single file: WhatsApp `.txt`, Telegram `.json`, or Slack `.zip`. This guide covers how to export each one so `ChatParser` (`Phase2/src/chat_parser.py`) can read it.

## WhatsApp (.txt)

1. Open the individual or group chat in the WhatsApp app.
2. **Android**: tap the ⋮ menu → **More** → **Export chat**.
   **iPhone**: tap the contact/group name at the top → scroll down → **Export Chat**.
3. Choose **Without Media** — media isn't used by the analysis and makes the export much smaller/faster to send.
4. Send the resulting `.txt` file to yourself (email, Drive, AirDrop, etc.) and save it locally.

Notes:
- Both 12-hour (`AM`/`PM`) and 24-hour timestamp formats are supported.
- WhatsApp exports carry no reply metadata. The parser infers replies by treating a message with no `@mention` as a reply to the immediately preceding message from a different sender, if it follows within 5 minutes.
- Lines containing `<Media omitted>`/`- omitted` are dropped rather than treated as message content.

## Telegram (.json)

JSON export is only available from **Telegram Desktop** (not the mobile apps).

1. Open the chat in Telegram Desktop.
2. Click the ⋮ menu in the top-right → **Export chat history**.
3. In the export settings, deselect all media types you don't need (photos, videos, etc. are ignored by this tool) and make sure the format is set to **Machine-readable JSON** (not HTML).
4. Click **Export**. Telegram creates a `ChatExport_<date>` folder — the file to upload is `result.json` inside it.

Notes:
- The parser reads the top-level `messages` array (or a bare list), each entry's `from`, `text`, `date` (ISO 8601), and `reply_to_message_id`.
- Text with inline entities (bold, links, mentions) is flattened to plain text.

## Slack (.zip)

Slack's export tool requires **Workspace Owner/Admin** access.

1. From a browser, go to your workspace's **Settings & administration** → **Workspace settings**.
2. Under **Import/Export Data**, open the **Export** tab.
3. Pick a date range and click **Start Export**. Slack emails you when the archive is ready (can take a few minutes for large workspaces).
4. Download the `.zip` file directly — don't unzip it, upload it as-is.

Notes:
- On the free/standard export tool, only **public channels** are included; private channels and DMs require Slack's Discovery API (Enterprise) or a compliance export.
- The zip should contain `users.json` (for name lookup) plus one JSON file per channel per day (e.g. `general/2024-01-01.json`). The parser walks every `.json` file in the archive except `users.json`, `channels.json`, and `integration_logs.json`, so multi-day/multi-channel exports work without any extra steps.
- `thread_ts` is used to reconstruct reply threads; reactions are mapped from user IDs to display names via `users.json`.

## Uploading

Once you have the file, either:
- Drag it into the upload zone in the web UI (`just frontend`), or
- `POST` it directly:
  ```bash
  curl -X POST http://localhost:8000/analyse -F "file=@/path/to/export.zip"
  ```
