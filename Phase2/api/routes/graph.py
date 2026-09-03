from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from src.llm_service import retrieval_service
from api.store import analysis_store

router = APIRouter()

class QueryRequest(BaseModel):
    query: str
    top_k: int = 5

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
    builder = analysis["builder"]
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
    
    results = []
    for idx, score in top_k_results:
        msg = messages[idx]
        results.append({
            "message_id": msg.id,
            "sender": msg.sender,
            "timestamp": msg.timestamp.isoformat(),
            "content": msg.content,
            "score": score
        })
        
    return {"results": results}

@router.delete("/{id}")
async def delete_analysis(id: str):
    success = analysis_store.delete(id)
    if not success:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return {"status": "deleted"}
