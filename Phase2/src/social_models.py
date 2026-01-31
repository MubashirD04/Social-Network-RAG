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

class SocialAnalysisResult(BaseModel):
    topic: str
    sentiment: str
    key_entities: List[str] = Field(default_factory=list)
