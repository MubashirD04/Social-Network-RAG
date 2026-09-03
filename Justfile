set shell := ["bash", "-c"]

# Install all dependencies
install:
    uv venv
    uv pip install -r Phase2/requirements.txt
    cd Phase2/frontend && npm install

# Remove installed dependencies
uninstall:
    rm -rf .venv
    rm -rf Phase2/frontend/node_modules

# Start the FastAPI backend
api:
    export PYTHONPATH=$PYTHONPATH:$(pwd)/Phase2 && \
    uv run uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

# Start the React frontend
frontend:
    cd Phase2/frontend && npm run dev

# Run the MCP server via inspector
inspect:
    export PYTHONPATH=$PYTHONPATH:$(pwd)/Phase2 && \
    npx @modelcontextprotocol/inspector uv run python Phase2/mcp_server/server.py

# Start the API and frontend together in the background
start:
    export PYTHONPATH=$PYTHONPATH:$(pwd)/Phase2 && \
    (uv run uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload > /tmp/social-rag-api.log 2>&1 &) && \
    (cd Phase2/frontend && npm run dev > /tmp/social-rag-frontend.log 2>&1 &) && \
    echo "API on :8000 (log: /tmp/social-rag-api.log), frontend on Vite's default port (log: /tmp/social-rag-frontend.log)." && \
    echo "Run 'just stop' to stop both."

# Stop processes started by `just start` (any leftover session, not just the last one)
stop:
    for pid in $(pgrep -f "Phase2/frontend/node_modules/.bin/vite" 2>/dev/null); do \
        ppid=$(ps -o ppid= -p "$pid" 2>/dev/null | tr -d ' '); \
        kill "$pid" "$ppid" 2>/dev/null || true; \
    done
    pkill -f "uvicorn api.main:app --host 0.0.0.0 --port 8000" 2>/dev/null || true
    rm -f .dev-pids
    echo "Stopped."

# Run all tests
test:
    export PYTHONPATH=$PYTHONPATH:$(pwd)/Phase2 && \
    uv run pytest Phase2/tests -v

# Run the social demo script
demo:
    export PYTHONPATH=$PYTHONPATH:$(pwd)/Phase2 && \
    uv run python Phase2/social_demo.py

# Clean up temporary files
clean:
    rm -rf Phase2/frontend/dist
    rm -rf .pytest_cache
    rm -rf output/*
