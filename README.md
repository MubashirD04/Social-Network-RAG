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

## Phase 5: Modern React Web UI

The project now includes a high-performance React dashboard powered by Vite.

### Development Setup

1. **Frontend**:
   ```bash
   cd Phase2/frontend
   npm install
   npm run dev
   ```
2. **Backend**:
   ```bash
   # In a separate terminal
   export PYTHONPATH=$PYTHONPATH:$(pwd)/Phase2
   ./venv/bin/python3 Phase2/api/main.py
   ```

### Production Build

The backend is configured to serve the built frontend from `Phase2/frontend/dist`. To rebuild:

```bash
cd Phase2/frontend
npm run build
```

## Testing on Linux

Since Claude Desktop is currently unavailable on Linux, we recommend using the **MCP Inspector** or **Cursor** to test and interact with the server.

### 1. Using MCP Inspector (Recommended for Debugging)

The MCP Inspector provides a local web UI to test tools and resources without an AI client.

**Requirements**: Node.js installed on your system.

**How to run**:

1.  **Start the FastAPI Backend**:
    ```bash
    export PYTHONPATH=$PYTHONPATH:$(pwd)/Phase2
    uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
    ```
2.  **In a second terminal, launch the Inspector**:
    ```bash
    npx @modelcontextprotocol/inspector python Phase2/mcp_server/server.py
    ```
3.  Open the URL provided (usually `http://localhost:3000`) in your browser. You can now trigger tools like `analyse_chat` directly.

### 2. Using Cursor (IDE)

Cursor is a fork of VS Code that supports MCP natively on Linux.

1.  Open Cursor Settings > **Models** > **MCP Servers**.
2.  Add a new server:
    - **Name**: `social-rag`
    - **Type**: `command`
    - **Command**: `path/to/your/venv/bin/python3 Phase2/mcp_server/server.py`
3.  Set the Environment Variable `PYTHONPATH` to the absolute path of the `Phase2` directory.

### 3. Using Goose (CLI Agent)

If you prefer a terminal-based agent:

1.  Install Goose: `curl -fsSL https://goose.b7s.ai/install.sh | sh`
2.  Add the server to `~/.config/goose/config.yaml`.

## Integration (macOS/Windows)

For users on macOS or Windows, you can connect this tool directly to **Claude Desktop**.

### 1. Locate your Paths

You will need the absolute paths to your virtual environment's Python executable and the `Phase2` directory:

- **Python Path**: `path/to/Social-Network-RAG/venv/bin/python3`
- **Server Script**: `path/to/Social-Network-RAG/Phase2/mcp_server/server.py`

### 2. Configure Claude Desktop

Open your Claude Desktop configuration file (usually `~/Library/Application Support/Claude/claude_desktop_config.json` on macOS or `%APPDATA%\Claude\claude_desktop_config.json` on Windows):

```json
{
  "mcpServers": {
    "social-rag": {
      "command": "/path/to/your/venv/bin/python3",
      "args": ["/path/to/your/Phase2/mcp_server/server.py"],
      "env": {
        "PYTHONPATH": "/path/to/your/Phase2"
      }
    }
  }
}
```

### 3. Restart Claude

After restarting, you should see the `SocialNetworkRAG` tools available in the paperclip menu or via slash commands.

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
