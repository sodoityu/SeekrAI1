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
    tmux new-session -d -s seekrai-ui "cd $(pwd) && $ENV_VARS python3 seekrWebUI_server.py"
    sleep 2
    echo "  Started UI service"
fi

# Service 3: ask-sre MCP server + its pgvector dependency (optional)
# Config (overridable via .env) — see SETUP_ASK_SRE.md
# Resolve ASK_SRE_DIR: honor an explicit setting, otherwise probe common locations
if [ -n "$ASK_SRE_DIR" ]; then
    ASK_SRE_DIR="${ASK_SRE_DIR/#\~/$HOME}"   # expand a leading ~ from .env
else
    for candidate in "$HOME/ask-sre" "$HOME/code/ask-sre" "$(dirname "$(pwd)")/ask-sre"; do
        if [ -f "$candidate/pyproject.toml" ]; then
            ASK_SRE_DIR="$candidate"
            break
        fi
    done
    ASK_SRE_DIR="${ASK_SRE_DIR:-$HOME/code/ask-sre}"   # fall back for the "not set up" message
fi
ASK_SRE_PORT="${ASK_SRE_PORT:-8000}"
PGVECTOR_CONTAINER="${PGVECTOR_CONTAINER:-pgvector}"

# --- Container engine helpers (cross-platform: macOS + Fedora/Linux, Docker + Podman) ---
OS_KIND="$(uname -s)"   # "Darwin" on macOS, "Linux" on Fedora

# Ensure the given container engine ($1: docker|podman) is up, starting it if needed.
# Handles the Docker Desktop app and Docker CLI/systemd on both macOS and Fedora,
# plus podman machine (macOS) / daemonless podman (Linux). Returns 0 once reachable.
ensure_engine_running() {
    local cli="$1" i
    $cli info >/dev/null 2>&1 && return 0   # already up

    if [ "$cli" = "docker" ]; then
        if [ "$OS_KIND" = "Darwin" ]; then
            echo "  Docker not running — launching Docker Desktop (this can take up to a minute)..."
            open -a Docker >/dev/null 2>&1 || open -a "Docker Desktop" >/dev/null 2>&1
        else
            echo "  Docker daemon not running — starting the docker service..."
            if command -v systemctl >/dev/null 2>&1; then
                systemctl start docker >/dev/null 2>&1 || sudo systemctl start docker >/dev/null 2>&1
            fi
        fi
    elif [ "$cli" = "podman" ]; then
        if [ "$OS_KIND" = "Darwin" ]; then
            echo "  Podman machine not running — starting it (this can take a minute)..."
            podman machine start >/dev/null 2>&1
        fi
        # On Linux podman is daemonless; nothing to start.
    fi

    # Wait for the engine to become reachable
    for i in $(seq 1 30); do
        $cli info >/dev/null 2>&1 && return 0
        sleep 2
    done
    return 1
}

start_ask_sre() {
    if tmux has-session -t seekrai-asksre 2>/dev/null; then
        echo "ask-sre service already running (port $ASK_SRE_PORT)"
        return 0
    fi

    # Preflight: ask-sre must be installed and poetry available
    if [ ! -d "$ASK_SRE_DIR" ]; then
        echo "ask-sre not set up — semantic SOP search will be disabled."
        echo "  Expected a checkout at: $ASK_SRE_DIR (override with ASK_SRE_DIR in .env)"
        echo "  To enable it, follow the setup guide: SETUP_ASK_SRE.md"
        return 0
    fi
    if ! command -v poetry &> /dev/null; then
        echo "ask-sre found at $ASK_SRE_DIR but 'poetry' is not installed — skipping."
        echo "  Install Poetry, then see SETUP_ASK_SRE.md."
        return 0
    fi

    # Dependency: pgvector PostgreSQL container must be running.
    # Works with Docker (Desktop app or CLI) and Podman, on macOS and Fedora.
    # Build the candidate engine list (CONTAINER_ENGINE in .env forces a choice).
    local engines=() eng cli="" fallback=""
    if [ -n "$CONTAINER_ENGINE" ] && command -v "$CONTAINER_ENGINE" &>/dev/null; then
        engines=("$CONTAINER_ENGINE")
    else
        command -v docker &>/dev/null && engines+=("docker")
        command -v podman &>/dev/null && engines+=("podman")
    fi

    if [ ${#engines[@]} -eq 0 ]; then
        echo "  Neither docker nor podman found — cannot start the pgvector database (see SETUP_ASK_SRE.md)."
    else
        # Prefer the engine that actually holds the pgvector container; start engines as needed.
        for eng in "${engines[@]}"; do
            ensure_engine_running "$eng" || continue
            if $eng ps -a --format '{{.Names}}' 2>/dev/null | grep -qx "$PGVECTOR_CONTAINER"; then
                cli="$eng"; break
            fi
            [ -z "$fallback" ] && fallback="$eng"   # reachable, but no container here
        done

        if [ -n "$cli" ]; then
            if $cli ps --format '{{.Names}}' 2>/dev/null | grep -qx "$PGVECTOR_CONTAINER"; then
                echo "  pgvector database already running ($PGVECTOR_CONTAINER via $cli)"
            else
                echo "  Starting pgvector database ($PGVECTOR_CONTAINER via $cli)..."
                if $cli start "$PGVECTOR_CONTAINER" >/dev/null 2>&1; then
                    # Wait until Postgres actually accepts connections
                    for _ in $(seq 1 20); do
                        $cli exec "$PGVECTOR_CONTAINER" pg_isready -U postgres >/dev/null 2>&1 && break
                        sleep 1
                    done
                    echo "    Started pgvector database"
                else
                    echo "    Could not start '$PGVECTOR_CONTAINER' — check '$cli logs $PGVECTOR_CONTAINER'"
                fi
            fi
        elif [ -n "$fallback" ]; then
            echo "  pgvector database container '$PGVECTOR_CONTAINER' not found (checked: ${engines[*]})."
            echo "    ask-sre needs it — create it per SETUP_ASK_SRE.md (step 1)."
        else
            echo "  Could not reach a container engine (${engines[*]}) to start the pgvector database."
            [ "$OS_KIND" = "Darwin" ] && echo "    macOS: open the Docker Desktop app (or run 'podman machine start'), then re-run."
            [ "$OS_KIND" = "Linux" ]  && echo "    Fedora: run 'sudo systemctl start docker' (or use podman), then re-run."
        fi
    fi

    # Start the MCP server, keeping MCP_SERVER_URL in sync with the chosen port
    echo "Starting ask-sre MCP server (port $ASK_SRE_PORT)..."
    tmux new-session -d -s seekrai-asksre \
        "cd $ASK_SRE_DIR && poetry run ask-sre mcp --transport http --host 0.0.0.0 --port $ASK_SRE_PORT"

    # Readiness probe: wait for the endpoint instead of a blind sleep
    local ready=0
    for _ in $(seq 1 15); do
        if ! tmux has-session -t seekrai-asksre 2>/dev/null; then
            break   # session died on launch
        fi
        if curl -s -o /dev/null --max-time 2 "http://localhost:$ASK_SRE_PORT/mcp/"; then
            ready=1
            break
        fi
        sleep 1
    done

    if [ "$ready" = "1" ]; then
        echo "  ask-sre MCP server is ready (port $ASK_SRE_PORT)"
    elif ! tmux has-session -t seekrai-asksre 2>/dev/null; then
        echo "  ask-sre failed to start — the server exited immediately."
        echo "    Try running it manually to see the error:"
        echo "    cd $ASK_SRE_DIR && poetry run ask-sre mcp --transport http --port $ASK_SRE_PORT"
    else
        echo "  ask-sre started but did not become ready in time — check: tmux attach -t seekrai-asksre"
    fi
}

start_ask_sre

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
