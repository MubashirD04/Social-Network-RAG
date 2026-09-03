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
