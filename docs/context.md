# Project Context

## Overview

A social network analysis tool that processes group chat data into an interactive directed graph and exposes that analysis via a FastAPI service and MCP server. Identifies key influencers, information brokers, and community clusters from raw message interactions — without requiring any external API calls at any stage. The MCP server allows any compatible AI model to trigger and interrogate analyses directly.

---

## Current State

The core pipeline, file ingestion (Phase 1), API layer (Phase 2), retrieval layer (Phase 3), MCP server (Phase 4), and web UI (Phase 5) are all functional and tested — including a browser-driven Playwright verification of the search flow (upload → query → linked-context display), not just a build check. The system is ready to be explored via Claude Desktop, the MCP Inspector, the web UI, or direct API calls.

An inferred-conversation-linking layer (Tier 1: weighted-sum scoring; Tier 2: an optional trained-classifier scoring mode and optional coreference-resolution preprocessing) sits on top of the retrieval layer — see `src/conversation_linker.py` and `src/coref_resolver.py` below, and `docs/conversation-linking-remaining-work.md` for what's left before Tier 2 specifically can be trusted in production.

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
│   │   ├── conversation_linker.py    # Inferred-link layer for the retrieval layer (Tier 1 + Tier 2 classifier mode)
│   │   └── coref_resolver.py         # Optional Tier 2: cross-message coreference resolution before embedding
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
│   ├── frontend/                     # Phase 5 — React + Vite, functional and tested (see Known Limitations)
│   │   ├── src/
│   │   │   ├── App.jsx               # Main component: upload, graph, search + linked-context display
│   │   │   ├── App.css
│   │   │   ├── index.css
│   │   │   ├── main.jsx
│   │   │   ├── NetworkBackground.jsx # Landing-page animated background
│   │   │   └── CodeExample.jsx       # Landing-page code snippet display
│   │   ├── public/
│   │   ├── package.json
│   │   └── vite.config.js            # Dev proxy: /analyse, /graph → localhost:8000
│   ├── tests/
│   │   ├── conftest.py                    # Stubs fastembed/yake for fast, offline tests
│   │   ├── test_social_graph_builder.py   # Pipeline unit tests (nodes, edges, communities, topics)
│   │   ├── test_chat_parser.py            # Parser tests per format
│   │   ├── test_api.py                    # Endpoint + retrieval tests
│   │   ├── test_mcp_server.py              # MCP tool tests (httpx mocked, no live API needed)
│   │   ├── test_conversation_linker.py    # Inferred-link scoring tests (synthetic sequences, classifier mode)
│   │   ├── test_coref_resolver.py         # Coref channel-grouping/windowing tests, real "not installed" fallback
│   │   └── large_social_test.py           # Manual 75-message integration run, not in CI
│   ├── scripts/
│   │   ├── eval_conversation_linker.py             # Manual Slack thread_ts precision/recall eval (`just eval-linker`)
│   │   ├── build_synthetic_slack_export.py         # Generates a realistic Slack export .zip for the eval above (`just build-slack-fixture`)
│   │   └── train_conversation_linker_classifier.py # Trains the Tier 2 classifier from a Slack export (`just train-linker-classifier`)
│   ├── models/                        # Trained classifier artifacts — gitignored, regenerate via the script above
│   ├── requirements.txt
│   ├── requirements-coref.txt         # Optional Tier 2 extra — fastcoref (torch + transformers), not installed by default
│   └── social_demo.py
├── docs/
│   ├── context.md                            # This file — technical reference
│   ├── data-export-guide.md                  # How to export WhatsApp/Telegram/Slack chats for upload
│   └── conversation-linking-remaining-work.md # What's left on the inferred-link layer, for scoping specs
├── scripts/
│   └── start-mcp.sh                  # Starts API + MCP Inspector
├── test_data/                        # Optional local sample chat exports (gitignored, not present by default — the frontend's upload zone hints at it, but it's not required)
├── output/                           # Generated HTML + GraphML/synthetic fixtures (gitignored)
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
    ├── Infer lexical-continuity connections for unthreaded messages
    ├── Extract topics via YAKE (local)
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
    channel: Optional[str] = None       # Slack channel name; None for single-conversation formats
```

`channel` scopes `_infer_lexical_continuity` (see below) to messages from the same room, so two unrelated channels never get wired together just for sharing vocabulary.

### `src/social_graph_builder.py`

The entire analysis pipeline. No external API dependencies. Complete and tested.

Key methods:

- `process_chat_data(messages, chat_name)` — async, builds full graph, returns stats dict
- `_infer_lexical_continuity(messages)` — connects unthreaded messages that share distinctive wording (see below)
- `get_topics()` — extracted topics with the messages that mention each one
- `regenerate_topics(top_n)` — re-runs topic extraction at a new count (5-10) without re-parsing the file
- `_calculate_stats()` — computes PageRank, betweenness, activity counts, badges
- `_detect_communities(graph, nodes)` — greedy modularity on undirected interaction graph
- `get_influence_report()` — list of per-person metric dicts sorted by PageRank
- `visualize(output_file)` — PyVis HTML with injected interactive sidebar
- `save_graph(filepath)` — writes GraphML

#### Inferred vs. confirmed connections

Most real chat isn't formally threaded — people just reply in the channel. `_infer_lexical_continuity` runs after the main per-message pass and connects a message with no explicit `reply_to` or opening `@mention` to the nearest prior message (within `CONTINUITY_LOOKBACK_MESSAGES` messages / `CONTINUITY_LOOKBACK_WINDOW` = 15 minutes, same `channel`, different sender) that shares a distinctive word (4+ letters, filtered against a stopword list and participant names).

This is a guess, not a fact, so it's kept both visually and numerically separate from confirmed connections:

- The `REPLIED_TO` edge it creates is tagged `inferred: true` (confirmed replies/mention-inferences are not).
- The `INTERACTS_WITH` person-to-person edge it creates carries `weight=0` with the guessed strength recorded in a separate `inferred_weight` field instead — `_calculate_stats` only sums `weight`, so PageRank, betweenness, community detection, and `replies_received` are computed purely from confirmed activity.
- The frontend renders these edges dashed and muted, and lets a viewer toggle them off entirely (`showInferredLinks` in `App.jsx`) without affecting any score shown elsewhere in the UI.

### `src/conversation_linker.py`

A second, separate inferred-link layer — richer than `_infer_lexical_continuity` above, and built for the retrieval layer rather than the visualization graph. `_infer_lexical_continuity` never touches this module and vice versa; they solve the same underlying gap (untagged messages that are conversationally related) for two different consumers with two different levels of signal.

`ConversationLinker.score_pairs(messages, embeddings)` scores candidate pairs of messages that have no `reply_to` set (real Slack `thread_ts` or the WhatsApp parser's own adjacency heuristic both count as "already linked" and are skipped as inference sources — explicit/prior signal always wins) using a weighted combination of four signals:

- **Semantic similarity** — cosine similarity between MiniLM embeddings. Reuses the embeddings already computed by `retrieval_service.generate_embeddings` in `POST /analyse` (index-aligned with `messages`) rather than loading a second model — the project already bakes `sentence-transformers/all-MiniLM-L6-v2` into the image via `fastembed` (ONNX Runtime, no PyTorch); adding the `sentence-transformers` package on top would mean shipping PyTorch for a model that's already loaded.
- **Temporal proximity** — exponential decay over the time gap, with a separate decay constant for Slack (`CONVERSATION_LINKING_SLACK_DECAY_MINUTES`, default 12) vs. WhatsApp/Telegram (`CONVERSATION_LINKING_DEFAULT_DECAY_MINUTES`, default 6), keyed on whether the message has a `channel`.
- **Speaker turn-taking** — boosts pairs where the two speakers have been rapidly alternating in the preceding `CONVERSATION_LINKING_TURN_TAKING_WINDOW` messages.
- **Lexical overlap** — Jaccard similarity between per-message YAKE keyword sets (a new, small per-message extraction — distinct from `extract_topics`' whole-chat extraction).

Weights, threshold, and all window sizes are config (`LinkerConfig.from_env()`, env-prefixed `CONVERSATION_LINKING_*`), not hardcoded. The whole layer is toggleable off via `CONVERSATION_LINKING_ENABLED=false` — `score_pairs` then returns `[]` immediately and nothing downstream changes shape.

Scoring is scoped per-channel and to a bounded lookback window (`CONVERSATION_LINKING_CANDIDATE_WINDOW_MESSAGES` / `_MINUTES`), never an all-pairs comparison over the whole history.

Output is a flat `List[InferredLink]` (`message_id_a`, `message_id_b`, `score`, `signals`) — stored alongside `messages`/`embeddings` in `analysis_store` and exposed both directly (`GET /graph/{id}/inferred-links`) and folded into `POST /graph/{id}/query` results as `linked_context` on each hit, so a query can surface a barely-similar-to-the-query message that sits right next to a strong hit.

`scripts/eval_conversation_linker.py` is a standalone, manually-run eval tool: strips `reply_to` from a Slack export's already-threaded messages, re-runs the scorer as if they were untagged, and reports precision/recall against the real threads it just erased — the only ground truth available for this heuristic (WhatsApp has none). Not part of the pytest suite (loads the real embedding model), same convention as `social_demo.py`.

`scripts/build_synthetic_slack_export.py` (`just build-slack-fixture`) generates a Slack export `.zip` to run that eval against, matching Slack's real export shape: one JSON file per channel *per day* nested under a per-channel folder, `ts`/`thread_ts`/`reactions`/`client_msg_id` matching Slack's actual message-object fields. Two of its threads deliberately have replies landing on a different calendar day than their root, to exercise the cross-day `thread_ts` resolution fix in `chat_parser.py`. Tier 1 baseline against it (default weighted-sum weights/threshold): ~0.20 precision / ~0.18 recall — most of what the metric counts as "false positives" are actually correct inferences on messages that were never threaded in the source data at all (so they can't appear in the thread_ts ground truth no matter how right they are); the real misses are short, low-content replies ("looking now", "nice catch") that don't carry enough standalone semantic signal for MiniLM — precisely the gap the coreference step below targets.

#### Tier 2: trained classifier

`ConversationLinker.iter_candidates(messages, embeddings)` is the weighted-sum's candidate generation split out from scoring — it yields every candidate pair within the window as a `Candidate(message_id_a, message_id_b, features)`, unfiltered by any threshold, so both `score_pairs` and the training script below share exactly one definition of "which pairs are even in play." `FEATURE_ORDER = ("semantic", "temporal", "turn_taking", "lexical")` fixes the column order a trained model and the runtime scorer both use, so they can never disagree about which weight goes with which signal.

`LinkerConfig.scoring_mode` (`CONVERSATION_LINKING_SCORING_MODE`) selects `"weighted_sum"` (default, hand-tuned, needs nothing extra) or `"classifier"` (loads a trained model from `CONVERSATION_LINKING_MODEL_PATH`, default `Phase2/models/conversation_linker_classifier.joblib`, and scores via `predict_proba` against `CONVERSATION_LINKING_CLASSIFIER_THRESHOLD`, default 0.5). If the model file is missing or fails to load, `ConversationLinker` logs a warning and falls back to `weighted_sum` for that instance (`linker.using_classifier` reports which mode is actually active) — requesting classifier mode can never crash the pipeline.

`scripts/train_conversation_linker_classifier.py` (`just train-linker-classifier <export.zip>`) builds a labeled dataset the same way the eval script builds ground truth — strip `reply_to` from a Slack export, walk `iter_candidates` over the stripped data, label each candidate 1 if it matches a real `thread_ts` pair and 0 otherwise — and fits a `sklearn.linear_model.LogisticRegression(class_weight="balanced")` (chosen for being genuinely negligible footprint, not for accuracy; a GBT is a drop-in alternative if more signal is ever needed). Saves `{model, feature_order, trained_on, n_samples, n_positive}` via `joblib`. **Caveat that matters**: the bundled synthetic fixture only has 5 ground-truth pairs that actually fall inside the candidate window (most of its 11 `thread_ts` pairs are far enough apart in time to never become a candidate at all, by the same windowing that keeps this from being an all-pairs comparison) — a classifier trained on 5 positives is a pipeline smoke test, not a trustworthy model; the training script prints this caution whenever positives are under 20. `Phase2/models/` is gitignored — trained models are a build artifact, not something to commit.

#### Tier 2: coreference resolution (`src/coref_resolver.py`)

Optional and **off by default** — the one piece of this feature that pulls in PyTorch + `transformers` (via `fastcoref`'s `FCoref` model, `biu-nlp/f-coref` on the Hugging Face Hub), which the rest of this project has deliberately avoided (see the `sentence-transformers` note above). Not in `requirements.txt`; lives in `Phase2/requirements-coref.txt` instead, and the default Docker build never installs it — see the Dockerfile's `runtime-coref` stage (`docker build --target runtime-coref`), which is not the default build target.

`CorefResolver` wraps fastcoref's spaCy pipeline component: `spacy.load("en_core_web_sm", disable=["parser", "ner", "lemmatizer"])` + `nlp.add_pipe("fastcoref", config={"device": "cpu"})`. **`spacy.blank("en")` does not work here** — fastcoref's `resolve_text=True` only substitutes a mention if some span in its cluster has a `NOUN`/`PROPN` `token.pos_`, and a blank pipeline never runs a tagger, so `pos_` is always empty. This was caught by actually running it: the coref model found correct clusters either way, but `resolved_text` was silently identical to the input every time under `spacy.blank`, and started resolving correctly the moment `en_core_web_sm` (~15MB, real tagger) was used instead. `en_core_web_sm` needs its own download step (`python -m spacy download en_core_web_sm`), separate from `pip install`.

`resolve_messages_by_channel(messages)` groups messages by channel and resolves them in bounded, non-overlapping chunks (`CONVERSATION_LINKING_COREF_WINDOW_MESSAGES`, default 20 messages) — never the whole channel history at once, same "bounded, never all-pairs" principle as the candidate window above — so a short reply like "yeah I agree with that" gets a chance to resolve "that" against something earlier in the same window before being embedded. Messages are joined with an inert separator string and resolved as one document (via fastcoref's own `resolve_text=True` / `doc._.resolved_text`) so pronouns can resolve across message boundaries, then split back apart on that same separator. Verified end to end: `"Alice Chen posted the new schema migration"` / `"She said it was ready for review"` resolves the second message to `"Alice Chen said the new schema migration was ready for review"` before embedding.

`get_embedding_texts(messages)` is the one call site `POST /analyse`, the eval script, and the training script all use instead of reading `.content` directly — returns original content unchanged unless `CONVERSATION_LINKING_COREF_ENABLED=true`, and even then falls back to original content if fastcoref isn't installed or fails to load (never raises). `message.content` itself, YAKE keyword extraction, and everything a viewer sees always use the original text — coreference resolution only ever changes what gets embedded.

**`transformers<5` is a required, verified pin** in `requirements-coref.txt`, not defensive caution: fastcoref 2.1.6 (its latest release, as of writing) crashes loading its model against `transformers` 5.x (`AttributeError: 'FCorefModel' object has no attribute 'all_tied_weights_keys'` — a renamed internal in `transformers`' newer model-loading code that fastcoref's pinned-loose `transformers>=4.11.3` requirement doesn't guard against). Confirmed by installing both and reproducing the crash, then confirming the 4.x line loads and resolves correctly.

**Measured, not estimated** (real `pip install` + real model load + real inference, in an isolated venv — see the size/RAM discussion this was researched for): the full dependency closure (torch CPU, transformers, spacy, fastcoref, and their transitive deps including `datasets`/`pyarrow`/`pandas`) installs to **~1.2GB**; `numpy`/`scipy`/`networkx` within that are already required by `requirements.txt` so don't count as incremental. The `biu-nlp/f-coref` model weights are **364.8MB** (confirmed via the HF Hub API), `en_core_web_sm` is **~15MB**. Net incremental Docker image size: **roughly 1.5GB**. Peak RSS for a single process actually loading the pipeline and resolving a small multi-message batch: **~800MB** (measured via `resource.getrusage`; import overhead alone — torch + transformers + spacy, before any model loads — accounts for ~450MB of that). Both numbers were measured on macOS/ARM; Linux/x86_64 in the actual deployment target should be the same order of magnitude, not verified identical.

The Docker `runtime-coref` stage's build steps mirror exactly what was measured working in the isolated venv (same imports, same `spacy.load`/`add_pipe` calls, same `transformers<5` pin) but the Dockerfile itself has not been build-tested end to end (a real `docker build` would take a while to pull ~1.5GB of layers) — treat the stage as unverified until someone runs it for real, even though its logic matches verified-working code.

### `src/chat_parser.py`

Single public method: `parse_file(filepath) -> List[Message]`. Auto-detects format from file extension.

Private parsers:

- `parse_whatsapp(filepath)` — `.txt`, handles both 12hr and 24hr date formats
- `parse_telegram(filepath)` — standard Telegram Desktop `.json` export
- `parse_slack(filepath)` — `.zip` export. Real Slack exports nest one JSON file per *day* under a per-channel folder (`<channel>/YYYY-MM-DD.json`); files are grouped by channel (folder name, or the file stem for a flat single-file-per-channel zip) before parsing, and `thread_ts` is resolved against a ts→id map spanning the whole channel — not per-file — so a reply on day 2 still resolves to a root posted on day 1. Maps user IDs via `users.json`.

### `src/llm_service.py`

Local intelligence only. No external API calls, no API key required.

- `generate_embeddings(texts)` → `np.ndarray` — fastembed (ONNX Runtime, no PyTorch) embeddings
- `get_top_k_similar(query, embeddings, k)` → ranked `(index, score)` tuples — cosine similarity
- `extract_topics(messages, top_n)` → `List[str]` — YAKE extraction

Exports a module-level singleton: `retrieval_service = LLMService()` used by the API routes.

### `api/store.py`

In-memory dict mapping `UUID → { builder, stats, messages, embeddings, inferred_links, timestamp }`. TTL-based eviction (default 1 hour). Global singleton `analysis_store`.

### `mcp_server/server.py`

FastMCP server. Each tool is an async function making an HTTP call to the FastAPI service via `httpx`. No business logic — all intelligence lives in the API and pipeline.

---

## API Endpoints

| Method | Path                        | Description                                        |
| ------ | --------------------------- | -------------------------------------------------- |
| POST   | `/analyse`                  | Upload file, run pipeline, return UUID + stats     |
| GET    | `/graph/{id}`               | Full graph metadata for a stored analysis          |
| GET    | `/graph/{id}/people`        | Influence report — participants ranked by PageRank |
| GET    | `/graph/{id}/topics`        | Extracted topics                                   |
| POST   | `/graph/{id}/topics`        | Re-extract topics at a new count (5-10), returns full updated graph |
| GET    | `/graph/{id}/communities`   | Community groupings and membership                 |
| GET    | `/graph/{id}/data`          | Raw nodes/edges for the React frontend's graph      |
| GET    | `/graph/{id}/visualisation` | Serve the generated standalone PyVis HTML export   |
| POST   | `/graph/{id}/query`         | Semantic search — returns ranked message chunks, each with a `linked_context` array of inferred-linked neighbors (toggle via `include_linked_context`) |
| GET    | `/graph/{id}/inferred-links`| Raw inferred-link edge list (`message_id_a`, `message_id_b`, `score`, `signals`) |
| DELETE | `/graph/{id}`               | Remove a stored analysis                           |

---

## MCP Tools

| Tool                 | Maps to API endpoint          | Description                                              |
| -------------------- | ----------------------------- | -------------------------------------------------------- |
| `analyse_chat`       | `POST /analyse`               | Upload file, returns analysis ID + summary               |
| `get_influencers`    | `GET /graph/{id}/people`      | Ranked influence report                                  |
| `get_communities`    | `GET /graph/{id}/communities` | Community groupings and key members                      |
| `get_topics`         | `GET /graph/{id}/topics`      | Extracted topics                                         |
| `get_person_network` | `GET /graph/{id}/people`      | Connections and metrics for a specific person, matched by their display name (the `label` field, not the internal `p_`-prefixed `name`) |
| `query_chat`         | `POST /graph/{id}/query`      | Semantic search — returns ranked relevant message chunks, each with `linked_context` |
| `get_inferred_links` | `GET /graph/{id}/inferred-links` | Full inferred conversational-link edge list |

---

## Language and Stack Decision

The entire project is Python. This was an explicit decision — the analysis pipeline depends on NetworkX, YAKE, and PyVis, none of which have Go equivalents. Moving the API layer to Go would mean running it as a proxy in front of a Python service, adding complexity with no real benefit. The bottleneck will always be the analysis pipeline itself, not the HTTP layer.

| Layer         | Library                        | Reason                                            |
| ------------- | ------------------------------- | -------------------------------------------------- |
| API           | FastAPI                        | Async, auto OpenAPI docs, Pydantic schemas reused |
| Server        | uvicorn                        | ASGI, production-grade, pairs with FastAPI        |
| MCP server    | mcp (Anthropic SDK)            | Official Python SDK, straightforward to build     |
| Schemas       | Pydantic                       | Already used throughout, shared across all layers |
| Analysis      | NetworkX, YAKE                 | Existing pipeline, unchanged                      |
| RAG retrieval | fastembed (ONNX, no PyTorch)   | Local embeddings, no API key, no torch dependency for the core pipeline |

## What to Leave Alone

- `social_graph_builder.py` — stable core pipeline; don't add LLM calls back into it.
- `social_models.py` — the `Message` schema is the contract between the parser and the rest of the pipeline; keep it minimal.
- The fastembed-not-sentence-transformers choice in `llm_service.py`/`conversation_linker.py` — deliberate, see the dependency-footprint rationale in `src/conversation_linker.py` below. Don't add `sentence-transformers` as a "simpler" alternative without a new reason.

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
just start     # Start API + frontend together in the background
just stop      # Stop processes started by `just start`
just inspect   # Start MCP Inspector
just test      # Run all tests
just clean     # Clean up temporary files
just build-slack-fixture              # Generate a synthetic Slack export for eval-linker
just eval-linker <slack.zip>          # Precision/recall of the inferred-link scorer against a Slack export's thread_ts
just train-linker-classifier <zip>    # Train the Tier 2 classifier scoring mode from a Slack export
```

---

## Node Types in Graph

| Type      | Shape   | Color                          | Represents                        |
| --------- | ------- | ------------------------------ | ---------------------------------- |
| `chat`    | box     | #FF6B6B                        | Root node, the chat group itself   |
| `person`  | dot     | community-colored (gray if none) | A participant (size = influence) |
| `message` | ellipse | #A0D2EB                        | An individual message              |
| `topic`   | diamond | #FFD93D                        | A YAKE-extracted keyword/theme, 5-10 shown at once (viewer-adjustable) |

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
| `REPLIED_TO`     | message → message | Explicit reply, an @mention-opening inference, or lexical continuity (shared wording, no formal thread — tagged `inferred: true`) |
| `MENTIONED`      | message → person  | @mention inside message content             |
| `REACTED_TO`     | person → message  | Person reacted to a message                 |
| `INTERACTS_WITH` | person → person   | Real replies/mentions (`weight`) plus, separately, lexical-continuity guesses (`inferred_weight`) — only `weight` counts toward scores |
| `DISCUSSED`      | chat → topic      | Chat contains this topic                    |
| `MENTIONS_TOPIC` | message → topic   | Message text matches topic keyword          |

---

## Metrics

| Metric             | Algorithm              | Stored on   | Meaning                          |
| ------------------ | ---------------------- | ----------- | -------------------------------- |
| `pagerank`         | NetworkX PageRank      | person node | Overall influence in the network |
| `betweenness`      | Betweenness Centrality | person node | Acts as bridge between groups    |
| `message_count`    | Count                  | person node | Raw activity volume              |
| `replies_received` | Count                  | person node | Confirmed replies received (excludes inferred lexical-continuity connections) |
| `community`        | Greedy Modularity      | person node | Which cluster they belong to     |

`pagerank`, `betweenness`, and `community` are all computed from the interaction graph built out of `INTERACTS_WITH` edges' `weight` field only — inferred-only connections (`inferred_weight`, no real `weight`) never enter it. See "Inferred vs. confirmed connections" above.

**Badge thresholds (per-chat, percentile-based):**

- `INFLUENCER` — PageRank above the 75th percentile of this chat's own participants
- `INFO_BROKER` — Betweenness above the 75th percentile of this chat's own participants

Computed relative to each chat's own score distribution rather than fixed constants, so badges stay meaningful whether the network has 5 people or 500; when scores are all tied, nobody clears the threshold.

---

## Dependencies

### Required

```
networkx
pyvis
pydantic
yake
fastembed
numpy
scipy         # networkx community-detection performance
fastapi
uvicorn
python-multipart
mcp<2
httpx
pytest
scikit-learn  # Tier 2 classifier scoring mode — LogisticRegression only, negligible footprint
joblib        # (de)serializes the trained classifier
```

### Optional (`requirements-coref.txt`, not installed by default)

```
--extra-index-url https://download.pytorch.org/whl/cpu
torch==2.6.0+cpu  # REQUIRED pin — plain `pip install fastcoref` resolves the full CUDA build otherwise
fastcoref
transformers<5    # fastcoref 2.1.6 crashes loading its model against transformers 5.x
spacy             # NOT tokenizer-only — fastcoref's resolve_text needs a real POS tagger
                  # (en_core_web_sm, ~15MB, via `python -m spacy download en_core_web_sm`)
```

### Not needed

```
groq          # removed — no LLM generation step
instructor    # removed — no structured LLM outputs
python-dotenv # removed — no API keys required anywhere
sentence-transformers # not added — fastembed already bakes in the same MiniLM model without PyTorch
```

---

## Tests

| File                           | Status   | Coverage                                                    |
| ------------------------------ | -------- | ------------------------------------------------------------ |
| `test_social_graph_builder.py` | Complete | Pipeline unit tests — node/edge wiring, communities, topics |
| `test_chat_parser.py`          | Complete | WhatsApp, Telegram, Slack ingestion                          |
| `test_api.py`                  | Complete | Endpoint tests and semantic retrieval                        |
| `test_mcp_server.py`           | Complete | MCP tool tests, httpx mocked — no live API needed            |
| `test_conversation_linker.py`  | Complete | Inferred-link scoring, `iter_candidates`, classifier mode (fit/fallback) |
| `test_coref_resolver.py`       | Complete | Channel grouping/windowing, real "fastcoref not installed" fallback path |
| `large_social_test.py`         | Manual   | 75-message integration run, not in CI                        |

`conftest.py` stubs `fastembed` and `yake` with deterministic fakes so the suite runs fast and without downloading real models. Real model behaviour is exercised manually via `just demo`.

```bash
cd Phase2
pytest tests/ -v
```

---

## Known Limitations

1. **Analysis store is in-memory** (`api/store.py`'s `AnalysisStore`, a process-local singleton with a 1-hour TTL). Restarting the API loses all stored analyses, and the deployed service must run as a **single instance** — multiple replicas would each hold a different, incomplete set of analyses, so requests to a stored `analysis_id` would 404 unpredictably depending which instance served them. No horizontal autoscaling until this moves to shared storage (SQLite or Redis).

Resolved since the last pass:

- **Topic-to-message matching** now matches per-word (with prefix matching for morphological variants like "design"/"designing") instead of requiring a YAKE bigram to appear as one exact phrase — see `SocialGraphBuilder.process_chat_data`'s topic-connection loop in `src/social_graph_builder.py`.
- **Badge thresholds** are now computed per-chat as the 75th percentile of that chat's own PageRank/betweenness distribution instead of fixed constants (0.12/0.15) — see `_calculate_stats` in `src/social_graph_builder.py`.
- **Nested reply visualisation**: every message node now carries `reply_depth`, `thread_root`, and `thread_size` (computed in `_compute_reply_threads`). The frontend shrinks message nodes by depth and, on click, highlights the full reply thread (dimming everything else) instead of just the one flat edge to its parent — see `App.jsx`.
- **Topic quality and volume**: `extract_topics` now excludes participant names (previously YAKE surfaced people's names as "topics" since they were the most repeated n-grams) and dedupes token-subset candidates (e.g. "design" absorbed into "database design"). Viewers can pick a topic count from 5-10 via a slider (`POST /graph/{id}/topics`, `regenerate_topics`) instead of a fixed count.
- **Unthreaded messages showing as disconnected**: real chat is rarely fully threaded, so two messages that were obviously the same back-and-forth (e.g. "is the coffee machine broken?" / "yeah, facilities is on it") previously had zero graph connection. Fixed by `_infer_lexical_continuity` (see above), scoped per-channel and to a short lookback window, with confirmed and inferred connections kept visually and numerically distinct so guesses never move influence scores.
- **Multi-day Slack exports fragmented into pseudo-channels**: `parse_slack` derived the channel from the per-file stem, which is only correct for a flat `engineering.json` — a real Slack export nests one file per channel *per day* (`engineering/2024-01-15.json`), so every day was read as its own separate "channel" and any thread whose reply landed on a different calendar day than its root silently lost that link. Fixed by grouping files by channel (folder name) before parsing and resolving `thread_ts` against a ts→id map spanning the whole channel. See `src/chat_parser.py`.

Phase 5's frontend known-issues list (debug panel, implicit node ID prefixes, competing renderers, `window.location.reload()`, the `DIAGNOSTIC PURPLE` comment) has been resolved — see `App.jsx` and `App.css`.

---

## Environment Variables

No environment variables or API keys are required for the core pipeline (file ingestion, graph analysis, retrieval, MCP) — it runs entirely locally with sensible defaults. The inferred-conversation-linking layer adds optional configuration, all with working defaults:

| Variable | Default | Purpose |
| --- | --- | --- |
| `CONVERSATION_LINKING_ENABLED` | `true` | Master toggle for the whole inferred-link layer |
| `CONVERSATION_LINKING_SCORING_MODE` | `weighted_sum` | `weighted_sum` or `classifier` (Tier 2) |
| `CONVERSATION_LINKING_SEMANTIC_WEIGHT` / `_TEMPORAL_WEIGHT` / `_TURN_TAKING_WEIGHT` / `_LEXICAL_WEIGHT` | `0.4` / `0.25` / `0.15` / `0.2` | Weighted-sum signal weights |
| `CONVERSATION_LINKING_THRESHOLD` | `0.45` | Weighted-sum link threshold |
| `CONVERSATION_LINKING_CLASSIFIER_THRESHOLD` | `0.5` | Classifier-mode link threshold |
| `CONVERSATION_LINKING_MODEL_PATH` | `Phase2/models/conversation_linker_classifier.joblib` | Trained classifier location |
| `CONVERSATION_LINKING_CANDIDATE_WINDOW_MESSAGES` / `_MINUTES` | `8` / `20.0` | Candidate-pair lookback window |
| `CONVERSATION_LINKING_SLACK_DECAY_MINUTES` / `_DEFAULT_DECAY_MINUTES` | `12.0` / `6.0` | Temporal-decay constants (Slack vs. WhatsApp/Telegram) |
| `CONVERSATION_LINKING_TURN_TAKING_WINDOW` | `4` | Messages looked at for the turn-taking signal |
| `CONVERSATION_LINKING_KEYWORDS_PER_MESSAGE` | `5` | Per-message YAKE keyword count |
| `CONVERSATION_LINKING_COREF_ENABLED` | `false` | Optional Tier 2 coreference resolution (needs `requirements-coref.txt`) |
| `CONVERSATION_LINKING_COREF_WINDOW_MESSAGES` | `20` | Coref resolution chunk size |
| `HF_HUB_OFFLINE`, `TRANSFORMERS_OFFLINE` | `1` (set in the Dockerfile) | Stop fastembed/transformers from any runtime network call once models are baked in |

Full definitions: `LinkerConfig.from_env()` in `src/conversation_linker.py`.

---

## Deployment

The app ships as a single Docker image (root `Dockerfile`, multi-stage): a Node stage builds the Vite frontend, and a `python:3.12-slim` runtime stage runs the FastAPI backend, which mounts the built `frontend/dist` as static files (`api/main.py`) — one process, one port, no separate frontend host or CORS config needed. **Build-verified**: `docker build .` → 1.29GB, container starts, `/health` returns 200, a real `/analyse` call succeeds end to end.

The `sentence-transformers/all-MiniLM-L6-v2` ONNX model is baked into the image at build time (`fastembed`'s default cache path, `/tmp/fastembed_cache`, resolved identically at build and run time since `llm_service.py` never overrides `cache_dir`), so the container needs no network access at runtime — cold starts don't re-download the model. `libgomp1` is installed explicitly since `onnxruntime` needs it and `python:slim` doesn't ship it.

**Host**: Hugging Face Spaces, Docker SDK, 16GB RAM / 2 vCPU hardware tier.

**Optional `runtime-coref` build stage**: adds Tier 2 coreference resolution (`docker build --target runtime-coref`), never built by default. Two real bugs were caught building this for the first time, both fixed: (1) appending a stage after `runtime` in the same Dockerfile makes Docker build it *by default* when no `--target` is given (last stage in the file = default target) — worked around with a trailing `FROM runtime AS default` stage so plain `docker build .` stays on the lightweight path; (2) `requirements-coref.txt` needs `--extra-index-url https://download.pytorch.org/whl/cpu` + a pinned `torch==...+cpu`, or `pip install fastcoref` silently resolves the full CUDA-enabled torch build (12.2GB image observed vs. ~1.5GB expected). See `docs/conversation-linking-remaining-work.md` for what's still unverified about this stage (a fresh build since the CPU pin, real-network-disabled cold start, coref-enabled eval numbers).

**Memory profiling finding** (see git history around `src/llm_service.py` for the fix): embedding an entire chat's messages in one `fastembed.embed()` call caused peak RSS to scale with message count and never release — independent of thread count or the ONNX Runtime CPU memory arena setting (both were profiled and ruled out as the cause). A 3,000-message chat could peak over 2GB on embeddings alone, dwarfing the graph-building cost. Fixed by chunking `generate_embeddings()` into batches of 32 with `gc.collect()` between chunks — cut peak RSS by roughly 70% (3,000-message chat: ~2.1GB → ~560MB, isolated embedding-only measurement). At the 16GB/2vCPU tier this is ample headroom either way, but the fix is what makes the app viable on much smaller hosts too, if ever moved off Spaces.

**Still true regardless of host RAM**: the single-instance constraint from the in-memory `AnalysisStore` (see Known Limitations) — don't enable autoscaling/multiple replicas without moving analysis storage out of process memory first.
