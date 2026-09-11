from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from src.llm_service import retrieval_service
from api.store import analysis_store

router = APIRouter()

class QueryRequest(BaseModel):
    query: str
    top_k: int = 5
    # Expands each hit with any messages the inferred-link layer connected
    # it to (see src/conversation_linker.py) — context a plain nearest-
    # embedding search would miss, e.g. a short unthreaded reply that's
    # barely similar to the query itself but sits right next to the message
    # that is.
    include_linked_context: bool = True

class TopicCountRequest(BaseModel):
    # Keeps the topic layer from either being too sparse to be useful or
    # dense enough to clutter the graph for a viewer skimming it.
    top_n: int = Field(ge=5, le=10)

def serialize_graph_data(builder):
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

def get_analysis_or_404(analysis_id: str):
    analysis = analysis_store.get(analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found or expired")
    return analysis

@router.get("/{id}")
async def get_graph_metadata(id: str):
    analysis = get_analysis_or_404(id)
    return {"id": id, "stats": analysis["stats"]}

@router.get("/{id}/people")
async def get_people(id: str):
    analysis = get_analysis_or_404(id)
    builder = analysis["builder"]
    return builder.get_influence_report()

@router.get("/{id}/topics")
async def get_topics(id: str):
    analysis = get_analysis_or_404(id)
    builder = analysis["builder"]
    return {"topics": builder.get_topics()}

@router.post("/{id}/topics")
async def set_topic_count(id: str, request: TopicCountRequest):
    """Re-extracts topics at a new count (5-10) against the same messages
    the graph was already built from, and returns the full updated graph so
    the frontend can swap it straight into state without a second request."""
    analysis = get_analysis_or_404(id)
    builder = analysis["builder"]
    await builder.regenerate_topics(request.top_n)
    return serialize_graph_data(builder)

@router.get("/{id}/communities")
async def get_communities(id: str):
    analysis = get_analysis_or_404(id)
    builder = analysis["builder"]
    communities = {}
    for node, data in builder.graph.nodes(data=True):
        if data.get("type") == "person":
            comm_id = data.get("community", -1)
            if comm_id not in communities:
                communities[comm_id] = []
            communities[comm_id].append(node)
    return {"communities": communities}

@router.get("/{id}/data")
async def get_graph_data(id: str):
    analysis = get_analysis_or_404(id)
    return serialize_graph_data(analysis["builder"])

@router.get("/{id}/visualisation")
async def get_visualisation(id: str):
    # This is a standalone PyVis HTML export for viewing a graph outside the
    # React SPA (or from a non-browser MCP client). The SPA itself renders
    # its own graph via react-force-graph-2d and never embeds this output.
    analysis = get_analysis_or_404(id)
    builder = analysis["builder"]

    import tempfile
    import os


    tmp_path = os.path.join(tempfile.gettempdir(), f"viz_{id}.html")
    builder.visualize(tmp_path)
    
    return FileResponse(tmp_path, media_type="text/html", filename=f"network_{id}.html")

@router.post("/{id}/query")
async def query_chat(id: str, request: QueryRequest):
    analysis = get_analysis_or_404(id)
    messages = analysis.get("messages")
    embeddings = analysis.get("embeddings")

    if not messages or embeddings is None or len(messages) == 0:
        raise HTTPException(status_code=400, detail="Analysis does not contain retrievable chunks.")

    top_k_results = retrieval_service.get_top_k_similar(request.query, embeddings, k=request.top_k)

    linked_context = _build_linked_context(analysis, messages, top_k_results) if request.include_linked_context else {}

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

    return {"results": results}

def _build_linked_context(analysis, messages, top_k_results) -> Dict[str, List[Dict[str, Any]]]:
    """For each top-k hit, pulls in the messages the inferred-link layer
    connected it to — context beyond simple adjacency or explicit threads
    that a plain nearest-embedding search alone would miss."""
    inferred_links = analysis.get("inferred_links") or []
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

@router.get("/{id}/inferred-links")
async def get_inferred_links(id: str):
    """Raw edge list from the inferred-link layer: (message_id_a,
    message_id_b, score, signals). Separate from the visualization graph's
    own REPLIED_TO edges — this is the richer, embedding-backed signal meant
    for the retrieval layer (see _build_linked_context above), exposed
    directly here for callers that want the full edge list themselves."""
    analysis = get_analysis_or_404(id)
    inferred_links = analysis.get("inferred_links") or []
    return {
        "links": [
            {
                "message_id_a": link.message_id_a,
                "message_id_b": link.message_id_b,
                "score": link.score,
                "signals": link.signals
            }
            for link in inferred_links
        ]
    }

@router.delete("/{id}")
async def delete_analysis(id: str):
    success = analysis_store.delete(id)
    if not success:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return {"status": "deleted"}
