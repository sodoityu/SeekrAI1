#!/bin/bash
# SeekrAI Startup Script
# Usage: ./start_seekrai.sh [--dev]

echo "========================================"
echo "  Starting SeekrAI Services"
echo "========================================"
echo ""

# Check if tmux is installed
if ! command -v tmux &> /dev/null; then
    echo "tmux is not installed"
    echo ""
    echo "Install it with:"
    echo "  sudo dnf install tmux   # Fedora"
    echo "  brew install tmux       # macOS"
    exit 1
fi

# Change to script directory
cd "$(dirname "$0")"

# Load .env if it exists
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
    echo "Loaded .env"
fi

# Kerberos environment
export KERBEROS_REALM="${KERBEROS_REALM:-IPA.REDHAT.COM}"
export LDAP_SERVER="${LDAP_SERVER:-ldap://ipa.redhat.com}"
export LDAP_BASE_DN="${LDAP_BASE_DN:-dc=redhat,dc=com}"
export LDAP_USER_BASE="${LDAP_USER_BASE:-cn=users,cn=accounts}"
export SECRET_KEY="${SECRET_KEY:-$(python3 -c 'import secrets; print(secrets.token_hex(32))')}"

# Dev mode
if [ "$1" = "--dev" ]; then
    export DISABLE_SSO=1
    echo "Dev mode: Kerberos authentication disabled"
    echo ""
else
    unset DISABLE_SSO
fi

# Service 1: Backend API (port 5500)
if tmux has-session -t seekrai-search 2>/dev/null; then
    echo "Search service already running (port 5500)"
else
    echo "Starting search service (port 5500)..."
    tmux new-session -d -s seekrai-search "cd $(pwd) && python3 unified_search.py"
    sleep 2
    echo "  Started search service"
fi

# Service 2: Frontend proxy + auth (port 5501)
if tmux has-session -t seekrai-ui 2>/dev/null; then
    echo "UI service already running (port 5501)"
else
    echo "Starting UI service (port 5501)..."
    ENV_VARS="KERBEROS_REALM=$KERBEROS_REALM LDAP_SERVER=$LDAP_SERVER LDAP_BASE_DN=$LDAP_BASE_DN LDAP_USER_BASE=$LDAP_USER_BASE SECRET_KEY=$SECRET_KEY"
    if [ -n "$DISABLE_SSO" ]; then
        ENV_VARS="$ENV_VARS DISABLE_SSO=1"
    fi
    if [ -n "$USER_KEY" ]; then
        ENV_VARS="$ENV_VARS USER_KEY=$USER_KEY"
    fi
    if [ -n "$AI_API_TOKEN" ]; then
        ENV_VARS="$ENV_VARS AI_API_TOKEN=$AI_API_TOKEN"
    fi
    tmux new-session -d -s seekrai-ui "cd $(pwd) && $ENV_VARS python3 seekrWebUI_server.py"
    sleep 2
    echo "  Started UI service"
fi

# Service 3: ask-sre MCP server (port 8000) — optional
ASK_SRE_DIR="${ASK_SRE_DIR:-$HOME/code/ask-sre}"
if tmux has-session -t seekrai-asksre 2>/dev/null; then
    echo "ask-sre service already running (port 8000)"
elif [ -d "$ASK_SRE_DIR" ]; then
    echo "Starting ask-sre MCP server (port 8000)..."
    tmux new-session -d -s seekrai-asksre "cd $ASK_SRE_DIR && poetry run ask-sre mcp --transport http --host 0.0.0.0 --port 8000"
    sleep 2
    echo "  Started ask-sre service"
else
    echo "ask-sre not found at $ASK_SRE_DIR (skipping — set ASK_SRE_DIR to override)"
fi

echo ""
echo "========================================"
echo "  Services Started!"
echo "========================================"
echo ""
echo "Open your browser:"
echo "  http://localhost:5501/seekr/login"
echo ""
echo "To view service logs:"
echo "  tmux attach -t seekrai-search   (Ctrl+B, D to detach)"
echo "  tmux attach -t seekrai-ui       (Ctrl+B, D to detach)"
echo "  tmux attach -t seekrai-asksre   (Ctrl+B, D to detach)"
echo ""
echo "To stop services:"
echo "  ./stop_seekrai.sh"
echo ""
