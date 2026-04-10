# Social Network RAG

A powerful social network analysis tool that turns raw group chat exports into an interactive directed graph and exposes that analysis via a FastAPI service and Model Context Protocol (MCP) server.

## Overview

This project identifies key influencers, information brokers, and community clusters from chat interactions—all using **local machine learning** (no external LLM API costs for core analysis). It supports semantic search (RAG) over conversation history and provides interactive visualizations.

## Project Flow

The system operates in a structured pipeline:
1.  **Ingestion**: Raw exports from WhatsApp (.txt), Telegram (.json), or Slack (.zip) are parsed and normalized into a standard message schema.
2.  **Graph Construction**: Builds a directed graph of social interactions (Replies, Mentions, Reactions).
3.  **Local Analysis**: 
    - **KeyBERT**: Extracts main conversation topics locally.
    - **NetworkX**: Calculates PageRank (Influence) and Betweenness Centrality (Info Brokers).
    - **Greedy Modularity**: Detects community clusters/sub-groups.
4.  **Retrieval Layer**: Uses `sentence-transformers` to generate text embeddings for every message, enabling semantic search via Cosine Similarity.
5.  **Interfaces**:
    - **API**: A FastAPI service exposing endpoints for analysis and retrieval.
    - **MCP**: A server that allows AI assistants (like Claude) to trigger analyses and query results directly.
    - **Web UI**: (Phase 5) Interactive graph exploration in the browser.

## Getting Started

### Prerequisites

- Python 3.12+
- Recommended: A virtual environment (`venv`)

### Installation

1. Clone the repository.
2. Create and activate a virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install -r Phase2/requirements.txt
   ```

### Running the API

The MCP server requires the backend API to be running:

```bash
export PYTHONPATH=$PYTHONPATH:$(pwd)/Phase2
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

## MCP Server Integration

The MCP server allows you to connect this tool to the **Claude Desktop** app or any other MCP-compatible client.

### 1. Locate your Paths
You will need the absolute paths to your virtual environment's Python executable and the MCP server script:
- **Python Path**: `path/to/Social-Network-RAG/venv/bin/python3`
- **Server Script**: `path/to/Social-Network-RAG/Phase2/mcp/server.py`

### 2. Configure Claude Desktop
Open your Claude Desktop configuration file (usually `~/Library/Application Support/Claude/claude_desktop_config.json` on macOS or `%APPDATA%\Claude\claude_desktop_config.json` on Windows):

```json
{
  "mcpServers": {
    "social-rag": {
      "command": "/path/to/your/venv/bin/python3",
      "args": [
        "/path/to/your/Phase2/mcp/server.py"
      ],
      "env": {
        "PYTHONPATH": "/path/to/your/Phase2"
      }
    }
  }
}
```

### 3. Restart Claude
After restarting, you should see the `SocialNetworkRAG` tools available (e.g., `analyse_chat`, `query_chat`, `get_influencers`).

### VS Code Integration (Roo Code)

If you use VS Code with the **Roo Code** extension, you can integrate this MCP server directly:

1.  Open the Roo Code settings (Settings cog in the Roo Code panel).
2.  Navigate to **MCP Servers**.
3.  Click **Edit Settings (JSON)**.
4.  Add the following entry to the `mcpServers` object (ensure absolute paths):
    ```json
    "social-rag": {
      "command": "/path/to/your/venv/bin/python3",
      "args": [
        "/path/to/your/Phase2/mcp/server.py"
      ],
      "env": {
        "PYTHONPATH": "/path/to/your/Phase2"
      }
    }
    ```
5.  Save and check the "MCP Server" tab in Roo Code to verify it is "Connected".

## Developer Tools

- **Run Tests**: `pytest Phase2/tests`
- **Manual Demo**: `python Phase2/social_demo.py` (generates a sample graph in `output/`)
- **Large Scale Test**: `python Phase2/tests/large_social_test.py`

## Visualization Legend

- **Teal Nodes**: People
- **Yellow Diamonds**: Topics
- **Light Blue Ellipses**: Messages
- **Yellow Arrows**: Reply chains
- **Node Size**: Reflects Influence (PageRank)
- **Node Color**: Reflects Detected Community Grouping
