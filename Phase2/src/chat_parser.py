import json
import re
import zipfile
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Union

from src.social_models import Message

class ChatParser:
    """
    Parses various chat export formats into the standard List[Message] schema.
    Supported formats: WhatsApp (.txt), Telegram (.json), Slack (.zip).
    """

    @classmethod
    def parse_file(cls, filepath: Union[str, Path]) -> List[Message]:
        filepath = Path(filepath)
        if not filepath.exists():
            raise FileNotFoundError(f"File not found: {filepath}")

        ext = filepath.suffix.lower()

        if ext == ".txt":
            return cls.parse_whatsapp(filepath)
        elif ext == ".json":
            # Assuming Telegram JSON for now if it's JSON
            # Discord was excluded for this iteration
            return cls.parse_telegram(filepath)
        elif ext == ".zip":
            return cls.parse_slack(filepath)
        else:
            raise ValueError(f"Unsupported file format: {ext}")

    @classmethod
    def parse_whatsapp(cls, filepath: Path) -> List[Message]:
        """
        Parses WhatsApp .txt export files.
        Handles both 12hr and 24hr date formats.
        """
        messages = []
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        # Common format: "DD/MM/YYYY, HH:MM - Sender: Message" or "[DD/MM/YYYY, HH:MM:SS] Sender: Message"
        pattern = re.compile(
            r'^(?:\[)?(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4}[,]? \d{1,2}:\d{2}(?::\d{2})?(?: [AP]M)?)(?:\]| \-) ([^:]+): (.*)$'
        )

        current_msg: Optional[Dict] = None

        for idx, line in enumerate(lines):
            match = pattern.match(line.strip())
            if match:
                if current_msg:
                    messages.append(current_msg)
                
                date_str, sender, content = match.groups()
                
                # Try parsing the date string. This is simplified and might need robust handling in production
                try:
                    # Strip commas and extra brackets first
                    clean_date = date_str.replace(',', '').strip()
                    if 'M' in clean_date: # AM/PM format
                        dt = datetime.strptime(clean_date, "%d/%m/%Y %I:%M %p")
                    else:
                        dt = datetime.strptime(clean_date, "%d/%m/%Y %H:%M")
                except ValueError:
                    # Fallback simple datetime if parsing fails
                    dt = datetime.now()

                current_msg = {
                    "id": f"wa_{idx}",
                    "sender": sender.strip(),
                    "content": content.strip(),
                    "timestamp": dt,
                    "reply_to": None,
                    "reactions": []
                }
            else:
                # Continuation of the previous message
                if current_msg and "- omitted" not in line:
                    current_msg['content'] += f"\n{line.strip()}"

        if current_msg:
            messages.append(current_msg)

        return [Message(**msg) for msg in messages]

    @classmethod
    def parse_telegram(cls, filepath: Path) -> List[Message]:
        """
        Parses Telegram JSON export files.
        Expects standard Telegram Desktop JSON structure.
        """
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        messages = []
        # Telegram exports can be a list of messages directly or nested under 'messages'
        raw_messages = data.get('messages', []) if isinstance(data, dict) else data
        
        for msg in raw_messages:
            if msg.get('type') != 'message':
                continue
                
            sender = msg.get('from', 'Unknown')
            if not sender:
                sender = "Unknown"
                
            # Content can be a string or a list of entities
            raw_text = msg.get('text', '')
            if isinstance(raw_text, list):
                text = ""
                for part in raw_text:
                    if isinstance(part, str):
                        text += part
                    elif isinstance(part, dict) and 'text' in part:
                        text += part['text']
            else:
                text = raw_text

            if not text:
                continue

            # Parse datetime
            try:
                # Format: "2023-12-31T23:59:00"
                dt = datetime.fromisoformat(msg.get('date'))
            except (ValueError, TypeError):
                dt = datetime.now()

            parsed_msg = Message(
                id=str(msg.get('id', '')),
                sender=sender,
                content=str(text),
                timestamp=dt,
                reply_to=str(msg.get('reply_to_message_id', '')) if msg.get('reply_to_message_id') else None,
                reactions=[]
            )
            messages.append(parsed_msg)

        return messages

    @classmethod
    def parse_slack(cls, filepath: Path) -> List[Message]:
        """
        Parses Slack .zip export files.
        Maps users from users.json and extracts messages from channel folders.
        """
        messages = []
        user_map = {}

        with zipfile.ZipFile(filepath, 'r') as z:
            # 1. Map users
            if 'users.json' in z.namelist():
                with z.open('users.json') as f:
                    users_data = json.load(f)
                    for user in users_data:
                        user_map[user.get('id')] = user.get('profile', {}).get('real_name') or user.get('name')

            # 2. Parse all other JSON files as channels (excluding users.json, channels.json, integration_logs.json)
            for filename in z.namelist():
                if not filename.endswith('.json') or filename in ['users.json', 'channels.json', 'integration_logs.json']:
                    continue

                with z.open(filename) as f:
                    channel_msgs = json.load(f)
                    for idx, msg in enumerate(channel_msgs):
                        if msg.get('type') != 'message' or msg.get('subtype'):
                            # Skip subtypes like channel_join, bot_message etc for now
                            continue

                        user_id = msg.get('user')
                        sender = user_map.get(user_id, user_id) or "Unknown"
                        
                        try:
                            # Slack ts is standard unix timestamp string "1704067140.000100"
                            ts = float(msg.get('ts', 0))
                            dt = datetime.fromtimestamp(ts)
                        except (ValueError, TypeError):
                            dt = datetime.now()

                        # Replicate reply tracking
                        reply_to = msg.get('thread_ts')
                        msg_id = msg.get('client_msg_id', f"slk_{ts}")

                        # Replicate reactions
                        reactions_users = []
                        for reaction in msg.get('reactions', []):
                            for r_user in reaction.get('users', []):
                                r_name = user_map.get(r_user, r_user)
                                if r_name not in reactions_users:
                                    reactions_users.append(r_name)

                        parsed_msg = Message(
                            id=msg_id,
                            sender=sender,
                            content=msg.get('text', ''),
                            timestamp=dt,
                            reply_to=str(reply_to) if reply_to and str(reply_to) != msg.get('ts') else None,
                            reactions=reactions_users
                        )
                        messages.append(parsed_msg)

        return messages
