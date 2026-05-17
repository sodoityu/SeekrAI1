#!/bin/bash
# Simple startup script for Unified Search
# Works from finaltoolMay17/ or project root!

# Go to finaltoolMay17 directory
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "========================================================================"
echo "  🚀 Starting Unified Search Tool (Self-Contained)"
echo "========================================================================"
echo ""
echo "📂 Working directory: $SCRIPT_DIR"
echo ""

# Check if we're in the ask-sre project directory structure
if [ -f "../pyproject.toml" ]; then
    echo "✅ Found poetry project in parent directory"
    echo "📦 Using poetry to run the application..."
    echo ""

    # Run with poetry (stay in finaltoolMay17 directory)
    cd ..
    exec poetry run python finaltoolMay17/unified_search.py
else
    # Try to run directly with python3
    echo "📦 Trying to run with system Python..."

    # Check if Flask is available
    if python3 -c "import flask" 2>/dev/null; then
        echo "✅ Flask is available"
        exec python3 unified_search.py
    else
        echo "❌ Flask not installed"
        echo ""
        echo "Please install dependencies:"
        echo "  pip3 install flask requests"
        echo ""
        echo "Or use poetry from the parent directory:"
        echo "  cd .."
        echo "  poetry install"
        echo "  poetry run python finaltoolMay17/unified_search.py"
        exit 1
    fi
fi
