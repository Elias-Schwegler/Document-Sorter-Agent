#!/usr/bin/env bash
# Check health of all Document Manager services
set -euo pipefail

if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

BACKEND_PORT="${BACKEND_PORT:-8000}"
QDRANT_PORT="${QDRANT_PORT:-6333}"
OLLAMA_PORT="${OLLAMA_PORT:-11434}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"

check_service() {
    local name="$1" url="$2"
    if curl -sf "$url" > /dev/null 2>&1; then
        echo "[OK] $name"
    else
        echo "[FAIL] $name ($url)"
    fi
}

echo "=== Document Manager Health Check ==="
check_service "Backend" "http://localhost:$BACKEND_PORT/health"
check_service "Qdrant" "http://localhost:$QDRANT_PORT/healthz"
check_service "Ollama" "http://localhost:$OLLAMA_PORT/api/tags"
check_service "Frontend" "http://localhost:$FRONTEND_PORT"
echo "=== Done ==="
