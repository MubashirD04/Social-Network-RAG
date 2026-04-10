import uuid
import time
from typing import Dict, Any, Optional
from src.social_graph_builder import SocialGraphBuilder

class AnalysisStore:
    def __init__(self, ttl_seconds: int = 3600):
        self._store: Dict[str, Dict[str, Any]] = {}
        self.ttl_seconds = ttl_seconds

    def save(self, builder: SocialGraphBuilder, stats: Dict[str, Any], messages: list = None, embeddings: Any = None) -> str:
        analysis_id = str(uuid.uuid4())
        self._store[analysis_id] = {
            "builder": builder,
            "stats": stats,
            "messages": messages,
            "embeddings": embeddings,
            "timestamp": time.time()
        }
        return analysis_id

    def get(self, analysis_id: str) -> Optional[Dict[str, Any]]:
        self._evict_expired()
        return self._store.get(analysis_id)

    def delete(self, analysis_id: str) -> bool:
        if analysis_id in self._store:
            del self._store[analysis_id]
            return True
        return False

    def _evict_expired(self):
        current_time = time.time()
        expired_keys = [
            k for k, v in self._store.items() 
            if current_time - v["timestamp"] > self.ttl_seconds
        ]
        for k in expired_keys:
            del self._store[k]

# Global singleton component
analysis_store = AnalysisStore()
