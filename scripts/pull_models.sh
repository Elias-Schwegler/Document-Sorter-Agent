#!/usr/bin/env bash
# Pull default models into Ollama
# Usage: ./scripts/pull_models.sh [OLLAMA_URL]

set -euo pipefail

OLLAMA_URL="${1:-http://localhost:11434}"

# Source .env if it exists
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

AGENT_MODEL="${AGENT_MODEL:-qwen3.5:4b}"
EMBEDDING_MODEL="${EMBEDDING_MODEL:-qwen3-embedding:4b}"

echo "Ollama URL: $OLLAMA_URL"
echo "Pulling agent model: $AGENT_MODEL"
curl -s "$OLLAMA_URL/api/pull" -d "{\"name\": \"$AGENT_MODEL\"}" | while read -r line; do
    status=$(echo "$line" | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
    [ -n "$status" ] && echo "  $status"
done
echo "Agent model ready."

echo "Pulling embedding model: $EMBEDDING_MODEL"
curl -s "$OLLAMA_URL/api/pull" -d "{\"name\": \"$EMBEDDING_MODEL\"}" | while read -r line; do
    status=$(echo "$line" | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
    [ -n "$status" ] && echo "  $status"
done
echo "Embedding model ready."

echo "All models pulled successfully."
