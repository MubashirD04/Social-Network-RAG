# Project Brief

## What It Is

A social network analysis tool that turns raw group chat exports into an interactive graph and exposes that analysis as an API and MCP server — so any AI model or external system can integrate it directly. Drop in a chat file, get back a structured map of who influences who, who brokers information between groups, and what the team is talking about. No cloud AI required for the core analysis.

---

## Where It Stands

The core pipeline, file ingestion (Phase 1), API layer (Phase 2), retrieval layer (Phase 3), and MCP server (Phase 4) are all complete and tested. The system can now process real chat exports from WhatsApp, Telegram, and Slack, and provide semantic search results through a standardized server protocol.

What does not exist yet is the Phase 5 web UI. Everything currently runs via the FastAPI endpoints or the MCP tools.

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

The project is organized into phases, with `Phase2` containing the active, production-ready codebase.

```
Social-Network-RAG/
├── Phase1/                   # Exploration and visualization (Notebooks)
├── Phase2/                   # Primary backend codebase
│   ├── src/                  # Core modules (Models, Graph Builder, Parser, LLM)
│   ├── api/                  # FastAPI layer and analysis store
│   ├── mcp_server/           # MCP server implementation
│   ├── tests/                # Automated test suites
│   ├── Dockerfile            # Container definition
│   ├── requirements.txt      # Dependencies
│   └── social_demo.py        # Minimal runnable demo
├── docs/                     # Documentation (brief.md, context.md)
├── scripts/
│   └── start-mcp.sh          # One-click startup script
├── test_data/                # Sample chat exports for testing
├── output/                   # Generated results (HTML, GraphML)
├── docker-compose.yml        # Multi-container orchestration
└── README.md                 # Entry point documentation
```

---

## Running the System

To start the entire backend (API and MCP server) and open the MCP Inspector for testing:

```bash
./scripts/start-mcp.sh
```

This will:

1. Start the FastAPI server at `http://localhost:8000`.
2. Wait for the API to be healthy.
3. Launch the MCP Inspector connected to `Phase2/mcp_server/server.py`.

---

## The Plan

### Phase 1 — File Ingestion

Build a `ChatParser` class that accepts uploaded files or compressed folders and normalises them into the existing `List[Message]` schema. This is the prerequisite for everything else — the API cannot accept real input without it.

Support formats in priority order:

1. **WhatsApp** — `.txt` line-by-line format
2. **Telegram** — `.json` export
3. **Slack** — `.zip` of per-channel `.json` files
4. **Discord** — `.json` (varies by export tool)

The parser should auto-detect format from file extension and content structure, handle missing fields gracefully (WhatsApp has no reactions or reply IDs natively), and reject unrecognised formats with a clear error. Once this exists the entire downstream pipeline works without any changes.

### Phase 2 — API Layer

Wrap the pipeline in a FastAPI service. The existing Pydantic models become request and response schemas directly. Endpoints map cleanly to what the pipeline already does.

**Endpoints:**

| Method | Path                        | Description                                        |
| ------ | --------------------------- | -------------------------------------------------- |
| POST   | `/analyse`                  | Upload a chat file, run the pipeline, return stats |
| GET    | `/graph/{id}`               | Full graph data for a previously run analysis      |
| GET    | `/graph/{id}/people`        | Influence report — all participants ranked         |
| GET    | `/graph/{id}/topics`        | Extracted topics for a chat                        |
| GET    | `/graph/{id}/communities`   | Community groupings and membership                 |
| GET    | `/graph/{id}/visualisation` | Serve the generated HTML graph                     |
| POST   | `/graph/{id}/query`         | Natural language RAG query (stubbed until Phase 3) |
| DELETE | `/graph/{id}`               | Remove a stored analysis                           |

Analyses are identified by a UUID returned from `/analyse`. Results are stored server-side (initially in memory, later persistent).

### Phase 3 — Retrieval Layer

Implement semantic search over message content so the `POST /graph/{id}/query` endpoint can return relevant chunks for a given query. No LLM generation step — the calling model (whatever invoked the MCP tool) handles that itself. This keeps the stack entirely free of external API dependencies.

What needs building:

- At analysis time, chunk each message and embed it using `sentence-transformers` (already in `llm_service.py`)
- Store chunk embeddings alongside the graph in the analysis store
- On query, embed the query string and run cosine similarity against stored chunks
- Return the top-k matching chunks as structured data — message ID, sender, timestamp, content, similarity score
- The calling model receives this context and generates its own answer

This makes `query_chat` a retrieval tool, not a question-answering tool. The AI model calling it does the generation. No nested LLM calls, no API key, no cost per query.

`llm_service.py` can be simplified to just `generate_embeddings()` and `chunk_text()` — the Groq client and `instructor` dependency are removed entirely.

### Phase 4 — MCP Server

Expose the API as callable tools via the Anthropic MCP Python SDK. This is what allows any MCP-compatible AI model to trigger and interrogate an analysis mid-conversation.

**Tools:**

| Tool                 | Description                                                                |
| -------------------- | -------------------------------------------------------------------------- |
| `analyse_chat`       | Upload and analyse a chat file, returns analysis ID + summary              |
| `get_influencers`    | Ranked influence report for a given analysis                               |
| `get_communities`    | Community groupings and key members                                        |
| `get_topics`         | Extracted topics                                                           |
| `get_person_network` | Connections and metrics for a specific person                              |
| `query_chat`         | Semantic search over chat content — returns ranked relevant message chunks |

The MCP server is a thin wrapper — each tool calls the FastAPI service internally. No business logic lives in the MCP layer.

### Phase 5 — Web UI

A browser interface that is intuitive enough to use without instructions and interactive enough to reward exploration. The UI is one consumer of the API, not the primary deliverable.

**Core:**

- Drag-and-drop file zone as the entry point — no forms, no configuration
- Visible loading progress while the pipeline runs
- Graph rendered inline in the browser

**Graph interactivity:**

- Clicking a person node highlights all their connections and dims everything else
- Clicking a topic node surfaces every message that mentions it
- Clicking a message node shows full text, sender, timestamp, and reply thread in the sidebar
- Search bar to locate any node by name and centre the graph on it
- Timeline scrubber to replay the conversation chronologically
- Filter to a single community or a single person's ego network

**Query panel:**

- Persistent search input docked alongside the graph
- Returns ranked relevant messages rather than generated answers — the results highlight directly in the graph
- Each result shows sender, timestamp, content, and relevance score
- Clicking a result centres the graph on that message node

**General UX:**

- Dark theme consistent with the existing visualisation
- No technical jargon — "Influence Score" not "PageRank", "Connector" not "Betweenness Centrality"
- Tooltips on hover for every metric and badge
- Mobile-responsive layout

---

## What to Leave Alone

- `social_graph_builder.py` — stable, do not add LLM calls back into it
- `social_models.py` — the `Message` schema is the contract between the parser and the pipeline, keep it minimal
- `archive/graph_builder.py` — legacy, not part of this project
- `llm_test.py` and `graph_test.py` — legacy, can be deleted
