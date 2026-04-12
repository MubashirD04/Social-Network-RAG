# Project Brief

## What It Is

A social network analysis tool that turns raw group chat exports into an interactive graph and exposes that analysis as an API and MCP server — so any AI model or external system can integrate it directly. Drop in a chat file, get back a structured map of who influences who, who brokers information between groups, and what the team is talking about. No cloud AI required at any stage.

---

## Where It Stands

The core pipeline, file ingestion (Phase 1), API layer (Phase 2), retrieval layer (Phase 3), and MCP server (Phase 4) are all complete and tested. The system processes real chat exports from WhatsApp, Telegram, and Slack and exposes semantic search through a standardised server protocol.

The Phase 5 web UI exists as a scaffold (React + Vite + react-force-graph-2d) but has known issues that must be resolved before it is considered functional. Everything currently runs via the FastAPI endpoints or MCP tools.

---

## Language and Stack Decision

The entire project is Python. This was an explicit decision — the analysis pipeline depends on NetworkX, KeyBERT, sentence-transformers, and PyVis, none of which have Go equivalents. Moving the API layer to Go would mean running it as a proxy in front of a Python service, adding complexity with no real benefit. The bottleneck will always be the analysis pipeline itself, not the HTTP layer.

**Stack:**

| Layer         | Library               | Reason                                            |
|---------------|-----------------------|---------------------------------------------------|
| API           | FastAPI               | Async, auto OpenAPI docs, Pydantic schemas reused |
| Server        | uvicorn               | ASGI, production-grade, pairs with FastAPI        |
| MCP server    | mcp (Anthropic SDK)   | Official Python SDK, straightforward to build     |
| Schemas       | Pydantic              | Already used throughout, shared across all layers |
| Analysis      | NetworkX, KeyBERT     | Existing pipeline, unchanged                      |
| RAG retrieval | sentence-transformers | Local embeddings, no API key required             |

---

## Project Structure

```
Social-Network-RAG/
├── Phase1/                   # Exploration notebooks (legacy)
├── Phase2/                   # Primary codebase
│   ├── src/                  # Core modules
│   ├── api/                  # FastAPI layer and analysis store
│   ├── mcp_server/           # MCP server implementation
│   ├── frontend/             # React + Vite web UI (Phase 5, in progress)
│   ├── tests/                # Automated test suites
│   ├── Dockerfile            # API + pipeline container definition
│   ├── requirements.txt      # Python dependencies
│   └── social_demo.py        # Minimal runnable demo
├── docs/                     # brief.md and context.md
├── scripts/
│   └── start-mcp.sh          # Starts API + MCP Inspector for testing
├── test_data/                # Sample chat exports for testing
├── output/                   # Generated HTML and GraphML files
├── docker-compose.yml        # Three-service Compose stack
├── Justfile                  # Local dev commands (just start, just test)
├── Makefile                  # Alternative to Justfile
└── README.md                 # Entry point — setup and usage
```

---

## Running the System

Two supported paths. Both are documented in the README.

### Containerised (Docker Compose or Podman)

```bash
docker compose up
# or with Podman
podman-compose up
```

Starts three services: API, frontend, and MCP server. The sentence-transformers model (~90MB) is not baked into the image — it downloads on first boot and caches to a mounted volume. Every subsequent start is instant with no re-download.

Works with Docker Desktop for the Claude Desktop MCP integration pattern. See README for Claude Desktop config.

### Local (no container runtime)

```bash
just install   # create venv via uv, install Python + npm deps
just start     # start API, frontend dev server, and MCP server
just test      # run full pytest suite
just stop      # stop all managed processes
```

Uses `uv` for fast dependency management and `just` (or `make`) as a process runner. No Docker required, works everywhere Python 3.12 runs.

---

## The Plan

### Phase 1 — File Ingestion ✅

`ChatParser.parse_file()` normalises WhatsApp (`.txt`), Telegram (`.json`), and Slack (`.zip`) exports into `List[Message]`. Auto-detects format, handles missing fields gracefully, rejects unrecognised formats with a clear error.

### Phase 2 — API Layer ✅

FastAPI service wrapping the pipeline. Analyses identified by UUID, results stored in-memory with TTL expiry.

**Endpoints:**

| Method | Path                        | Description                                          |
|--------|-----------------------------|------------------------------------------------------|
| POST   | `/analyse`                  | Upload a chat file, run the pipeline, return stats   |
| GET    | `/graph/{id}`               | Full graph data for a previously run analysis        |
| GET    | `/graph/{id}/people`        | Influence report — all participants ranked           |
| GET    | `/graph/{id}/topics`        | Extracted topics for a chat                          |
| GET    | `/graph/{id}/communities`   | Community groupings and membership                   |
| GET    | `/graph/{id}/visualisation` | Serve the generated PyVis HTML graph                 |
| POST   | `/graph/{id}/query`         | Semantic search over message content                 |
| DELETE | `/graph/{id}`               | Remove a stored analysis                             |

### Phase 3 — Retrieval Layer ✅

Semantic search over message content using local `sentence-transformers` embeddings and cosine similarity. No LLM generation step — the calling model handles answer synthesis from the returned chunks. No API key, no cost per query.

### Phase 4 — MCP Server ✅

Thin wrapper around the API exposing callable tools via the Anthropic MCP Python SDK. Runs as a sidecar in the Docker Compose stack — depends on the API service, starts after it, exposes an HTTP port for Claude Desktop or any MCP-compatible client to reach.

**Tools:**

| Tool                 | Description                                                                |
|----------------------|----------------------------------------------------------------------------|
| `analyse_chat`       | Upload and analyse a chat file, returns analysis ID + summary              |
| `get_influencers`    | Ranked influence report for a given analysis                               |
| `get_communities`    | Community groupings and key members                                        |
| `get_topics`         | Extracted topics                                                           |
| `get_person_network` | Connections and metrics for a specific person                              |
| `query_chat`         | Semantic search — returns ranked relevant message chunks                   |

### Phase 5 — Web UI (in progress)

A browser interface that is intuitive enough to use without instructions and interactive enough to reward exploration. Runs as a **separate service** from the API — both in Docker Compose and locally. It is one consumer of the API, not the primary deliverable.

**Known issues to resolve before Phase 5 ships:**
- Debug log panel is hardcoded into `App.jsx` — must be removed
- Node ID prefix convention (`p_`, `m_`) between backend and frontend is implicit — needs to be formalised or removed
- Two graph renderers coexist (`react-force-graph-2d` in the UI vs PyVis for `/visualisation`) — decide one owner
- `window.location.reload()` used for reset — replace with clean React state reset
- Development artefacts in `App.css` (`/* DIAGNOSTIC PURPLE */` comment) — remove

**Target UX once issues are resolved:**

- Drag-and-drop file zone as entry point — no forms, no configuration
- Visible loading progress while the pipeline runs
- Graph rendered inline; clicking a person node highlights connections, clicking a topic surfaces related messages, clicking a message shows full content and thread
- Search bar to locate any node by name
- Timeline scrubber to replay conversation chronologically
- Filter to a single community or ego network
- Persistent query panel — results highlight in the graph, each showing sender, timestamp, content, and relevance score
- Dark theme, no technical jargon, tooltips on all metrics, mobile-responsive

---

## Containerisation

### Architecture: three-service Docker Compose stack

| Service    | Exposed to host | Notes                                        |
|------------|-----------------|----------------------------------------------|
| `api`      | No              | Internal only, reachable by frontend and MCP |
| `frontend` | Yes             | Static files on a host port                  |
| `mcp`      | Yes             | HTTP transport — Claude Desktop connects here |

All three share an internal Compose network. The MCP server is a sidecar — it depends on the API, enforces startup order via `depends_on`, and has no logic of its own.

### Model caching: download on first boot

The sentence-transformers model is not baked into the image. On first container start the API checks a mounted volume for the model, downloads it if absent, and skips the download on all subsequent starts. Image stays lean; first run is slow, every run after is instant. No manual setup required from the user.

### Podman alternative

The same `docker-compose.yml` runs with `podman-compose`. No Docker Desktop license, no background daemon. Recommended for Linux users.

---

## Local Development

`uv` handles virtual environments and dependency installation significantly faster than pip. `just` (or `make`) manages all three processes from a single config.

```bash
just install   # uv sync + npm install
just start     # API + frontend + MCP in parallel with correct PYTHONPATH
just test      # pytest Phase2/tests/
just stop      # terminate managed processes
```

---

## What to Leave Alone

- `social_graph_builder.py` — stable, do not add LLM calls back into it
- `social_models.py` — the `Message` schema is the contract between the parser and the pipeline, keep it minimal
- `archive/graph_builder.py` — legacy, not part of this project
- `llm_test.py` and `graph_test.py` — legacy, can be deleted
