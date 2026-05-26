#!/bin/bash
# Simple startup script for Unified Search Tool
# Usage: ./start.sh

set -e

echo "🚀 Starting Unified Search Tool..."
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
# MCP server is in ../kush/mcp-server/mcp-server relative to finaltoolMay18
MCP_SERVER_DIR="$SCRIPT_DIR/../kush/mcp-server/mcp-server"

# Step 1: Start MCP Server
echo -e "${YELLOW}Step 1: Starting MCP Server...${NC}"
cd "$MCP_SERVER_DIR"

# Check if already running
if netstat -tuln 2>/dev/null | grep -q ":8000 "; then
    echo -e "${GREEN}✅ MCP Server already running on port 8000${NC}"
else
    nohup ./start_server.sh > mcp_server.log 2>&1 &
    echo -e "${GREEN}✅ MCP Server started (logs: mcp_server.log)${NC}"
    sleep 5
fi

# Step 2: Start Unified Search
echo ""
echo -e "${YELLOW}Step 2: Starting Unified Search UI...${NC}"
cd "$SCRIPT_DIR"

# Check if already running
if netstat -tuln 2>/dev/null | grep -q ":5500 "; then
    echo -e "${GREEN}✅ Unified Search already running on port 5500${NC}"
else
    nohup python3 unified_search.py > unified_search.log 2>&1 &
    echo -e "${GREEN}✅ Unified Search started (logs: unified_search.log)${NC}"
    sleep 5
fi

# Done
echo ""
echo "=========================================="
echo -e "${GREEN}✅ All services are running!${NC}"
echo "=========================================="
echo ""
echo "🌐 Open in your browser:"
echo "   👉 http://localhost:5500"
echo ""
echo "📊 Services:"
echo "   • MCP Server:      http://localhost:8000"
echo "   • Unified Search:  http://localhost:5500"
echo ""
echo "🛑 To stop:"
echo "   cd $SCRIPT_DIR && ./stop.sh"
echo "   OR: pkill -f uvicorn && pkill -f unified_search"
echo ""
