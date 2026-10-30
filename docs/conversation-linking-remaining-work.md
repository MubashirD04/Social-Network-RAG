# Conversation-linking layer — remaining work

Tracks what's left on the inferred-conversation-linking feature (see `docs/context.md`'s `src/conversation_linker.py` / `src/coref_resolver.py` sections for what's built and why). Intended as input for scoping specs on the next phase of work.

---

## Deployment status

The web app runs in the browser and deploys to Vercel as a static site, using Tier 1 only (no classifier mode, no coref). Tier 2 applies only to the local FastAPI service.

## Must-do before Tier 2 coreference resolution can be trusted

1. **Confirm the CPU-only torch pin works.** Install `requirements-coref.txt` in a clean venv and rerun an `/analyse` smoke test with `CONVERSATION_LINKING_COREF_ENABLED=true`. The `torch==2.6.0+cpu` pin hasn't been exercised end to end.
2. **Run `scripts/eval_conversation_linker.py` with `CONVERSATION_LINKING_COREF_ENABLED=true`** against real data. This is the actual gate for whether coref is worth keeping — no precision/recall number exists yet for coref specifically, only for the weighted-sum baseline and the (undertrained) classifier.
3. **Cold-start test with no network access.** Set `HF_HUB_OFFLINE=1`/`TRANSFORMERS_OFFLINE=1` with network disabled, and confirm both the MiniLM and (if enabled) f-coref models load from local disk with zero runtime fetch attempts.

## Must-do before the Tier 2 classifier can be trusted

4. **Train on real Slack export(s), not just the synthetic fixture.** Current model has only 5 positive examples inside the candidate window; flagged everywhere in the code/docs as a pipeline smoke test, not a real result.
5. **Proper held-out evaluation.** Training and eval currently reuse the same data (no train/test split), so the classifier's reported numbers are optimistic by construction. Needs either multiple independent exports (train on some, eval on others) or k-fold CV once there's enough data.

## Decisions pending on measurement

6. **Weighted-sum vs. classifier as the shipped default** — no apples-to-apples comparison exists yet (classifier's numbers aren't from held-out data).
7. **Tier 1 weight/threshold tuning** — current defaults were hand-calibrated against one smoke-test case, not systematically swept against the eval script's precision/recall output.

## Integration gaps (fixed 2026-09-11)

8. ~~Frontend has no visibility into the new inferred-link layer.~~ **Fixed.** Each search result in `App.jsx` now shows a "Linked context" section (`.linked-context`) listing the messages `conversation_linker` connected it to, styled with the same dashed muted-blue-gray language as the graph's existing `inferred` edges, clickable to jump to that node. Verified in a real browser via Playwright against the live dev servers, not just a successful build — screenshot confirmed the section renders correctly under real search results (e.g. Diana Kowalski's coffee-machine message showing Frank Silva's reply as linked context).
9. ~~MCP server doesn't expose the new endpoint.~~ **Fixed.** Added `get_inferred_links(analysis_id)` to `mcp_server/server.py`, wrapping `GET /graph/{id}/inferred-links`, following the same pattern as the other tools. (Note: `linked_context` was already reachable via the existing `query_chat` tool, which passes through the raw `/query` response — this new tool adds the full edge list, which wasn't reachable any other way.)

## Validated / not blocking

Tier 1 scoring (`ConversationLinker.score_pairs`, all four signals), the `chat_parser.py` multi-day Slack export bug fix (channel grouping + cross-day `thread_ts` resolution), the classifier's plumbing (training script, scoring mode, missing-model fallback), coref's core mechanics (separator-based message splitting, per-channel windowing, the `fastcoref.spacy_component` import bug, the `spacy.blank` vs. tagged-pipeline bug, the `transformers<5` pin), and both integration gaps above (frontend display, MCP tool) are built and tested — just the coref/classifier pieces specifically not yet validated at real-data scale.
