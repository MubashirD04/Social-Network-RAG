# syntax=docker/dockerfile:1

# ---- Stage 1: build the React frontend ----
FROM node:20-slim AS frontend-build
WORKDIR /build
COPY Phase2/frontend/package.json Phase2/frontend/package-lock.json ./
RUN npm ci
COPY Phase2/frontend/ ./
RUN npm run build

# ---- Stage 2: backend runtime ----
FROM python:3.12-slim AS runtime
WORKDIR /app/Phase2

ENV PYTHONPATH=/app/Phase2 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# onnxruntime (a fastembed dependency) needs libgomp at runtime and it is not
# present in the slim base image.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY Phase2/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Bake the sentence-transformers/all-MiniLM-L6-v2 ONNX model into the image so
# the container never needs network access to load it. fastembed caches to
# {tempdir}/fastembed_cache (i.e. /tmp/fastembed_cache) by default, and
# src/llm_service.py never overrides cache_dir, so this path is picked up
# automatically at runtime too. Kept above the app COPY so code edits don't
# bust this (slow, ~80MB download) layer.
RUN python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='sentence-transformers/all-MiniLM-L6-v2')"

# Applied only after the bake step above (which needs network access to
# download the model the first time) — these stop fastembed/transformers
# from making any version-check network call at runtime once the model is
# already cached in the image.
ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

COPY Phase2/api ./api
COPY Phase2/src ./src
COPY --from=frontend-build /build/dist ./frontend/dist

RUN useradd --create-home --uid 1000 appuser \
    && chown -R appuser:appuser /app /tmp/fastembed_cache
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=45s --retries=3 \
    CMD python -c 'import os,urllib.request as u; u.urlopen("http://localhost:%s/health" % os.environ.get("PORT","8000"), timeout=3)' || exit 1

# Shell form so $PORT (injected by Render, absent locally) expands; falls
# back to 8000 for a plain `docker run`.
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]

# ---- Stage 3 (optional, not built by default): + coreference resolution ----
# Adds fastcoref (torch + transformers CPU wheels) for the optional Tier 2
# coreference-resolution preprocessing step (src/coref_resolver.py). A
# plain `docker build .` never reaches this stage — the default target is
# `runtime` above. Opt in explicitly:
#   docker build --target runtime-coref -t social-rag:coref .
#   docker run -e CONVERSATION_LINKING_COREF_ENABLED=true ... social-rag:coref
# Measured (not estimated — see docs/context.md): ~1.2GB of installed
# dependencies (torch/transformers/spacy/datasets/pyarrow/pandas — numpy,
# scipy, networkx already in the base image don't count twice) + ~365MB
# f-coref model weights + ~15MB en_core_web_sm ≈ 1.5-1.6GB added to the
# image, and ~500-800MB additional RSS once the pipeline is loaded and
# processing. Only worth it once scripts/eval_conversation_linker.py shows
# it actually improves precision/recall on your own data.
FROM runtime AS runtime-coref
USER root
COPY Phase2/requirements-coref.txt ./requirements-coref.txt
RUN pip install --no-cache-dir -r requirements-coref.txt
# en_core_web_sm (~15MB) is required, not optional: fastcoref's resolve_text
# substitution only fires for a mention whose cluster contains a NOUN/PROPN
# token.pos_, and spacy.blank("en") never runs a tagger, so pos_ is always
# empty — coref_resolver.py loads a real tagged pipeline for exactly this
# reason (see its comment for how this was verified).
RUN python -m spacy download en_core_web_sm
USER appuser

# Bake the biu-nlp/f-coref model weights into appuser's Hugging Face cache
# (created fresh under its home dir, so no chown needed afterward). The
# HF_HUB_OFFLINE/TRANSFORMERS_OFFLINE=1 set in the runtime stage above would
# block this download, so they're overridden for this single RUN only —
# the final image still inherits =1 for actual runtime.
RUN HF_HUB_OFFLINE=0 TRANSFORMERS_OFFLINE=0 python -c "\
import spacy, fastcoref.spacy_component; \
nlp = spacy.load('en_core_web_sm', disable=['parser', 'ner', 'lemmatizer']); \
nlp.add_pipe('fastcoref', config={'device': 'cpu'})"

# ---- Stage 4: re-declares the plain runtime image as the LAST stage ----
# Docker builds the *last* stage in the file when no --target is given —
# without this, appending runtime-coref above silently made IT the default
# for a plain `docker build .`, defeating the entire point of it being
# optional. This stage adds nothing (BuildKit reuses runtime's already-built
# layers with zero extra cost) and exists purely to make `runtime` the
# implicit default again. Build runtime-coref only with an explicit
# `--target runtime-coref`.
FROM runtime AS default
