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
    rm -f .dev-pids && \
    (uv run uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload > /tmp/social-rag-api.log 2>&1 & echo $! >> .dev-pids) && \
    (cd Phase2/frontend && npm run dev > /tmp/social-rag-frontend.log 2>&1 & echo $! >> ../../.dev-pids) && \
    echo "API on :8000 (log: /tmp/social-rag-api.log), frontend on Vite's default port (log: /tmp/social-rag-frontend.log)." && \
    echo "Run 'just stop' to stop both."

# Stop processes started by `just start`
stop:
    if [ -f .dev-pids ]; then \
        while read -r pid; do kill "$pid" 2>/dev/null || true; done < .dev-pids; \
        rm -f .dev-pids; \
        echo "Stopped."; \
    else \
        echo "No .dev-pids file found — nothing to stop."; \
    fi

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
