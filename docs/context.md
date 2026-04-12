# Project Context

## Overview

A social network analysis tool that processes group chat data into an interactive directed graph and exposes that analysis via a FastAPI service and MCP server. It identifies key influencers, information brokers, and community clusters from raw message interactions — without requiring any LLM API calls for core functionality. The MCP server allows any compatible AI model to trigger and interrogate analyses directly.

---

## Current State
 
The core pipeline, file ingestion layer (Phase 1), API layer (Phase 2), local retrieval layer (Phase 3), and MCP server (Phase 4) are all fully functional and tested. The system is ready to be explored via standard AI assistants or its dedicated API. The final remaining milestone is the web UI (Phase 5).

---

## Active File Structure

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

## Data Flow

```
Uploaded file (.txt / .json / .zip)
    │
    ▼
ChatParser.parse()                        ← Phase 1
    │
    ▼
List[Message]
    │
    ▼
SocialGraphBuilder.process_chat_data()   ← Exists now
    │
    ├── Build person, message, chat nodes
    ├── Parse reply/mention/reaction edges (regex)
    ├── Extract topics via KeyBERT (local)
    ├── Calculate PageRank + betweenness centrality
    ├── Detect communities (greedy modularity)
    └── Assign badges (INFLUENCER, INFO_BROKER)
    │
    ▼
nx.DiGraph (stored by UUID in api/store.py)
    │
    ├── GET /graph/{id}/people       → influence report
    ├── GET /graph/{id}/topics       → topic list
    ├── GET /graph/{id}/communities  → community groupings
    ├── GET /graph/{id}/visualisation→ HTML graph
    └── POST /graph/{id}/query       → ranked message chunks (Phase 3, retrieval only)
    │
    ▼
MCP tools (Phase 4) — thin wrappers around API calls
```

---

## Core Classes and Responsibilities

### `src/social_models.py`

Defines the normalised message schema. All parsers must produce this. Shared across the pipeline, API, and MCP layers.

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

Single public method: `parse(filepath) -> List[Message]`. Auto-detects format. Each supported format has its own private parser method. Handles WhatsApp, Telegram, and Slack.

### `api/main.py`

FastAPI application. Imports routes from `api/routes/`. Reuses Pydantic models from `src/social_models.py` as response schemas.

### `api/store.py`

In-memory dict mapping `UUID → SocialGraphBuilder instance`. Handles TTL expiry so old analyses don't accumulate indefinitely.

### `mcp_server/server.py`

MCP server using the Anthropic Python SDK. Each tool makes an HTTP call to the FastAPI service. No business logic here.

### `src/llm_service.py`

Handles all local intelligence tasks. Uses `sentence-transformers` for semantic embedding generation and `KeyBERT` for topic extraction. Decoupled from any external LLM APIs.

- `generate_embeddings(texts)` -> numpy matrix
- `extract_topics(messages)` -> List of key phrases
- `get_top_k_similar(query, embeddings)` -> Ranked message indices

### `archive/graph_builder.py`

**Ignore.** Legacy knowledge graph builder from an earlier phase.

---

## API Endpoints _(Phase 2)_

| Method | Path                        | Description                                           |
| ------ | --------------------------- | ----------------------------------------------------- |
| POST   | `/analyse`                  | Upload a chat file, run pipeline, return UUID + stats |
| GET    | `/graph/{id}`               | Full graph metadata for a stored analysis             |
| GET    | `/graph/{id}/people`        | Influence report — participants ranked by PageRank    |
| GET    | `/graph/{id}/topics`        | Extracted topics                                      |
| GET    | `/graph/{id}/communities`   | Community groupings and membership                    |
| GET    | `/graph/{id}/visualisation` | Serve the generated HTML graph file                   |
| POST   | `/graph/{id}/query`         | RAG query — stubbed until Phase 3                     |
| DELETE | `/graph/{id}`               | Remove a stored analysis                              |

---

## MCP Tools _(Phase 4)_

| Tool                 | Maps to API endpoint          | Description                                              |
| -------------------- | ----------------------------- | -------------------------------------------------------- |
| `analyse_chat`       | `POST /analyse`               | Upload file, returns analysis ID + summary               |
| `get_influencers`    | `GET /graph/{id}/people`      | Ranked influence report                                  |
| `get_communities`    | `GET /graph/{id}/communities` | Community groupings and key members                      |
| `get_topics`         | `GET /graph/{id}/topics`      | Extracted topics                                         |
| `get_person_network` | `GET /graph/{id}/people`      | Connections and metrics for a specific person            |
| `query_chat`         | `POST /graph/{id}/query`      | Semantic search — returns ranked relevant message chunks |

---

## Node Types in Graph

| Type      | Shape   | Color   | Represents                        |
| --------- | ------- | ------- | --------------------------------- |
| `chat`    | box     | #FF6B6B | Root node, the chat group itself  |
| `person`  | dot     | #4ECDC4 | A participant (size = influence)  |
| `message` | ellipse | #A0D2EB | An individual message             |
| `topic`   | diamond | #FFD93D | A KeyBERT-extracted keyword/theme |

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

**Badge thresholds (current, fixed):**

- `INFLUENCER` — PageRank > 0.12
- `INFO_BROKER` — Betweenness > 0.15

---

## Dependencies

### Required (pipeline — exists now)

```
networkx
pyvis
pydantic
keybert
sentence-transformers
```

### Required (API — Phase 2)

```
fastapi
uvicorn
python-multipart    # file upload support
```

### Required (retrieval — Phase 3)

```
sentence-transformers   # already installed, used by KeyBERT
numpy                   # cosine similarity over embeddings
```

### Required (MCP — Phase 4)

```
mcp                 # Anthropic MCP Python SDK
httpx               # MCP server calling the FastAPI service
```

### Not needed

```
groq                # removed — no LLM generation step in the pipeline
instructor          # removed — no structured LLM outputs needed
python-dotenv       # removed — no API keys required anywhere
```

---

## Tests

| File                   | Status   | Coverage                                          |
| ---------------------- | -------- | ------------------------------------------------- |
| `test_chat_parser.py`  | Complete | WhatsApp, Telegram, Slack ingestion tests          |
| `test_api.py`          | Complete | Endpoint tests and semantic retrieval tests       |
| `large_social_test.py` | Complete | 75-message integration run                        |

Run current tests:

```bash
cd Phase2
pytest tests/test_social_pipeline.py -v
```

---

## Known Limitations

1. **Topic-to-message matching is exact.** KeyBERT bigrams only connect to messages containing that exact phrase. Single-word topics match more reliably.
2. **Badge thresholds are fixed constants.** Dynamic percentile-based thresholds would be more robust across chat sizes.
3. **Analysis store is in-memory.** Restarting the API loses all stored analyses. Persistent storage (SQLite or Redis) needed before production.
4. **No nested replies in visualization.** The graph shows direct reply edges but complex nested threads can be hard to follow visually.


---

## Environment Variables

No environment variables or API keys are required at any phase. The entire stack runs locally.
