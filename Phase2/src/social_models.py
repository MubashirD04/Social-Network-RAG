from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field

class Message(BaseModel):
    id: str
    sender: str
    content: str
    timestamp: datetime
    reply_to: Optional[str] = None
    reactions: List[str] = Field(default_factory=list)
    # Which channel/room this came from (Slack only has real channels; other
    # formats are already a single conversation, so this stays None there).
    # Used to scope same-conversation heuristics — e.g. inferring a
    # connection between unthreaded messages — so they never fire across
    # two genuinely unrelated channels that just happen to share a filename
    # prefix or overlapping timestamps.
    channel: Optional[str] = None

class SocialAnalysisResult(BaseModel):
    topic: str
    sentiment: str
    key_entities: List[str] = Field(default_factory=list)
