#!/bin/bash

# Get the absolute path of the project root
PROJECT_ROOT=$(pwd)
PHASE2_DIR="$PROJECT_ROOT/Phase2"
VENV_PYTHON="$PROJECT_ROOT/venv/bin/python3"

# Check if venv exists
if [ ! -f "$VENV_PYTHON" ]; then
    echo "Error: Virtual environment not found at $VENV_PYTHON"
    echo "Please run the installation steps in README first."
    exit 1
fi

echo "--- Starting Social Network RAG Backend ---"
echo "API will be available at http://localhost:8000"

# Set PYTHONPATH so modules are found
export PYTHONPATH=$PYTHONPATH:$PHASE2_DIR

# Start FastAPI in the background
$VENV_PYTHON -m uvicorn api.main:app --host 0.0.0.0 --port 8000 &
API_PID=$!

# Wait for API to be ready
echo "Waiting for API to start..."
while ! curl -s http://localhost:8000/health > /dev/null; do
    sleep 1
done
echo "API is UP!"

echo "--- Starting MCP Inspector ---"
echo "This will allow you to test tools in your browser."

# Run the inspector
npx @modelcontextprotocol/inspector $VENV_PYTHON $PHASE2_DIR/mcp_server/server.py

# When inspector is closed, kill the API
kill $API_PID
echo "Backend stopped."
