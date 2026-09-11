# Social Network RAG

A powerful social network analysis tool that turns raw group chat exports into an interactive directed graph and exposes that analysis via a FastAPI service and Model Context Protocol (MCP) server.

## Overview

This project identifies key influencers, information brokers, and community clusters from chat interactions—all using **local machine learning** (no external LLM API costs for core analysis). It supports semantic search (RAG) over conversation history and provides interactive visualizations.

## Project Flow

The system operates in a structured pipeline:

1.  **Ingestion**: Raw exports from WhatsApp (.txt), Telegram (.json), or Slack (.zip) are parsed and normalized into a standard message schema. See [docs/data-export-guide.md](docs/data-export-guide.md) for step-by-step instructions on exporting each one.
2.  **Graph Construction**: Builds a directed graph of social interactions (Replies, Mentions, Reactions), plus inferred connections between unthreaded messages that clearly continue one conversation (shared wording, same channel, short time window) — kept visually and numerically distinct from confirmed connections so a guess never inflates anyone's influence score.
3.  **Local Analysis**:
    - **YAKE**: Extracts main conversation topics locally (unsupervised, no embeddings).
    - **NetworkX**: Calculates PageRank (Influence) and Betweenness Centrality (Info Brokers).
    - **Greedy Modularity**: Detects community clusters/sub-groups.
4.  **Retrieval Layer**: Uses `fastembed` (ONNX Runtime, no PyTorch) to generate text embeddings for every message, enabling semantic search via Cosine Similarity. A second, richer **inferred-conversation-linking layer** (`src/conversation_linker.py`) scores untagged message pairs — ones with no explicit reply — for likely conversational continuity (semantic similarity, temporal proximity, speaker turn-taking, shared keywords), and surfaces the result as extra `linked_context` on search results. See [docs/context.md](docs/context.md) for the full design, including an optional Tier 2 trained-classifier scoring mode and optional coreference-resolution preprocessing.
5.  **Interfaces**:
    - **API**: A FastAPI service exposing endpoints for analysis and retrieval.
    - **MCP**: A server that allows AI assistants (like Claude) to trigger analyses and query results directly.
    - **Web UI**: Interactive graph exploration and semantic search in the browser.

## Getting Started

### Prerequisites

- [uv](https://github.com/astral-sh/uv) (Fast Python package manager)
- [just](https://github.com/casey/just) (Command runner)
- Node.js (For frontend and MCP inspector)

### Installation

```bash
just install
```

This will create a virtual environment via `uv`, install Python dependencies, and set up the frontend `node_modules`.

### Running the System

You will typically need two or three terminals:

1.  **Backend API**:
    ```bash
    just api
    ```
2.  **Frontend UI**:
    ```bash
    just frontend
    ```
3.  **MCP Inspector** (for testing tools):
    ```bash
    just inspect
    ```

Alternatively, run the API and frontend together in the background with a single command:

```bash
just start
```

This logs the API to `/tmp/social-rag-api.log` and the frontend to `/tmp/social-rag-frontend.log`. Stop both with:

```bash
just stop
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
   # In a separate terminal, from the repo root
   export PYTHONPATH=$PYTHONPATH:$(pwd)/Phase2
   uv run uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
   ```

### Production Build

The backend is configured to serve the built frontend from `Phase2/frontend/dist`. To rebuild:

```bash
cd Phase2/frontend
npm run build
```

## Deployment

The root `Dockerfile` builds and serves the whole app as a single container: a Node stage builds the React frontend, and a Python stage runs the FastAPI backend, which serves that build directly (`Phase2/frontend/dist`) alongside the API — one image, one port, nothing else to host separately. The embedding model is baked into the image at build time, so the container needs no network access at startup.

```bash
docker build -t social-network-rag .
docker run -p 8000:8000 social-network-rag
```

This builds and runs the default image (~1.3GB, build-verified) — Tier 1 of the conversation-linking layer only, no optional Tier 2 extras. Tier 2 coreference resolution lives in a separate, opt-in build stage that a plain `docker build .` never reaches:

```bash
docker build --target runtime-coref -t social-network-rag:coref .
docker run -p 8000:8000 -e CONVERSATION_LINKING_COREF_ENABLED=true social-network-rag:coref
```

Hosted on **Hugging Face Spaces** (Docker SDK, 16GB RAM / 2 vCPU). Because `api/store.py`'s analysis store lives in process memory with no shared backing store, the service must run as a single instance — see [docs/context.md](docs/context.md#deployment) for the full rationale and the memory-profiling notes behind the current embedding-batch-size choice in `src/llm_service.py`.

## Testing on Linux

Since Claude Desktop is currently unavailable on Linux, we recommend using the **MCP Inspector** or **Cursor** to test and interact with the server.

### 1. Using MCP Inspector (Recommended for Debugging)

The MCP Inspector provides a local web UI to test tools and resources without an AI client.

**Requirements**: Node.js installed on your system.

**How to run**:

1.  **Start the FastAPI Backend**:
    ```bash
    export PYTHONPATH=$PYTHONPATH:$(pwd)/Phase2
    uv run uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
    ```
2.  **In a second terminal, launch the Inspector**:
    ```bash
    npx @modelcontextprotocol/inspector uv run python Phase2/mcp_server/server.py
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

- **Run Tests**: `just test` (or `PYTHONPATH=$PYTHONPATH:$(pwd)/Phase2 uv run pytest Phase2/tests -v`)
- **Manual Demo**: `just demo` (or `PYTHONPATH=$PYTHONPATH:$(pwd)/Phase2 uv run python Phase2/social_demo.py`) — generates a sample graph in `output/`
- **Large Scale Test**: `PYTHONPATH=$PYTHONPATH:$(pwd)/Phase2 uv run python Phase2/tests/large_social_test.py`
- **Conversation-linking layer**: `just build-slack-fixture` generates a synthetic Slack export; `just eval-linker <slack.zip>` reports precision/recall against its own `thread_ts` (the only real ground truth available); `just train-linker-classifier <slack.zip>` trains the optional Tier 2 classifier scoring mode. See [docs/context.md](docs/context.md) and [docs/conversation-linking-remaining-work.md](docs/conversation-linking-remaining-work.md).

## Visualization Legend

- **Person Nodes**: Colored by detected community (gray if not in one)
- **Yellow Diamonds**: Topics (pick 5-10 shown via the in-app slider)
- **Light Blue Ellipses**: Messages
- **Yellow Arrows**: Confirmed reply chains (explicit reply or an opening @mention)
- **Dashed Gray Arrows**: Inferred connections — messages that share distinctive wording but were never formally threaded. Toggleable in the app, and excluded from every influence/broker/community score regardless of whether they're shown.
- **Node Size**: Reflects Influence (PageRank)
- **Linked Context** (search panel): a richer, separate signal from the graph's dashed arrows above — semantic similarity, temporal proximity, speaker turn-taking, and shared keywords, not just wording overlap. Shown under a search result when it connects to another message with no explicit reply between them; click to jump to it in the graph.
