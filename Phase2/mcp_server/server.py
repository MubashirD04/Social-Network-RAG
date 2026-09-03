import httpx
from mcp.server.fastmcp import FastMCP
import asyncio
import os

# Initialize FastMCP Server
mcp = FastMCP("SocialNetworkRAG")

# Point tools to the local FastAPI instance
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

@mcp.tool()
async def analyse_chat(file_path: str) -> dict:
    """
    Upload and analyse a chat file.
    
    Args:
        file_path: Absolute path to the chat file (.txt, .json, .zip).
    """
    if not os.path.exists(file_path):
        return {"error": f"File not found: {file_path}"}
        
    async with httpx.AsyncClient() as client:
        with open(file_path, "rb") as f:
            files = {"file": (os.path.basename(file_path), f, "application/octet-stream")}
            try:
                response = await client.post(f"{API_BASE_URL}/analyse", files=files, timeout=300.0)
            except Exception as e:
                return {"error": f"Failed to connect to API on {API_BASE_URL}. Ensure it is running.", "detail": str(e)}
            
        if response.status_code == 200:
            return response.json()
        return {"error": f"API Error: {response.status_code}", "detail": response.text}

@mcp.tool()
async def get_influencers(analysis_id: str) -> dict:
    """
    Get the ranked influence report for a given analysis.
    
    Args:
        analysis_id: The UUID of the analysis.
    """
    async with httpx.AsyncClient() as client:
        try:
             response = await client.get(f"{API_BASE_URL}/graph/{analysis_id}/people")
        except Exception as e:
             return {"error": "Connection failed", "detail": str(e)}
             
        if response.status_code == 200:
            return response.json()
        return {"error": f"API Error: {response.status_code}", "detail": response.text}

@mcp.tool()
async def get_communities(analysis_id: str) -> dict:
    """
    Get community groupings and key members.
    
    Args:
        analysis_id: The UUID of the analysis.
    """
    async with httpx.AsyncClient() as client:
        try:
             response = await client.get(f"{API_BASE_URL}/graph/{analysis_id}/communities")
        except Exception as e:
             return {"error": "Connection failed", "detail": str(e)}
             
        if response.status_code == 200:
            return response.json()
        return {"error": f"API Error: {response.status_code}", "detail": response.text}

@mcp.tool()
async def get_topics(analysis_id: str) -> dict:
    """
    Get extracted topics for a chat.
    
    Args:
        analysis_id: The UUID of the analysis.
    """
    async with httpx.AsyncClient() as client:
        try:
             response = await client.get(f"{API_BASE_URL}/graph/{analysis_id}/topics")
        except Exception as e:
             return {"error": "Connection failed", "detail": str(e)}
             
        if response.status_code == 200:
            return response.json()
        return {"error": f"API Error: {response.status_code}", "detail": response.text}

@mcp.tool()
async def get_person_network(analysis_id: str, person_name: str) -> dict:
    """
    Get connections and metrics for a specific person.
    
    Args:
        analysis_id: The UUID of the analysis.
        person_name: Exact name of the person.
    """
    async with httpx.AsyncClient() as client:
        try:
             # First retrieve all people to find the matching one
             response = await client.get(f"{API_BASE_URL}/graph/{analysis_id}/people")
        except Exception as e:
             return {"error": "Connection failed", "detail": str(e)}

        if response.status_code == 200:
            # /graph/{id}/people returns a bare JSON array of people, not
            # {"people": [...]}. Match on "label" (the human-readable sender
            # name), not "name" (the internal p_-prefixed graph node id).
            people = response.json()
            for person in people:
                if person.get("label", "").lower() == person_name.lower():
                    return person
            return {"error": f"Person '{person_name}' not found in network."}
        return {"error": f"API Error: {response.status_code}", "detail": response.text}

@mcp.tool()
async def query_chat(analysis_id: str, query: str, top_k: int = 5) -> dict:
    """
    Semantic search over chat content — returns ranked relevant message chunks.
    
    Args:
        analysis_id: The UUID of the analysis.
        query: The semantic search query phrase.
        top_k: Number of message chunks to return.
    """
    async with httpx.AsyncClient() as client:
        payload = {"query": query, "top_k": top_k}
        try:
             response = await client.post(f"{API_BASE_URL}/graph/{analysis_id}/query", json=payload)
        except Exception as e:
             return {"error": "Connection failed", "detail": str(e)}
             
        if response.status_code == 200:
            return response.json()
        return {"error": f"API Error: {response.status_code}", "detail": response.text}

if __name__ == "__main__":
    mcp.run()
