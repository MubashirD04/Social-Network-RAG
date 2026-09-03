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
        }
    ]
    
    with zipfile.ZipFile(file_path, 'w') as z:
        z.writestr('users.json', json.dumps(users))
        z.writestr('general/updates.json', json.dumps(channel_msgs))
        
    messages = ChatParser.parse_file(file_path)
    
    assert len(messages) == 2
    assert messages[0].sender == "Alice"
    assert messages[0].id == "msg1"
    
    assert messages[1].sender == "Bob"
    assert "Alice" in messages[1].reactions
    assert messages[1].content == "With reaction"
