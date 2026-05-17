#!/bin/bash
# Simple startup script for Unified Search

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "========================================================================"
echo "  🚀 Starting Unified Search Tool"
echo "========================================================================"
echo ""
echo "📂 Working directory: $SCRIPT_DIR"
echo ""

# Try to run directly with python3
echo "📦 Trying to run with system Python..."

# Check if Flask is available
if python3 -c "import flask" 2>/dev/null; then
    echo "✅ Flask is available"
    echo "🌐 Starting server on http://localhost:5500"
    echo ""
    exec python3 unified_search.py
else
    echo "❌ Flask not installed"
    echo ""
    echo "Please install dependencies:"
    echo "  pip3 install flask requests"
    echo ""
    echo "Or install with pip:"
    echo "  pip3 install -r requirements.txt"
    echo ""
    exit 1
fi
