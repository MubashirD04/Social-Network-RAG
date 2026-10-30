"""
Entry point for the Pyodide build, called from frontend/src/pipeline/worker.js.
Plays the role of the FastAPI routes and AnalysisStore for a single browser
tab: one analysis lives here at a time, and every result crosses back to
JavaScript as a JSON string.
"""
import json
import os
import uuid
from typing import Any, Dict, List, Optional

import numpy as np

from src.analysis import build_query_results, run_analysis, serialize_graph_data
from src.chat_parser import ChatParser
from src.coref_resolver import get_embedding_texts
from src.llm_service import LLMService
from src.social_models import Message

_pending_messages: List[Message] = []
_analysis: Optional[Dict[str, Any]] = None


def _json_default(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _dumps(payload: Any) -> str:
    return json.dumps(payload, default=_json_default)


def parse_file(path: str) -> str:
    """Parses an uploaded file and returns the texts JavaScript should embed."""
    global _pending_messages
    _pending_messages = ChatParser.parse_file(path)
    return _dumps(get_embedding_texts(_pending_messages))


async def analyse(embedding_bytes: Any, dimension: int, chat_name: str) -> str:
    global _analysis, _pending_messages
    messages = _pending_messages
    _pending_messages = []
    embeddings = np.frombuffer(embedding_bytes, dtype=np.float32).reshape(len(messages), dimension)

    _analysis = await run_analysis(messages, embeddings, chat_name)
    return _dumps({
        "id": str(uuid.uuid4()),
        "stats": _analysis["stats"],
        "graph": serialize_graph_data(_analysis["builder"]),
    })


async def set_topic_count(top_n: int) -> str:
    builder = _analysis["builder"]
    await builder.regenerate_topics(top_n)
    return _dumps(serialize_graph_data(builder))


def query(query_embedding_bytes: Any, top_k: int) -> str:
    query_embedding = np.frombuffer(query_embedding_bytes, dtype=np.float32)
    top_k_results = LLMService.top_k_by_embedding(query_embedding, _analysis["embeddings"], top_k)
    return _dumps({"results": build_query_results(_analysis, top_k_results)})


def remove_upload(path: str) -> None:
    if os.path.exists(path):
        os.unlink(path)
