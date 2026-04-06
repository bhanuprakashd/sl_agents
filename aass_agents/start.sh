#!/usr/bin/env bash
# SL Agents — Start API Server
# Usage: ./start.sh [port]

PORT="${1:-8080}"

cd "$(dirname "$0")"

# Kill any existing process on the port
if command -v lsof &>/dev/null; then
    PID=$(lsof -ti :"$PORT" 2>/dev/null)
    if [ -n "$PID" ]; then
        echo "  Killing existing process on port $PORT (PID: $PID)..."
        kill -9 $PID 2>/dev/null
        sleep 1
    fi
elif command -v netstat &>/dev/null; then
    PID=$(netstat -ano 2>/dev/null | grep ":$PORT " | grep LISTENING | awk '{print $NF}' | head -1)
    if [ -n "$PID" ] && [ "$PID" != "0" ]; then
        echo "  Killing existing process on port $PORT (PID: $PID)..."
        taskkill //F //PID "$PID" 2>/dev/null || kill -9 "$PID" 2>/dev/null
        sleep 1
    fi
fi

echo "============================================================"
echo "  SL Agents — Event Pipeline Server"
echo "  Starting on http://localhost:$PORT"
echo "  Dashboard: http://localhost:$PORT"
echo "  API Docs:  http://localhost:$PORT/api/docs"
echo "============================================================"

# Activate venv if available
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

python -m uvicorn api:app --host 0.0.0.0 --port "$PORT" --timeout-keep-alive 5400
