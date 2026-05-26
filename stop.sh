#!/bin/bash
# Stop all servers
# Usage: ./stop.sh

echo "🛑 Stopping all servers..."
echo ""

# Stop MCP Server (port 8000)
if pgrep -f "uvicorn.*8000" > /dev/null 2>&1; then
    pkill -9 -f "uvicorn.*8000"
    sleep 1
    echo "✅ Stopped MCP Server (port 8000)"
elif lsof -ti:8000 > /dev/null 2>&1; then
    kill -9 $(lsof -ti:8000)
    echo "✅ Killed process on port 8000"
else
    echo "ℹ️  MCP Server not running"
fi

# Stop Unified Search (port 5500)
if pgrep -f "unified_search.py" > /dev/null 2>&1; then
    pkill -9 -f "unified_search.py"
    sleep 1
    echo "✅ Stopped Unified Search (port 5500)"
elif lsof -ti:5500 > /dev/null 2>&1; then
    kill -9 $(lsof -ti:5500)
    echo "✅ Killed process on port 5500"
else
    echo "ℹ️  Unified Search not running"
fi

# Verify ports are released
sleep 1
echo ""
if netstat -tuln 2>/dev/null | grep -qE ":8000|:5500"; then
    echo "⚠️  Warning: Some ports still in use"
    netstat -tuln 2>/dev/null | grep -E ":8000|:5500"
else
    echo "✅ All servers stopped and ports released"
fi
