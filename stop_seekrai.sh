#!/bin/bash
# SeekrAI Stop Script — stops all services

echo "========================================"
echo "  Stopping SeekrAI Services"
echo "========================================"
echo ""

if tmux has-session -t seekrai-search 2>/dev/null; then
    tmux kill-session -t seekrai-search
    echo "  Stopped search service (port 5500)"
else
    echo "  Search service not running"
fi

if tmux has-session -t seekrai-ui 2>/dev/null; then
    tmux kill-session -t seekrai-ui
    echo "  Stopped UI service (port 5501)"
else
    echo "  UI service not running"
fi

if tmux has-session -t seekrai-asksre 2>/dev/null; then
    tmux kill-session -t seekrai-asksre
    echo "  Stopped ask-sre service"
else
    echo "  ask-sre service not running"
fi

# The pgvector database container is left running by default — it may be shared
# and is slow to re-index. To stop it too, uncomment the lines below (works with
# either docker or podman, on macOS and Fedora):
# PGVECTOR_CONTAINER="${PGVECTOR_CONTAINER:-pgvector}"
# for cli in docker podman; do
#     command -v "$cli" &>/dev/null && "$cli" stop "$PGVECTOR_CONTAINER" 2>/dev/null \
#         && { echo "  Stopped pgvector database ($cli)"; break; }
# done

echo ""
echo "All services stopped."
echo ""
