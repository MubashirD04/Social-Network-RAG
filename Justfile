set shell := ["bash", "-c"]

# Install all dependencies
install:
    uv venv
    uv pip install -r Phase2/requirements.txt
    cd Phase2/frontend && npm install

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
