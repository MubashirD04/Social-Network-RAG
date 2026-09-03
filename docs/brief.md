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
| ------------- | --------------------- | ------------------------------------------------- |
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
│   ├── requirements.txt      # Python dependencies
│   └── social_demo.py        # Minimal runnable demo
├── docs/                     # brief.md and context.md
├── scripts/
│   └── start-mcp.sh          # Starts API + MCP Inspector for testing
├── test_data/                # Sample chat exports for testing
├── Justfile                  # Local dev commands (just install, just api, etc.)
└── README.md                 # Entry point — setup and usage
```

---

## Running the System

### Local Execution

```bash
just install   # create venv via uv, install Python + npm deps
just start     # start API + frontend dev server together in the background
just test      # run full pytest suite
just stop      # stop processes started by `just start`
```

Uses `uv` for fast dependency management and `just` as a process runner. No Docker required, works everywhere Python 3.12 runs.

---

## The Plan

### Phase 1 — File Ingestion ✅

`ChatParser.parse_file()` normalises WhatsApp (`.txt`), Telegram (`.json`), and Slack (`.zip`) exports into `List[Message]`. Auto-detects format, handles missing fields gracefully, rejects unrecognised formats with a clear error.

### Phase 2 — API Layer ✅

FastAPI service wrapping the pipeline. Analyses identified by UUID, results stored in-memory with TTL expiry.

**Endpoints:**

| Method | Path                        | Description                                        |
| ------ | --------------------------- | -------------------------------------------------- |
| POST   | `/analyse`                  | Upload a chat file, run the pipeline, return stats |
| GET    | `/graph/{id}`               | Full graph data for a previously run analysis      |
| GET    | `/graph/{id}/people`        | Influence report — all participants ranked         |
| GET    | `/graph/{id}/topics`        | Extracted topics for a chat                        |
| GET    | `/graph/{id}/communities`   | Community groupings and membership                 |
| GET    | `/graph/{id}/data`          | Raw nodes/edges for the React frontend's graph      |
| GET    | `/graph/{id}/visualisation` | Serve the generated standalone PyVis HTML export   |
| POST   | `/graph/{id}/query`         | Semantic search over message content               |
| DELETE | `/graph/{id}`               | Remove a stored analysis                           |

### Phase 3 — Retrieval Layer ✅

Semantic search over message content using local `sentence-transformers` embeddings and cosine similarity. No LLM generation step — the calling model handles answer synthesis from the returned chunks. No API key, no cost per query.

### Phase 4 — MCP Server ✅

Thin wrapper around the API exposing callable tools via the Anthropic MCP Python SDK. Depends on the API service, starts after it, exposes an HTTP port for Claude Desktop or any MCP-compatible client to reach.

**Tools:**

| Tool                 | Description                                                   |
| -------------------- | ------------------------------------------------------------- |
| `analyse_chat`       | Upload and analyse a chat file, returns analysis ID + summary |
| `get_influencers`    | Ranked influence report for a given analysis                  |
| `get_communities`    | Community groupings and key members                           |
| `get_topics`         | Extracted topics                                              |
| `get_person_network` | Connections and metrics for a specific person                 |
| `query_chat`         | Semantic search — returns ranked relevant message chunks      |

### Phase 5 — Web UI (in progress)

A browser interface that is intuitive enough to use without instructions and interactive enough to reward exploration. Runs as a **separate service** from the API. It is one consumer of the API, not the primary deliverable.

**Known issues — resolved:**

- ~~Debug log panel hardcoded into `App.jsx`~~ — removed.
- ~~Node ID prefix convention (`p_`, `m_`) implicit~~ — formalised as a `nodeId` helper (`App.jsx`) instead of inline template literals; documented in `social_graph_builder.py`.
- ~~Two graph renderers coexist~~ — ownership decided and documented in both places: `react-force-graph-2d` is the only in-app renderer; PyVis's `/graph/{id}/visualisation` is kept as a separate, standalone HTML export (for viewing outside the SPA, e.g. from an MCP client), never embedded in the app.
- ~~`window.location.reload()` used for reset~~ — replaced with a `resetApp()` function that clears React state.
- ~~`/* DIAGNOSTIC PURPLE */` comment in `App.css`~~ — removed.

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

---

## Local Development

### Tooling

- `uv` — Unified Python tool for virtual environments and dependency management.
- `just` — Command runner to manage all services.

### Commands

```bash
just install   # uv venv + uv pip install + npm install
just api       # Start FastAPI backend
just frontend  # Start Vite development server
just start     # Start API + frontend together in the background
just stop      # Stop processes started by `just start`
just inspect   # Start MCP Inspector
just test      # Run all tests
just clean     # Clean up temporary files
```

---

## What to Leave Alone

- `social_graph_builder.py` — stable, do not add LLM calls back into it
- `social_models.py` — the `Message` schema is the contract between the parser and the pipeline, keep it minimal
