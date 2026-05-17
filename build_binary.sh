#!/bin/bash
# Build standalone binary using PyInstaller

set -e

echo "======================================================================"
echo "🔨 Building Unified Search Binary"
echo "======================================================================"

# Check if PyInstaller is installed
if ! poetry run pyinstaller --version > /dev/null 2>&1; then
    echo "📦 Installing PyInstaller..."
    poetry add --group dev pyinstaller
fi

echo ""
echo "📦 Building binary with PyInstaller..."
echo ""

# Build single executable
poetry run pyinstaller \
    --onefile \
    --name unified-search \
    --add-data "templates_unified:templates_unified" \
    --hidden-import flask \
    --hidden-import jinja2 \
    --hidden-import requests \
    --hidden-import concurrent.futures \
    unified_search.py

echo ""
echo "======================================================================"
echo "✅ Binary built successfully!"
echo "======================================================================"
echo ""
echo "📍 Location: dist/unified-search"
echo "📦 Size: $(du -h dist/unified-search | cut -f1)"
echo ""
echo "🧪 Test it:"
echo "   cd dist/"
echo "   ./unified-search"
echo "   # Open: http://localhost:5500"
echo ""
echo "📤 Distribute:"
echo "   1. Upload to GitHub Releases"
echo "   2. Users download and run:"
echo "      chmod +x unified-search"
echo "      ./unified-search"
echo ""
echo "⚠️  Note: Binary does NOT include Slack MCP support"
echo "   (Users still need Podman/Docker for Slack search)"
echo ""
