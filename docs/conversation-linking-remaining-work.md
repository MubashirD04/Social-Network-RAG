# Conversation-linking layer — remaining work

Tracks what's left on the inferred-conversation-linking feature (see `docs/context.md`'s `src/conversation_linker.py` / `src/coref_resolver.py` sections for what's built and why). Intended as input for scoping specs on the next phase of work.

---

## Deployment status (2026-09-11)

The default image (`docker build .`, Tier 1 only — no classifier mode, no coref) is **build-verified and ready to host**: builds clean at 1.29GB, container starts, `/health` returns 200, and a real `/analyse` call against the synthetic Slack export succeeds end to end through the running container.

Getting here caught two real bugs in the `runtime-coref` stage that would otherwise have shipped:
- Appending `runtime-coref` after `runtime` in the same Dockerfile made it the *default* build target (Docker builds the last stage in the file when no `--target` is given) — a plain `docker build .` was silently building the full torch/transformers/fastcoref stack, producing a 12.2GB image instead of ~1.3GB. Fixed with a trailing `FROM runtime AS default` stage.
- `requirements-coref.txt` had no CPU-only torch pin, so it resolved the CUDA-enabled build from PyPI's default index. Fixed with `--extra-index-url https://download.pytorch.org/whl/cpu` + `torch==2.6.0+cpu`.

Both are fixed; `runtime-coref` has now been built once (successfully, coref model verified loading and resolving correctly during the bake step) but not re-verified after these two fixes — see item 1 below.

## Must-do before Tier 2 coreference resolution can be trusted

1. **Re-verify `runtime-coref` builds clean after the two fixes above.** It built successfully once (before the CPU-pin fix, so that specific run pulled the CUDA stack) — hasn't been rebuilt since pinning `torch==2.6.0+cpu`. Confirm the pin doesn't break resolution (rerun the same `/analyse`-style smoke test against a `--target runtime-coref` image with `CONVERSATION_LINKING_COREF_ENABLED=true`).
2. **Run `scripts/eval_conversation_linker.py` with `CONVERSATION_LINKING_COREF_ENABLED=true`** against real data. This is the actual gate for the merge-vs-split Docker image decision — no precision/recall number exists yet for coref specifically, only for the weighted-sum baseline and the (undertrained) classifier.
3. **Cold-start test with no network access.** Original spec requirement never completed: start the container with `HF_HUB_OFFLINE=1`/`TRANSFORMERS_OFFLINE=1` set, in an environment with network disabled, and confirm both the MiniLM and (if enabled) f-coref models load from local disk with zero runtime fetch attempts.

## Must-do before the Tier 2 classifier can be trusted

4. **Train on real Slack export(s), not just the synthetic fixture.** Current model has only 5 positive examples inside the candidate window; flagged everywhere in the code/docs as a pipeline smoke test, not a real result.
5. **Proper held-out evaluation.** Training and eval currently reuse the same data (no train/test split), so the classifier's reported numbers are optimistic by construction. Needs either multiple independent exports (train on some, eval on others) or k-fold CV once there's enough data.

## Decisions pending on measurement

6. **Single vs. two Docker images** — blocked on item 2.
7. **Weighted-sum vs. classifier as the shipped default** — no apples-to-apples comparison exists yet (classifier's numbers aren't from held-out data).
8. **Tier 1 weight/threshold tuning** — current defaults were hand-calibrated against one smoke-test case, not systematically swept against the eval script's precision/recall output.

## Integration gaps (fixed 2026-09-11)

9. ~~Frontend has no visibility into the new inferred-link layer.~~ **Fixed.** Each search result in `App.jsx` now shows a "Linked context" section (`.linked-context`) listing the messages `conversation_linker` connected it to, styled with the same dashed muted-blue-gray language as the graph's existing `inferred` edges, clickable to jump to that node. Verified in a real browser via Playwright against the live dev servers, not just a successful build — screenshot confirmed the section renders correctly under real search results (e.g. Diana Kowalski's coffee-machine message showing Frank Silva's reply as linked context).
10. ~~MCP server doesn't expose the new endpoint.~~ **Fixed.** Added `get_inferred_links(analysis_id)` to `mcp_server/server.py`, wrapping `GET /graph/{id}/inferred-links`, following the same pattern as the other tools. (Note: `linked_context` was already reachable via the existing `query_chat` tool, which passes through the raw `/query` response — this new tool adds the full edge list, which wasn't reachable any other way.)

## Validated / not blocking

Tier 1 scoring (`ConversationLinker.score_pairs`, all four signals), the `chat_parser.py` multi-day Slack export bug fix (channel grouping + cross-day `thread_ts` resolution), the classifier's plumbing (training script, scoring mode, missing-model fallback), coref's core mechanics (separator-based message splitting, per-channel windowing, the `fastcoref.spacy_component` import bug, the `spacy.blank` vs. tagged-pipeline bug, the `transformers<5` pin), the default Docker image (build + container start + a real `/analyse` call, all verified), and both integration gaps above (frontend display, MCP tool) are built and tested — just the coref/classifier pieces specifically not yet validated at real-data scale.
