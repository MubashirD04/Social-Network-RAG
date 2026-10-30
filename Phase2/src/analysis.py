"""
Analysis logic shared by the FastAPI routes and the browser build
(src/browser_entry.py), so the two can't drift apart. Neither fastapi nor
fastembed is imported here: each caller embeds text its own way and passes
the vectors in.
"""
from typing import Any, Dict, List, Optional

import numpy as np

from src.conversation_linker import ConversationLinker
from src.social_graph_builder import SocialGraphBuilder
from src.social_models import Message


async def run_analysis(messages: List[Message], embeddings: np.ndarray, chat_name: str) -> Dict[str, Any]:
    builder = SocialGraphBuilder()
    stats = await builder.process_chat_data(messages, chat_name=chat_name)

    # Inferred-link layer: scores untagged message pairs (never ones
    # already linked by an explicit Slack thread_ts or the WhatsApp
    # parser's adjacency heuristic) for likely conversational continuity,
    # reusing the embeddings passed in. Toggleable off via
    # CONVERSATION_LINKING_ENABLED without affecting anything else here.
    inferred_links = ConversationLinker().score_pairs(messages, embeddings)

    return {
        "builder": builder,
        "stats": stats,
        "messages": messages,
        "embeddings": embeddings,
        "inferred_links": inferred_links,
    }


def serialize_graph_data(builder: SocialGraphBuilder) -> Dict[str, List[Dict[str, Any]]]:
    graph = builder.graph

    nodes = []
    for node_id, data in graph.nodes(data=True):
        node_dict = {"id": node_id}
        node_dict.update(data)
        nodes.append(node_dict)

    edges = []
    for source, target, data in graph.edges(data=True):
        edge_dict = {"source": source, "target": target}
        edge_dict.update(data)
        edges.append(edge_dict)

    return {"nodes": nodes, "edges": edges}


def build_query_results(analysis: Dict[str, Any], top_k_results: List[tuple], include_linked_context: bool = True) -> List[Dict[str, Any]]:
    messages = analysis["messages"]
    linked_context = _build_linked_context(analysis, messages, top_k_results) if include_linked_context else {}

    results = []
    for idx, score in top_k_results:
        msg = messages[idx]
        entry = {
            "message_id": msg.id,
            "sender": msg.sender,
            "timestamp": msg.timestamp.isoformat(),
            "content": msg.content,
            "score": score
        }
        if msg.id in linked_context:
            entry["linked_context"] = linked_context[msg.id]
        results.append(entry)

    return results


def _build_linked_context(analysis: Dict[str, Any], messages: List[Message], top_k_results: List[tuple]) -> Dict[str, List[Dict[str, Any]]]:
    """For each top-k hit, pulls in the messages the inferred-link layer
    connected it to — context beyond simple adjacency or explicit threads
    that a plain nearest-embedding search alone would miss."""
    inferred_links: Optional[list] = analysis.get("inferred_links") or []
    if not inferred_links:
        return {}

    msg_by_id = {msg.id: msg for msg in messages}
    adjacency: Dict[str, List] = {}
    for link in inferred_links:
        adjacency.setdefault(link.message_id_a, []).append(link)
        adjacency.setdefault(link.message_id_b, []).append(link)

    linked_context: Dict[str, List[Dict[str, Any]]] = {}
    for idx, _score in top_k_results:
        msg = messages[idx]
        neighbors = []
        for link in adjacency.get(msg.id, []):
            other_id = link.message_id_b if link.message_id_a == msg.id else link.message_id_a
            other = msg_by_id.get(other_id)
            if other is None:
                continue
            neighbors.append({
                "message_id": other.id,
                "sender": other.sender,
                "timestamp": other.timestamp.isoformat(),
                "content": other.content,
                "link_score": link.score
            })
        if neighbors:
            linked_context[msg.id] = neighbors

    return linked_context
