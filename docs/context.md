# Project Context

## Overview

A social network analysis tool that processes group chat data into an interactive directed graph and exposes that analysis via a FastAPI service and MCP server. Identifies key influencers, information brokers, and community clusters from raw message interactions — without requiring any external API calls at any stage. The MCP server allows any compatible AI model to trigger and interrogate analyses directly.

---

## Current State

The core pipeline, file ingestion (Phase 1), API layer (Phase 2), retrieval layer (Phase 3), and MCP server (Phase 4) are all fully functional and tested. The system is ready to be explored via Claude Desktop, the MCP Inspector, or direct API calls.

The Phase 5 web UI exists as a scaffold but has known issues — see the Known Limitations section.

---

## Active File Structure

```
Social-Network-RAG/
├── Phase1/                       # Exploration notebooks (legacy)
├── Phase2/
│   ├── src/
│   │   ├── __init__.py
│   │   ├── social_models.py          # Pydantic Message schema — shared contract
│   │   ├── social_graph_builder.py   # Core analysis pipeline
│   │   ├── chat_parser.py            # File ingestion (WhatsApp, Telegram, Slack)
│   │   ├── llm_service.py            # Local embeddings + retrieval
│   │   └── config.py                 # Environment settings (unused currently)
│   ├── api/
│   │   ├── __init__.py
│   │   ├── main.py                   # FastAPI app entry point
│   │   ├── store.py                  # In-memory analysis store (UUID → data)
│   │   └── routes/
│   │       ├── __init__.py
│   │       ├── analyse.py            # POST /analyse
│   │       └── graph.py              # GET/POST/DELETE /graph/{id}/*
│   ├── mcp_server/
│   │   ├── __init__.py
│   │   └── server.py                 # MCP server — thin wrappers over API calls
│   ├── frontend/                     # Phase 5 — React + Vite (in progress)
│   │   ├── src/
│   │   │   ├── App.jsx               # Main component (has known issues — see below)
│   │   │   ├── App.css
│   │   │   ├── index.css
│   │   │   └── main.jsx
│   │   ├── public/
│   │   ├── package.json
│   │   └── vite.config.js            # Dev proxy: /analyse, /graph → localhost:8000
│   ├── tests/
│   │   ├── test_social_pipeline.py   # 47 tests — full pipeline, KeyBERT stubbed
│   │   ├── test_chat_parser.py       # Parser tests per format
│   │   └── test_api.py               # Endpoint + retrieval tests
│   ├── archive/
│   │   └── graph_builder.py          # Legacy — ignore
│   ├── requirements.txt
│   └── social_demo.py
├── docs/
│   ├── brief.md                      # Forward-looking plan and decisions
│   └── context.md                    # This file — technical reference
├── scripts/
│   └── start-mcp.sh                  # Starts API + MCP Inspector
├── test_data/                        # Sample chat exports
├── output/                           # Generated HTML + GraphML
├── Justfile                          # Local dev commands
└── README.md
```

---

## Data Flow

```
Uploaded file (.txt / .json / .zip)
    │
    ▼
ChatParser.parse_file()                    ← Phase 1
    │
    ▼
List[Message]
    │
    ▼
SocialGraphBuilder.process_chat_data()     ← Phase 2 pipeline
    │
    ├── Build person, message, chat nodes
    ├── Parse reply/mention/reaction edges (regex, no LLM)
    ├── Extract topics via KeyBERT (local)
    ├── Calculate PageRank + betweenness centrality
    ├── Detect communities (greedy modularity)
    └── Assign badges (INFLUENCER, INFO_BROKER)
    │
    ▼
nx.DiGraph + message embeddings            ← stored by UUID in api/store.py
    │
    ├── GET /graph/{id}/people             → influence report
    ├── GET /graph/{id}/topics             → topic list
    ├── GET /graph/{id}/communities        → community groupings
    ├── GET /graph/{id}/visualisation      → PyVis HTML graph
    └── POST /graph/{id}/query             → cosine similarity → ranked chunks
    │
    ▼
MCP tools — HTTP calls to the API above
    │
    ▼
Calling AI model synthesises answer from returned chunks
(no LLM generation step inside the pipeline)
```

---

## Core Classes and Responsibilities

### `src/social_models.py`

Defines the normalised message schema. All parsers must produce this. Shared across pipeline, API, and MCP.

```python
class Message(BaseModel):
    id: str
    sender: str
    content: str
    timestamp: datetime
    reply_to: Optional[str] = None      # ID of message being replied to
    reactions: List[str] = []           # List of sender names who reacted
```

### `src/social_graph_builder.py`

The entire analysis pipeline. No external API dependencies. Complete and tested.

Key methods:

- `process_chat_data(messages, chat_name)` — async, builds full graph, returns stats dict
- `_extract_topics_keybert(messages, top_n)` — local keyword extraction via KeyBERT
- `_calculate_stats()` — computes PageRank, betweenness, activity counts, badges
- `_detect_communities(graph, nodes)` — greedy modularity on undirected interaction graph
- `get_influence_report()` — list of per-person metric dicts sorted by PageRank
- `visualize(output_file)` — PyVis HTML with injected interactive sidebar
- `save_graph(filepath)` — writes GraphML

### `src/chat_parser.py`

Single public method: `parse_file(filepath) -> List[Message]`. Auto-detects format from file extension.

Private parsers:

- `parse_whatsapp(filepath)` — `.txt`, handles both 12hr and 24hr date formats
- `parse_telegram(filepath)` — standard Telegram Desktop `.json` export
- `parse_slack(filepath)` — `.zip` of per-channel `.json` files, maps user IDs via `users.json`

### `src/llm_service.py`

Local intelligence only. No external API calls, no API key required.

- `generate_embeddings(texts)` → `np.ndarray` — sentence-transformers embeddings
- `get_top_k_similar(query, embeddings, k)` → ranked `(index, score)` tuples — cosine similarity
- `extract_topics(messages, top_n)` → `List[str]` — KeyBERT extraction

Exports a module-level singleton: `retrieval_service = LLMService()` used by the API routes.

### `api/store.py`

In-memory dict mapping `UUID → { builder, stats, messages, embeddings, timestamp }`. TTL-based eviction (default 1 hour). Global singleton `analysis_store`.

### `mcp_server/server.py`

FastMCP server. Each tool is an async function making an HTTP call to the FastAPI service via `httpx`. No business logic — all intelligence lives in the API and pipeline.

### `archive/graph_builder.py`

**Ignore.** Legacy knowledge graph builder, not connected to anything.

---

## API Endpoints

| Method | Path                        | Description                                        |
| ------ | --------------------------- | -------------------------------------------------- |
| POST   | `/analyse`                  | Upload file, run pipeline, return UUID + stats     |
| GET    | `/graph/{id}`               | Full graph metadata for a stored analysis          |
| GET    | `/graph/{id}/people`        | Influence report — participants ranked by PageRank |
| GET    | `/graph/{id}/topics`        | Extracted topics                                   |
| GET    | `/graph/{id}/communities`   | Community groupings and membership                 |
| GET    | `/graph/{id}/visualisation` | Serve the generated PyVis HTML graph               |
| POST   | `/graph/{id}/query`         | Semantic search — returns ranked message chunks    |
| DELETE | `/graph/{id}`               | Remove a stored analysis                           |

---

## MCP Tools

| Tool                 | Maps to API endpoint          | Description                                              |
| -------------------- | ----------------------------- | -------------------------------------------------------- |
| `analyse_chat`       | `POST /analyse`               | Upload file, returns analysis ID + summary               |
| `get_influencers`    | `GET /graph/{id}/people`      | Ranked influence report                                  |
| `get_communities`    | `GET /graph/{id}/communities` | Community groupings and key members                      |
| `get_topics`         | `GET /graph/{id}/topics`      | Extracted topics                                         |
| `get_person_network` | `GET /graph/{id}/people`      | Connections and metrics for a specific person            |
| `query_chat`         | `POST /graph/{id}/query`      | Semantic search — returns ranked relevant message chunks |

---



---

## Local Development

### Tooling

- `uv` — Unified Python tool for virtual environments and dependency management.
- `just` — Command runner to manage API, frontend, and MCP processes.

### Commands

```bash
just install   # uv venv + uv pip install + npm install
just api       # Start FastAPI backend
just frontend  # Start Vite development server
just inspect   # Start MCP Inspector
just test      # Run all tests
just clean     # Clean up temporary files
```

---

## Node Types in Graph

| Type      | Shape   | Color   | Represents                        |
| --------- | ------- | ------- | --------------------------------- |
| `chat`    | box     | #FF6B6B | Root node, the chat group itself  |
| `person`  | dot     | #4ECDC4 | A participant (size = influence)  |
| `message` | ellipse | #A0D2EB | An individual message             |
| `topic`   | diamond | #FFD93D | A KeyBERT-extracted keyword/theme |

### Node ID conventions (critical for frontend integration)

| Node type | ID format         | Example     |
| --------- | ----------------- | ----------- |
| person    | `p_{sender_name}` | `p_Alice`   |
| message   | `m_{message_id}`  | `m_42`      |
| topic     | raw topic string  | `database`  |
| chat      | raw chat name     | `team_chat` |

---

## Edge Types in Graph

| Relationship     | Direction         | Meaning                                     |
| ---------------- | ----------------- | ------------------------------------------- |
| `SENT`           | person → message  | Person authored the message                 |
| `PART_OF`        | message → chat    | Message belongs to the chat                 |
| `REPLIED_TO`     | message → message | Explicit or inferred reply chain            |
| `MENTIONED`      | message → person  | @mention inside message content             |
| `REACTED_TO`     | person → message  | Person reacted to a message                 |
| `INTERACTS_WITH` | person → person   | Inferred from replies and mentions (hidden) |
| `DISCUSSED`      | chat → topic      | Chat contains this topic                    |
| `MENTIONS_TOPIC` | message → topic   | Message text matches topic keyword          |

---

## Metrics

| Metric             | Algorithm              | Stored on   | Meaning                          |
| ------------------ | ---------------------- | ----------- | -------------------------------- |
| `pagerank`         | NetworkX PageRank      | person node | Overall influence in the network |
| `betweenness`      | Betweenness Centrality | person node | Acts as bridge between groups    |
| `message_count`    | Count                  | person node | Raw activity volume              |
| `replies_received` | Count                  | person node | How often others respond to them |
| `community`        | Greedy Modularity      | person node | Which cluster they belong to     |

**Badge thresholds (fixed constants):**

- `INFLUENCER` — PageRank > 0.12
- `INFO_BROKER` — Betweenness > 0.15

---

## Dependencies

### Required

```
networkx
pyvis
pydantic
keybert
sentence-transformers
numpy
fastapi
uvicorn
python-multipart
mcp
httpx
pytest
```

### Not needed

```
groq          # removed — no LLM generation step
instructor    # removed — no structured LLM outputs
python-dotenv # removed — no API keys required anywhere
```

---

## Tests

| File                      | Status   | Coverage                                  |
| ------------------------- | -------- | ----------------------------------------- |
| `test_social_pipeline.py` | Complete | 47 tests — full pipeline, KeyBERT stubbed |
| `test_chat_parser.py`     | Complete | WhatsApp, Telegram, Slack ingestion       |
| `test_api.py`             | Complete | Endpoint tests and semantic retrieval     |
| `large_social_test.py`    | Manual   | 75-message integration run, not in CI     |
| `llm_test.py`             | Legacy   | Tests removed features — delete           |

```bash
cd Phase2
pytest tests/ -v
```

---

## Known Limitations

1. **Topic-to-message matching is exact.** KeyBERT bigrams only connect to messages containing that exact phrase. Single-word topics match more reliably.
2. **Badge thresholds are fixed constants.** Dynamic percentile-based thresholds would be more robust across different chat sizes.
3. **Analysis store is in-memory.** Restarting the API loses all stored analyses. Persistent storage (SQLite or Redis) needed before any production deployment.
4. **No nested reply visualisation.** The graph shows direct reply edges but complex nested threads are hard to follow visually.
5. **Frontend has unresolved issues (Phase 5):**
   - Debug log panel hardcoded in `App.jsx` — remove before production
   - Node ID prefix convention (`p_`, `m_`) is implicit between backend and frontend — must be formalised
   - Two competing graph renderers: `react-force-graph-2d` in the UI and PyVis for `/visualisation` — decide one owner
   - `window.location.reload()` used for reset — replace with clean React state reset
   - `App.css` contains `/* DIAGNOSTIC PURPLE */` development comment — remove

---

## Environment Variables

No environment variables or API keys are required at any phase. The entire stack runs locally.
