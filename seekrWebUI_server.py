#!/usr/bin/env python3
"""
SeekrAI Web UI Server
Flask server for the SeekrAI unified search interface
Serves HTML pages and provides API endpoints for authentication and token management
"""

from flask import Flask, request, jsonify, session, redirect, send_file, send_from_directory
from flask_cors import CORS
from datetime import datetime, timedelta
import tempfile
import requests
import logging
import os
import sys
import subprocess
import json
import re
import glob as _glob
import getpass
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import time

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s:%(name)s:%(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
CORS(app, supports_credentials=True)

# Configuration
UNIFIED_SEARCH_API = 'http://localhost:5500'
KERBEROS_REALM = os.environ.get('KERBEROS_REALM', 'IPA.REDHAT.COM')
TOKENS_FILE = 'user_tokens.json'
SEARCH_HISTORY_FILE = 'user_search_history.json'

# ============================================================================
# Claude AI + SFDC Configuration
# ============================================================================
CLAUDE_API_BASE = os.getenv("CLAUDE_API_BASE", "")
CLAUDE_MODEL_ID = os.getenv("MODEL_ID", "claude-sonnet-4")
CLAUDE_USER_KEY = os.getenv("USER_KEY") or os.getenv("AI_API_TOKEN", "")
SFDC_API_BASE   = "https://access.redhat.com"
CLOSED_STATUSES = {'closed', 'waiting on customer', 'waiting for customer', 'resolved'}
_SYSTEM_CA      = "/etc/pki/tls/certs/ca-bundle.crt"

# Lazy-import cache for ask_sre
_asksre_search_fn  = None
_asksre_get_doc_fn = None

def _get_asksre_fns():
    global _asksre_search_fn, _asksre_get_doc_fn
    if _asksre_search_fn is None:
        try:
            _poetry_venv = subprocess.check_output(
                ["poetry", "env", "info", "--path"],
                cwd="/home/jayu/asksre/ask-sre",
                text=True, stderr=subprocess.DEVNULL
            ).strip()
            _site_pkgs = _glob.glob(f"{_poetry_venv}/lib/python*/site-packages")
            if _site_pkgs and _site_pkgs[0] not in sys.path:
                sys.path.insert(0, _site_pkgs[0])
            if "/home/jayu/asksre/ask-sre" not in sys.path:
                sys.path.insert(0, "/home/jayu/asksre/ask-sre")
        except Exception:
            pass
        from ask_sre.mcp.main import search_sre_docs, get_full_document
        _asksre_search_fn  = search_sre_docs
        _asksre_get_doc_fn = get_full_document
    return _asksre_search_fn, _asksre_get_doc_fn

def _get_ai_key():
    return CLAUDE_USER_KEY or ""

def _claude_post_with_retry(url, headers, payload, timeout, verify, max_retries=3):
    """POST to Claude API, retrying with backoff on 429 rate-limit responses."""
    for attempt in range(max_retries):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=timeout, verify=verify)
        except requests.exceptions.Timeout:
            raise
        if resp.status_code == 429:
            raw = resp.headers.get('Retry-After', '')
            wait = min(int(raw) if raw.isdigit() else 5 * (attempt + 1), 30)
            logger.warning(f"Claude API 429 rate limit, retrying in {wait}s (attempt {attempt + 1}/{max_retries})")
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return resp
    raise RuntimeError(f"Claude API still rate-limited after {max_retries} retries")


def call_claude_api(prompt: str, system: str = "", messages: list = None,
                    max_tokens: int = 2000, timeout=(10, 90)) -> str:
    key = _get_ai_key()
    if not key:
        return "<p><strong>Error:</strong> Claude API key not configured. Set USER_KEY or AI_API_TOKEN env var.</p>"
    endpoint = f"{CLAUDE_API_BASE}/sonnet/models/{CLAUDE_MODEL_ID}:streamRawPredict"
    _ca = os.getenv("REQUESTS_CA_BUNDLE") or (_SYSTEM_CA if os.path.exists(_SYSTEM_CA) else True)
    payload = {
        "anthropic_version": "vertex-2023-10-16",
        "max_tokens": max_tokens,
        "temperature": 0.2,
    }
    if system:
        payload["system"] = system
    if messages:
        payload["messages"] = messages
    else:
        payload["messages"] = [{"role": "user", "content": [{"type": "text", "text": prompt}]}]
    try:
        resp = _claude_post_with_retry(
            endpoint,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
            payload=payload, timeout=timeout, verify=_ca
        )
        data = resp.json()
        for block in data.get("content", []):
            if block.get("type") == "text":
                return block["text"]
        return "<p>No response generated.</p>"
    except requests.exceptions.Timeout:
        return "__TIMEOUT__"
    except Exception as e:
        logger.error(f"Claude API error: {e}")
        return f"<p><strong>Claude API error:</strong> {str(e)}</p>"


# ── SRE Cluster Investigator (Claude Tool Use / agentic loop) ─────────────────

SRE_INVESTIGATOR_SYSTEM_PROMPT = """You are an expert Red Hat SRE with deep knowledge of OpenShift, ROSA (Classic and HCP), Kubernetes, and AWS infrastructure.

You have access to a `run_command` tool that executes oc/kubectl/rosa CLI commands on the locally logged-in cluster. When the user reports a cluster issue, PROACTIVELY INVESTIGATE by running relevant commands — do not just give general advice. Chain multiple commands as needed to narrow down the root cause.

Investigation patterns by issue type:

NODES / SCHEDULING:
  oc get nodes -o wide
  oc describe node <node-name>
  oc get pods --all-namespaces --field-selector=status.phase!=Running
  oc adm top nodes

PODS / WORKLOADS:
  oc get pods -n <namespace> -o wide
  oc describe pod <pod-name> -n <namespace>
  oc logs <pod-name> -n <namespace> --tail=100
  oc get events -n <namespace> --sort-by=.lastTimestamp

NETWORKING:
  oc get svc -n <namespace>
  oc get route -n <namespace>
  oc get networkpolicies -n <namespace>
  oc get ingresscontroller -n openshift-ingress-operator -o yaml

STORAGE:
  oc get pvc -n <namespace>
  oc get pv
  oc describe pvc <pvc-name> -n <namespace>

CLUSTER HEALTH:
  oc get clusteroperators
  oc get clusterversion
  oc get mcp
  oc get nodes

ROSA:
  rosa list clusters
  rosa describe cluster -c <cluster-name>
  rosa list machinepools -c <cluster-name>

After investigating, provide a clear root cause analysis and recommended remediation steps.
Use HTML formatting (<p>, <ul>, <li>, <code>, <strong>) for your response — no markdown."""

ALLOWED_COMMANDS = [
    'oc ', 'oc\t', 'kubectl ', 'kubectl\t', 'rosa ',
]

def is_command_allowed(command: str) -> bool:
    cmd = command.strip()
    return any(cmd.startswith(prefix) for prefix in ALLOWED_COMMANDS)

def execute_local_command(command: str) -> str:
    if not is_command_allowed(command):
        return f"Error: Only oc, kubectl, and rosa commands are allowed. Rejected: {command!r}"
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=30
        )
        output = (result.stdout or '') + (result.stderr or '')
        return output[:3000] if output else "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: Command timed out after 30 seconds"
    except Exception as e:
        return f"Error executing command: {str(e)}"

def call_claude_with_tools(prompt: str, system: str = "", messages: list = None,
                           max_tokens: int = 4000, timeout=(10, 180)) -> str:
    """Agentic loop: Claude calls run_command tool until it reaches end_turn."""
    key = _get_ai_key()
    if not key:
        return "<p><strong>Error:</strong> Claude API key not configured.</p>"
    endpoint = f"{CLAUDE_API_BASE}/sonnet/models/{CLAUDE_MODEL_ID}:streamRawPredict"
    _ca = os.getenv("REQUESTS_CA_BUNDLE") or (_SYSTEM_CA if os.path.exists(_SYSTEM_CA) else True)
    loop_deadline = time.time() + 300  # 5-minute total wall-clock limit for the full agentic loop
    tools = [{
        "name": "run_command",
        "description": "Run an oc, kubectl, or rosa CLI command on the locally logged-in cluster to investigate issues.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The oc/kubectl/rosa command to execute, e.g. 'oc get nodes -o wide'"
                }
            },
            "required": ["command"]
        }
    }]
    if messages is None:
        messages = [{"role": "user", "content": [{"type": "text", "text": prompt}]}]
    for _ in range(10):
        if time.time() > loop_deadline:
            return "<p><strong>Investigation timed out</strong> — the cluster health check took too long. Try a more specific question (e.g. 'check cluster operators status').</p>"
        payload = {
            "anthropic_version": "vertex-2023-10-16",
            "max_tokens": max_tokens,
            "temperature": 0.2,
            "tools": tools,
            "tool_choice": {"type": "auto"},
        }
        if system:
            payload["system"] = system
        payload["messages"] = messages
        try:
            resp = _claude_post_with_retry(
                endpoint,
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
                payload=payload, timeout=timeout, verify=_ca
            )
            data = resp.json()
        except requests.exceptions.Timeout:
            return "__TIMEOUT__"
        except Exception as e:
            logger.error(f"Claude tools API error: {e}")
            return f"<p><strong>Claude API error:</strong> {str(e)}</p>"
        stop_reason = data.get("stop_reason", "")
        content_blocks = data.get("content", [])
        messages.append({"role": "assistant", "content": content_blocks})
        if stop_reason == "end_turn":
            for block in content_blocks:
                if block.get("type") == "text":
                    return block["text"]
            return "<p>Investigation complete.</p>"
        elif stop_reason == "tool_use":
            tool_results = []
            for block in content_blocks:
                if block.get("type") == "tool_use":
                    command = block.get("input", {}).get("command", "")
                    logger.info(f"SRE tool use: {command}")
                    output = execute_local_command(command)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block["id"],
                        "content": output
                    })
            messages.append({"role": "user", "content": tool_results})
        else:
            for block in content_blocks:
                if block.get("type") == "text":
                    return block["text"]
            return f"<p>Stopped with reason: {stop_reason}</p>"
    return "<p>Investigation reached maximum turns without a final conclusion.</p>"

def _is_cluster_investigation(question: str) -> bool:
    """Detect if the question is asking to investigate a live cluster."""
    q = question.lower()
    strong_signals = [
        'have a check', 'please investigate', 'please diagnose',
        'run oc', 'run kubectl', 'i had login', 'logged in to',
        'logged into', "i'm logged in", 'i am logged in',
    ]
    if any(s in q for s in strong_signals):
        return True
    has_cluster = any(s in q for s in ['cluster', 'node', 'namespace', 'pod'])
    has_intent = any(s in q for s in ['check', 'investigate', 'diagnose', 'troubleshoot', 'look into'])
    return has_cluster and has_intent


def exchange_offline_token(offline_token: str) -> str:
    try:
        r = requests.post(
            'https://sso.redhat.com/auth/realms/redhat-external/protocol/openid-connect/token',
            data={'grant_type': 'refresh_token', 'client_id': 'rhsm-api', 'refresh_token': offline_token},
            timeout=10
        )
        if r.status_code == 200:
            return r.json().get('access_token', '')
    except Exception as e:
        logger.warning(f"Token exchange failed: {e}")
    return ''

def fetch_sfdc_case_details_full(case_number: str, sfdc_token: str) -> dict:
    access_token = exchange_offline_token(sfdc_token) if sfdc_token else ''
    if not access_token:
        logger.warning("Could not obtain access token for SFDC case fetch")
        return {}
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    result = {}
    try:
        r = requests.get(f"{SFDC_API_BASE}/hydra/rest/cases/{case_number}", headers=headers, timeout=15)
        r.raise_for_status()
        result = r.json()
    except Exception as e:
        logger.warning(f"SFDC case fetch error: {e}")
    for ep in [f"/hydra/rest/cases/{case_number}/comments",
               f"/hydra/rest/cases/{case_number}/notes"]:
        try:
            r = requests.get(f"{SFDC_API_BASE}{ep}", headers=headers, timeout=15)
            if r.status_code == 200:
                result[f'_ep_{ep.split("/")[-1]}'] = r.json()
        except Exception:
            pass
    return result

def extract_linked_resources(description: str, comments_text: str) -> dict:
    all_text = (description or '') + '\n' + (comments_text or '')
    resources = {'kcs': [], 'jira': [], 'bugzilla': [], 'docs': []}
    seen_kcs: set = set()
    for m in re.finditer(r'https?://access\.redhat\.com/(?:solutions|articles)/\d+[^\s\)\"\'<>]*', all_text, re.IGNORECASE):
        url = m.group(0).rstrip('.,;)')
        if url not in seen_kcs:
            seen_kcs.add(url); resources['kcs'].append(url)
    seen_jira: set = set()
    for m in re.finditer(r'\b([A-Z]{2,10}-\d+)\b', all_text):
        key = m.group(1)
        if key not in seen_jira:
            seen_jira.add(key); resources['jira'].append({'key': key, 'url': f'https://redhat.atlassian.net/browse/{key}'})
    seen_bz: set = set()
    for m in re.finditer(r'https?://bugzilla\.redhat\.com/(?:show_bug\.cgi\?id=)?(\d+)', all_text, re.IGNORECASE):
        bug_id = m.group(1)
        if bug_id not in seen_bz:
            seen_bz.add(bug_id); resources['bugzilla'].append({'id': bug_id, 'url': m.group(0).rstrip('.,;)')})
    seen_docs: set = set()
    for m in re.finditer(r'https?://(?:docs\.openshift\.com|docs\.redhat\.com|access\.redhat\.com/documentation)[^\s\)\"\'<>]+', all_text, re.IGNORECASE):
        url = m.group(0).rstrip('.,;)')
        if url not in seen_docs:
            seen_docs.add(url); resources['docs'].append(url)
    return resources

def _chat_search_sop(question: str) -> tuple:
    try:
        search_fn, get_doc_fn = _get_asksre_fns()
        seen = {}
        for r in search_fn(problem_statement=question, max_results=15):
            if r.get("source") != "local_ops_sop": continue
            fp = r.get("file_path", "")
            if not fp: continue
            score = r.get("similarity", 0)
            if fp not in seen or score > seen[fp]["score"]:
                seen[fp] = {"score": score, "title": r.get("title", fp)}
        if not seen:
            return "", []
        top_docs = sorted(seen.items(), key=lambda x: x[1]["score"], reverse=True)[:2]
        parts, refs = [], []
        for fp, info in top_docs:
            gh_url = f"https://github.com/openshift/ops-sop/blob/master/{fp}"
            try:
                full = get_doc_fn(document_id=fp, source="local_ops_sop")
                content = (full.get("full_content") or "")[:4000]
            except Exception:
                content = ""
            if content:
                parts.append(f"### SOP: {info['title']}\nFile: {fp}\n\n{content}")
                refs.append({"title": info['title'], "url": gh_url, "type": "local_ops_sop"})
        return "\n\n---\n\n".join(parts), refs
    except Exception as e:
        logger.warning(f"Chat SOP search failed: {e}")
        return "", []

def _chat_search_kcs(question: str, sfdc_token: str) -> tuple:
    try:
        headers = {"Authorization": f"Bearer {sfdc_token}", "Content-Type": "application/json"}
        r = requests.get(
            f"{SFDC_API_BASE}/hydra/rest/search/v2/kcs",
            headers=headers,
            params={"q": question, "rows": 3},
            timeout=15
        )
        articles = r.json().get("articles", []) if r.status_code == 200 else []
        parts, refs = [], []
        for a in articles:
            title = a.get("title", "KCS Article")
            url   = a.get("url") or a.get("view_uri", "")
            if title and title != "No title":
                parts.append(f"### KCS: {title}")
                refs.append({"title": title, "url": url, "type": "kcs"})
        return "\n\n".join(parts), refs
    except Exception as e:
        logger.warning(f"Chat KCS search failed: {e}")
        return "", []

# ============================================================================
# PERSISTENT TOKEN STORAGE
# ============================================================================

def load_user_tokens(username):
    """Load tokens for a specific user from persistent storage"""
    try:
        if os.path.exists(TOKENS_FILE):
            with open(TOKENS_FILE, 'r') as f:
                all_tokens = json.load(f)
                return all_tokens.get(username, {})
    except Exception as e:
        logger.error(f"Error loading tokens for {username}: {e}")
    return {}

def save_user_tokens(username, tokens):
    """Save tokens for a specific user to persistent storage"""
    try:
        all_tokens = {}
        if os.path.exists(TOKENS_FILE):
            with open(TOKENS_FILE, 'r') as f:
                all_tokens = json.load(f)

        all_tokens[username] = tokens

        with open(TOKENS_FILE, 'w') as f:
            json.dump(all_tokens, f, indent=2)

        logger.info(f"Tokens saved to persistent storage for {username}")
        return True
    except Exception as e:
        logger.error(f"Error saving tokens for {username}: {e}")
        return False

def get_user_token_data(username):
    """Get all token data for a user"""
    tokens = load_user_tokens(username)
    return {
        'atlassian_email': tokens.get('atlassian_email', ''),
        'atlassian_token': tokens.get('atlassian_token', ''),
        'atlassian_token_expiry': tokens.get('atlassian_token_expiry', ''),
        'redhat_token': tokens.get('redhat_token', ''),
        'redhat_token_expiry': tokens.get('redhat_token_expiry', ''),
        'slack_xoxc': tokens.get('slack_xoxc', ''),
        'slack_xoxd': tokens.get('slack_xoxd', ''),
        'github_token': tokens.get('github_token', ''),
        'github_token_expiry': tokens.get('github_token_expiry', ''),
        'gitlab_token': tokens.get('gitlab_token', ''),
        'gitlab_url': tokens.get('gitlab_url', 'https://gitlab.cee.redhat.com'),
        'gitlab_token_expiry': tokens.get('gitlab_token_expiry', '')
    }

def update_user_token(username, token_key, token_value):
    """Update a specific token for a user"""
    tokens = load_user_tokens(username)
    tokens[token_key] = token_value
    save_user_tokens(username, tokens)

# ============================================================================
# SEARCH HISTORY STORAGE
# ============================================================================

def load_user_search_history(username):
    """Load search history for a specific user"""
    try:
        if os.path.exists(SEARCH_HISTORY_FILE):
            with open(SEARCH_HISTORY_FILE, 'r') as f:
                all_history = json.load(f)
                return all_history.get(username, [])
    except Exception as e:
        logger.error(f"Error loading search history for {username}: {e}")
    return []

def save_user_search_history(username, history):
    """Save search history for a specific user"""
    try:
        all_history = {}
        if os.path.exists(SEARCH_HISTORY_FILE):
            with open(SEARCH_HISTORY_FILE, 'r') as f:
                all_history = json.load(f)

        all_history[username] = history

        with open(SEARCH_HISTORY_FILE, 'w') as f:
            json.dump(all_history, f, indent=2)

        logger.info(f"Search history saved for user {username}")
    except Exception as e:
        logger.error(f"Error saving search history for {username}: {e}")

def add_search_to_history(username, query, results_count, sources):
    """Add a search to user's history (max 1 month retention)"""
    try:
        history = load_user_search_history(username)

        # Add new search at the beginning
        search_entry = {
            'query': query,
            'timestamp': datetime.now().isoformat(),
            'results_count': results_count,
            'sources': sources  # List of sources that returned results
        }

        history.insert(0, search_entry)

        # Keep only searches from last 30 days
        cutoff_date = datetime.now() - timedelta(days=30)
        history = [s for s in history if datetime.fromisoformat(s['timestamp']) > cutoff_date]

        # Limit to 500 most recent searches
        history = history[:500]

        save_user_search_history(username, history)
    except Exception as e:
        logger.error(f"Error adding search to history for {username}: {e}")

# ============================================================================
# KERBEROS AUTHENTICATION
# ============================================================================

def authenticate_kerberos(username, password):
    """
    Authenticate user with Kerberos.
    Returns (success: bool, message: str)
    """
    # Validate inputs
    if not username or not isinstance(username, str):
        logger.warning("Login attempt with empty or invalid username")
        return False, "Username is required"

    if not password or not isinstance(password, str):
        logger.warning(f"Login attempt with empty password for user: {username}")
        return False, "Password is required"

    # Sanitize username (only allow alphanumeric, underscore, dash)
    username = username.strip()
    if not username or not all(c.isalnum() or c in '_-' for c in username):
        logger.warning(f"Login attempt with invalid username format: {username}")
        return False, "Invalid username format"

    principal = f"{username}@{KERBEROS_REALM}"
    logger.info(f"Attempting Kerberos authentication for: {principal}")

    try:
        # Check if kinit is available
        kinit_check = subprocess.run(['which', 'kinit'], capture_output=True)
        if kinit_check.returncode != 0:
            logger.error("kinit not found - Kerberos authentication unavailable")
            return False, "Kerberos authentication not configured on this server"

        kinit_input = password + '\n'

        # Try --password-file first (works on macOS), fall back to stdin pipe (works on Fedora/RHEL)
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.tmp', delete=False) as f:
                f.write(kinit_input)
                tmpfile = f.name
            result = subprocess.run(
                ['kinit', '--password-file=' + tmpfile, principal],
                capture_output=True, text=True, timeout=30
            )
            os.unlink(tmpfile)
            if 'unrecognized option' in result.stderr:
                raise ValueError('password-file not supported')
            stdout, stderr = result.stdout, result.stderr
            process = result
        except (ValueError, Exception) as pf_err:
            if os.path.exists(tmpfile):
                os.unlink(tmpfile)
            logger.info(f"--password-file not supported, using stdin pipe: {pf_err}")
            process = subprocess.Popen(
                ['kinit', principal],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            stdout, stderr = process.communicate(input=kinit_input, timeout=30)
        if process.returncode == 0:
            logger.info(f"Kerberos authentication successful for {username}")
            subprocess.run(['kdestroy'], capture_output=True)
            return True, "Authentication successful"
        else:
            logger.warning(f"Kerberos authentication failed for {username}: {stderr.strip()}")
            return False, f"Kerberos error: {stderr.strip()}"

    except subprocess.TimeoutExpired:
        logger.error(f"Kerberos authentication timeout for {username}")
        return False, "Authentication timeout - please try again"
    except FileNotFoundError:
        logger.error("kinit command not found")
        return False, "Kerberos authentication not available"
    except Exception as e:
        logger.error(f"Kerberos authentication error for {username}: {str(e)}")
        return False, "Authentication error - please try again"


# ============================================================================
# BACKGROUND TOKEN VALIDATION
# ============================================================================

def validate_atlassian_token_background(username, email, token):
    """
    Background thread function to validate Atlassian token without blocking requests.
    Runs in a separate thread to avoid blocking the main request.
    """
    if not email or not token:
        logger.debug(f"Skipping Atlassian validation for {username} - missing email or token")
        return

    try:
        logger.info(f"Background: Validating Atlassian token for {username}")

        # Test token against Atlassian API using Basic Auth
        # Atlassian API tokens use: email as username, token as password
        test_response = requests.get(
            'https://api.atlassian.com/oauth/token/accessible-resources',
            headers={'Accept': 'application/json'},
            auth=(email, token),
            timeout=10
        )

        logger.debug(f"Atlassian API response status: {test_response.status_code}")

        if test_response.status_code == 401 or test_response.status_code == 403:
            # Token is revoked or invalid
            logger.warning(f"Atlassian token REVOKED/INVALID for {username} (HTTP {test_response.status_code})")

            # Clear the token from persistent storage
            update_user_token(username, 'atlassian_token', '')
            update_user_token(username, 'atlassian_token_expiry', '')
            update_user_token(username, 'atlassian_revoked', 'true')
            update_user_token(username, 'atlassian_revoked_date', datetime.now().strftime('%Y-%m-%d'))
            update_user_token(username, 'atlassian_revoked_reason', 'Token has been revoked or is invalid')

            logger.info(f"Cleared revoked Atlassian token for {username}")

        elif test_response.status_code == 200:
            # Token is valid
            logger.info(f"Atlassian token VALID for {username}")

            # Update last validated timestamp
            update_user_token(username, 'atlassian_last_validated',
                            datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

            # Clear any previous revocation flags
            update_user_token(username, 'atlassian_revoked', '')
            update_user_token(username, 'atlassian_revoked_date', '')
            update_user_token(username, 'atlassian_revoked_reason', '')

        else:
            # Unexpected status code - don't clear token, might be temporary API issue
            logger.warning(f"Unexpected Atlassian API status {test_response.status_code} for {username} - not clearing token")

    except requests.exceptions.Timeout:
        logger.warning(f"Atlassian API timeout for {username} - not clearing token (might be network issue)")
    except requests.exceptions.ConnectionError:
        logger.warning(f"Atlassian API connection error for {username} - not clearing token (might be network issue)")
    except Exception as e:
        logger.error(f"Atlassian token validation error for {username}: {type(e).__name__}: {e}")
        # Don't clear token on unexpected errors - could be temporary network/API issues

# ============================================================================
# STATIC FILE SERVING
# ============================================================================

@app.route('/seekrai_ui.css')
def serve_css():
    """Serve CSS file with cache busting"""
    response = send_file('src/seekrai_ui.css', mimetype='text/css')
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/seekrai_ui.js')
def serve_js():
    """Serve main JavaScript file"""
    return send_file('src/seekrai_ui.js', mimetype='application/javascript')

@app.route('/src/<path:filename>')
def serve_src_files(filename):
    """Serve files from src directory"""
    return send_from_directory('src', filename)

# ============================================================================
# AUTHENTICATION & PAGE ROUTES (with /seekr/ prefix)
# ============================================================================

@app.route('/seekr/login', methods=['GET', 'POST'])
def login():
    """Login page and authentication handler"""
    if request.method == 'GET':
        logger.info("Serving login page")
        return send_file('src/seekrai_loginPage.html')

    # POST - handle login with Kerberos authentication
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()

    if not username or not password:
        return jsonify({'success': False, 'message': 'Username and password required'}), 400

    # Authenticate with Kerberos
    success, message = authenticate_kerberos(username, password)

    if success:
        session['username'] = username
        session.permanent = True
        app.permanent_session_lifetime = timedelta(hours=8)

        # Load saved tokens from persistent storage into session
        saved_tokens = get_user_token_data(username)
        logger.info(f"DEBUG: Loading tokens for {username}: {list(saved_tokens.keys())}")
        logger.info(f"DEBUG: atlassian_token length: {len(saved_tokens.get('atlassian_token', ''))}")
        for key, value in saved_tokens.items():
            if value:  # Only load if value exists
                session[key] = value
                logger.info(f"DEBUG: Loaded {key} into session (length: {len(str(value))})")

        logger.info(f"User {username} logged in successfully, tokens loaded from storage")
        logger.info(f"DEBUG: Session now has atlassian_token: {session.get('atlassian_token', 'NOT SET')[:20]}...")
        return jsonify({'success': True, 'redirect': '/seekr/main'})
    else:
        logger.warning(f"Failed login attempt for user {username}")
        return jsonify({'success': False, 'message': message}), 401

@app.route('/seekr/logout')
def logout():
    """Logout and clear session"""
    username = session.get('username', 'unknown')
    session.clear()
    logger.info(f"User {username} logged out")
    return redirect('/seekr/login')

@app.route('/seekr/main')
@app.route('/seekr/')
@app.route('/')
@app.route('/main')
def main_page():
    """Main search page - requires authentication"""
    if 'username' not in session:
        logger.info("Attempted access to /seekr/main without authentication - redirecting to /seekr/login")
        return redirect('/seekr/login')
    logger.info(f"User {session['username']} accessing main page")
    return send_file('src/seekrai_ui.html')

@app.route('/seekr/settings')
def settings():
    """Settings page - requires authentication"""
    if 'username' not in session:
        logger.info("Attempted access to /seekr/settings without authentication - redirecting to /seekr/login")
        return redirect('/seekr/login')
    logger.info(f"User {session['username']} accessing settings page")
    return send_file('src/seekrai_settings.html')

# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.route('/api/user', methods=['GET'])
def get_user():
    """Get current user info with auto-generated email"""
    if 'username' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    username = session['username']
    # Auto-generate Red Hat email from Kerberos username
    email = f"{username}@redhat.com"

    return jsonify({
        'username': username,
        'email': email
    })

@app.route('/api/search', methods=['POST'])
def search():
    """Proxy search requests to unified_search.py backend"""
    if 'username' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    try:
        data = request.get_json()
        query = data.get('query', '')
        logger.info(f"Search request from {session['username']}: query='{query}'")

        # Prepare config with tokens from session (key names match user_tokens.json)
        config = {
            'redhat_token': session.get('redhat_token', ''),
            'atlassian_token': session.get('atlassian_token', ''),
            'atlassian_email': session.get('atlassian_email', ''),
            'slack_xoxc': session.get('slack_xoxc', ''),
            'slack_xoxd': session.get('slack_xoxd', ''),
            'github_token': session.get('github_token', ''),
            'gitlab_token': session.get('gitlab_token', ''),
            'gitlab_url': session.get('gitlab_url', 'https://gitlab.cee.redhat.com')
        }

        # Log token status
        token_status = []
        if config['redhat_token']: token_status.append('Red Hat: YES')
        else: token_status.append('Red Hat: NO')
        if config['atlassian_token']: token_status.append('Jira: YES')
        else: token_status.append('Jira: NO')
        if config['slack_xoxc'] and config['slack_xoxd']: token_status.append('Slack: YES')
        else: token_status.append('Slack: NO')
        if config['github_token']: token_status.append('GitHub: YES')
        else: token_status.append('GitHub: NO')
        if config['gitlab_token']: token_status.append('GitLab: YES')
        else: token_status.append('GitLab: NO')
        logger.info(f"Token status - {', '.join(token_status)}")

        # Get selected sources from request (if provided)
        sources = data.get('sources', None)
        if sources:
            logger.info(f"Searching selected sources: {sources}")

        # Get optional parameters from request
        slack_channels = data.get('slack_channels', None)
        max_results = data.get('max_results', 20)
        jira_created_after = data.get('jira_created_after', None)
        jira_created_before = data.get('jira_created_before', None)
        custom_jql = data.get('custom_jql', None)
        jira_search_logic = data.get('jira_search_logic', 'AND')

        if slack_channels:
            logger.info(f"Filtering Slack to channels: {slack_channels}")

        # Forward to backend search API
        response = requests.post(
            f'{UNIFIED_SEARCH_API}/search',
            json={
                'query': query,
                'config': config,
                'sources': sources,
                'slack_channels': slack_channels,
                'max_results': max_results,
                'jira_created_after': jira_created_after,
                'jira_created_before': jira_created_before,
                'custom_jql': custom_jql,
                'jira_search_logic': jira_search_logic,
            },
            headers={'X-Username': session.get('username', '')},
            timeout=60
        )

        if response.status_code == 200:
            logger.info(f"Search completed successfully for user {session['username']}")
            return jsonify(response.json())
        else:
            logger.error(f"Search backend error: {response.status_code}")
            return jsonify({'error': 'Search backend error'}), response.status_code

    except Exception as e:
        logger.error(f"Search error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/github-file-content', methods=['POST'])
def github_file_content():
    """Proxy GitHub file content request to backend"""
    if 'username' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    try:
        # Get request data and add GitHub token from session
        payload = request.get_json() or {}
        payload['config'] = {
            'github_token': session.get('github_token', '')
        }

        logger.info(f"GitHub file content request: repo={payload.get('repository')}, path={payload.get('path')}, token={'SET' if payload['config']['github_token'] else 'NOT SET'}")

        # Forward request to backend with token in body
        response = requests.post(
            f'{UNIFIED_SEARCH_API}/api/github-file-content',
            json=payload,
            headers={'X-Username': session.get('username', '')},
            timeout=30
        )
        return jsonify(response.json()), response.status_code
    except Exception as e:
        logger.error(f"GitHub file content error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/gitlab-file-content', methods=['POST'])
def gitlab_file_content():
    """Proxy GitLab file content request to backend"""
    if 'username' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    try:
        # Get request data and add GitLab token from session
        payload = request.get_json() or {}
        payload['config'] = {
            'gitlab_token': session.get('gitlab_token', ''),
            'gitlab_url': session.get('gitlab_url', 'https://gitlab.cee.redhat.com')
        }

        logger.info(f"GitLab file content request: project={payload.get('project_id')}, path={payload.get('path')}, token={'SET' if payload['config']['gitlab_token'] else 'NOT SET'}")

        # Forward request to backend with token in body
        response = requests.post(
            f'{UNIFIED_SEARCH_API}/api/gitlab-file-content',
            json=payload,
            headers={'X-Username': session.get('username', '')},
            timeout=30
        )
        return jsonify(response.json()), response.status_code
    except Exception as e:
        logger.error(f"GitLab file content error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/kcs-article-details', methods=['POST'])
def kcs_article_details():
    """Fetch full KCS article details including Environment and Resolution"""
    if 'username' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    try:
        data = request.get_json()
        article_id = data.get('id')

        if not article_id:
            return jsonify({'success': False, 'error': 'Missing article ID'}), 400

        # Forward to unified_search backend
        payload = {
            'id': article_id,
            'config': {
                'redhat_token': session.get('redhat_token', '')
            }
        }

        response = requests.post(
            'http://localhost:5500/api/kcs-article-details',
            json=payload,
            headers={'X-Username': session.get('username', '')},
            timeout=30
        )
        return jsonify(response.json()), response.status_code
    except Exception as e:
        logger.error(f"KCS article details error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/case-escalations/<case_number>', methods=['GET'])
def get_case_escalations(case_number):
    """Proxy request to get SFDC case external trackers (OHSS tickets) and related content"""
    if 'username' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    try:
        logger.info(f"Case escalations request from {session['username']}: case_number={case_number}")

        # Forward to backend API with username header
        headers = {
            'X-RedHat-Token': session.get('redhat_token', ''),
            'X-Username': session.get('username', '')
        }

        response = requests.get(
            f'{UNIFIED_SEARCH_API}/api/case-escalations/{case_number}',
            headers=headers,
            timeout=30
        )

        if response.status_code == 200:
            logger.info(f"Case escalations fetched successfully for {case_number}")
            return jsonify(response.json())
        else:
            logger.error(f"Case escalations backend error: {response.status_code}")
            return jsonify({'error': 'Backend error'}), response.status_code

    except Exception as e:
        logger.error(f"Case escalations error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/sfdc/case/<case_number>', methods=['GET'])
def get_sfdc_case_details(case_number):
    """Proxy request to get full SFDC case details (lazy loading)"""
    if 'username' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    try:
        logger.info(f"SFDC case details request from {session['username']}: case_number={case_number}")

        # Forward to backend API
        response = requests.get(
            f'{UNIFIED_SEARCH_API}/api/sfdc/case/{case_number}',
            headers={'X-Username': session.get('username', '')},
            timeout=10
        )

        if response.status_code == 200:
            logger.info(f"SFDC case details fetched successfully for {case_number}")
            return jsonify(response.json())
        else:
            logger.error(f"SFDC case details backend error: {response.status_code}")
            return jsonify({'error': 'Backend error'}), response.status_code

    except Exception as e:
        logger.error(f"SFDC case details error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/sfdc/case/<case_number>/related-content', methods=['GET'])
def get_sfdc_case_related_content(case_number):
    """Proxy request to get Related Content (KCS, Docs, Slack) from SFDC case comments"""
    if 'username' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    try:
        logger.info(f"SFDC Related Content request from {session['username']}: case_number={case_number}")

        response = requests.get(
            f'{UNIFIED_SEARCH_API}/api/sfdc/case/{case_number}/related-content',
            headers={'X-Username': session.get('username', '')},
            timeout=30
        )

        if response.status_code == 200:
            logger.info(f"SFDC Related Content fetched successfully for {case_number}")
            return jsonify(response.json())
        else:
            logger.error(f"SFDC Related Content backend error: {response.status_code}")
            return jsonify({'kcs_articles': [], 'redhat_docs': [], 'slack_threads': [], 'error': 'Backend error'}), response.status_code

    except Exception as e:
        logger.error(f"SFDC Related Content error: {str(e)}")
        return jsonify({'kcs_articles': [], 'redhat_docs': [], 'slack_threads': [], 'error': str(e)}), 500

@app.route('/api/jira-issue-links/<jira_key>', methods=['GET'])
def get_jira_issue_links(jira_key):
    """Proxy request to get Jira issue links and related content (KCS, Slack)"""
    if 'username' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    try:
        logger.info(f"Jira issue links request from {session['username']}: jira_key={jira_key}")

        response = requests.get(
            f'{UNIFIED_SEARCH_API}/api/jira-issue-links/{jira_key}',
            headers={'X-Username': session.get('username', '')},
            timeout=30
        )

        if response.status_code == 200:
            return jsonify(response.json())
        else:
            logger.error(f"Jira links backend error: {response.status_code}")
            return jsonify({'error': 'Backend error'}), response.status_code

    except Exception as e:
        logger.error(f"Jira links error: {str(e)}")
        return jsonify({'error': str(e)}), 500

# ============================================================================
# API TOKEN MANAGEMENT ENDPOINTS
# ============================================================================
# Consolidated section for all API token save/load/test endpoints
# Includes: Atlassian, Red Hat, Slack
# ============================================================================

# ----------------------------------------------------------------------------
# ATLASSIAN API TOKEN
# ----------------------------------------------------------------------------

@app.route('/api/settings/atlassian-token', methods=['GET', 'POST'])
def atlassian_token():
    """API endpoint to save/retrieve Atlassian API token with user-specified expiry date"""
    if 'username' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    if request.method == 'POST':
        data = request.get_json()
        email = data.get('email', '').strip()
        token = data.get('token', '').strip()
        expiry_date = data.get('expiry_date', '').strip()

        if not email or not token:
            return jsonify({
                'success': False,
                'message': 'Email and token are required'
            }), 400

        # If no expiry date provided, auto-calculate 90 days from now (Atlassian API tokens last 90 days)
        if not expiry_date:
            expiry_date = (datetime.now() + timedelta(days=90)).strftime('%Y-%m-%d')
            logger.info(f"Auto-calculated Atlassian token expiry: {expiry_date}")

        # Save to session
        session['atlassian_email'] = email
        session['atlassian_token'] = token
        session['atlassian_token_expiry'] = expiry_date

        # Save to persistent storage
        username = session['username']
        update_user_token(username, 'atlassian_email', email)
        update_user_token(username, 'atlassian_token', token)
        update_user_token(username, 'atlassian_token_expiry', expiry_date)

        logger.info(f"Atlassian token saved for user {username}, expires: {expiry_date}")
        return jsonify({
            'success': True,
            'message': f'Atlassian token saved successfully (expires: {expiry_date})'
        })

    else:  # GET
        token = session.get('atlassian_token', '')
        email = session.get('atlassian_email', '')
        expiry_date = session.get('atlassian_token_expiry', '')

        # Auto-populate email from Kerberos username if not already set
        if not email and 'username' in session:
            email = f"{session['username']}@redhat.com"

        if not token:
            return jsonify({
                'token': '',
                'email': email,  # Return auto-generated email even if no token
                'expiry_date': '',
                'days_remaining': None
            })

        # Check expiry
        if expiry_date:
            try:
                expiry_date_obj = datetime.strptime(expiry_date, '%Y-%m-%d').date()
                today = datetime.now().date()
                days_remaining = (expiry_date_obj - today).days

                if days_remaining < 0:
                    logger.warning(f"Atlassian token expired for user {session['username']}")
                    return jsonify({
                        'expired': True,
                        'message': 'Your Atlassian API token has expired. Please update it in Settings.'
                    })

                logger.info(f"Re-validating Atlassian token for {session['username']}")
                return jsonify({
                    'token': token,
                    'email': email,
                    'expiry_date': expiry_date,
                    'days_remaining': days_remaining
                })
            except ValueError:
                logger.error(f"Invalid expiry date format for Atlassian token: {expiry_date}")

        return jsonify({
            'token': token,
            'email': email,
            'expiry_date': expiry_date,
            'days_remaining': None
        })

@app.route('/api/settings/test-atlassian-token', methods=['POST'])
def test_atlassian_token():
    """Test Atlassian API token validity"""
    if 'username' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    data = request.get_json()
    email = data.get('email', '').strip()
    token = data.get('token', '').strip()

    if not email or not token:
        return jsonify({
            'valid': False,
            'message': '⚠️ Email and token required'
        }), 400

    logger.info(f"Testing Atlassian token for email: {email}")

    try:
        # Test against Red Hat's Atlassian Jira instance
        response = requests.get(
            'https://redhat.atlassian.net/rest/api/3/myself',
            auth=(email, token),
            timeout=10
        )

        logger.info(f"Jira API response status: {response.status_code}")

        if response.status_code == 200:
            user_info = response.json()
            logger.info(f"Atlassian token valid for {email}")
            return jsonify({
                'valid': True,
                'message': f"✅ Connected as {user_info.get('displayName', email)}",
                'user_info': user_info
            })
        elif response.status_code == 401:
            logger.warning(f"Atlassian token test failed for {email}: Invalid credentials")
            return jsonify({
                'valid': False,
                'message': '❌ Invalid credentials. Check your email and token.'
            }), 401
        else:
            return jsonify({
                'valid': False,
                'message': f'❌ Unexpected response: {response.status_code}'
            }), 400

    except requests.exceptions.Timeout:
        return jsonify({
            'valid': False,
            'message': '❌ Connection timeout. Please try again.'
        }), 408
    except Exception as e:
        logger.error(f"Atlassian token test error: {str(e)}")
        return jsonify({
            'valid': False,
            'message': '❌ Could not connect to Atlassian. Please check your network.'
        }), 400

# ----------------------------------------------------------------------------
# RED HAT API TOKEN
# ----------------------------------------------------------------------------

@app.route('/api/settings/redhat-token', methods=['GET', 'POST'])
def redhat_token():
    """API endpoint to save/retrieve Red Hat API token with user-specified expiry date"""
    if 'username' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    if request.method == 'POST':
        data = request.get_json()
        token = data.get('token', '').strip()
        expiry_date = data.get('expiry_date', '').strip()

        if not token:
            return jsonify({
                'success': False,
                'message': 'Token is required'
            }), 400

        # If no expiry date provided, auto-calculate 30 days from now
        if not expiry_date:
            expiry_date = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
            logger.info(f"Auto-calculated Red Hat token expiry: {expiry_date}")

        # Save to session
        session['redhat_token'] = token
        session['redhat_token_expiry'] = expiry_date

        # Save to persistent storage
        username = session['username']
        update_user_token(username, 'redhat_token', token)
        update_user_token(username, 'redhat_token_expiry', expiry_date)

        logger.info(f"Red Hat token saved for user {username}, expires: {expiry_date}")
        return jsonify({
            'success': True,
            'message': f'Red Hat token saved successfully (expires: {expiry_date})'
        })

    else:  # GET
        token = session.get('redhat_token', '')
        expiry_date = session.get('redhat_token_expiry', '')

        if not token:
            return jsonify({
                'token': '',
                'expiry_date': '',
                'days_remaining': None
            })

        # Check expiry
        if expiry_date:
            try:
                expiry_date_obj = datetime.strptime(expiry_date, '%Y-%m-%d').date()
                today = datetime.now().date()
                days_remaining = (expiry_date_obj - today).days

                if days_remaining < 0:
                    logger.warning(f"Red Hat token expired for user {session['username']}")
                    return jsonify({
                        'expired': True,
                        'message': 'Your Red Hat API token has expired. Please update it in Settings.'
                    })

                return jsonify({
                    'token': token,
                    'expiry_date': expiry_date,
                    'days_remaining': days_remaining
                })
            except ValueError:
                logger.error(f"Invalid expiry date format for Red Hat token: {expiry_date}")

        return jsonify({
            'token': token,
            'expiry_date': expiry_date,
            'days_remaining': None
        })

@app.route('/api/settings/test-redhat-token', methods=['POST'])
def test_redhat_token():
    """Test Red Hat API token validity"""
    if 'username' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    data = request.get_json()
    token = data.get('token', '').strip()

    if not token:
        return jsonify({
            'valid': False,
            'message': '⚠️ Token required'
        }), 400

    try:
        # First, exchange the refresh token for an access token
        sso_url = 'https://sso.redhat.com/auth/realms/redhat-external/protocol/openid-connect/token'
        payload = {
            'grant_type': 'refresh_token',
            'client_id': 'rhsm-api',
            'refresh_token': token
        }

        token_response = requests.post(sso_url, data=payload, timeout=10)

        if token_response.status_code != 200:
            return jsonify({
                'valid': False,
                'message': '❌ Invalid or expired token. Please generate a new one from access.redhat.com/management/api'
            }), 401

        token_data = token_response.json()
        access_token = token_data.get('access_token')

        if not access_token:
            return jsonify({
                'valid': False,
                'message': '❌ Could not obtain access token'
            }), 400

        # Now test the access token against SFDC API
        test_response = requests.post(
            'https://access.redhat.com/hydra/rest/search/v2/cases',
            headers={
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            },
            json={'q': 'test', 'rows': 1},
            timeout=10
        )

        if test_response.status_code == 200:
            return jsonify({
                'valid': True,
                'message': '✅ Token is valid! Successfully connected to Red Hat API (SFDC & KCS).'
            })
        else:
            return jsonify({
                'valid': False,
                'message': f'❌ Token exchange succeeded but API test failed: {test_response.status_code}'
            }), 400

    except requests.exceptions.Timeout:
        return jsonify({
            'valid': False,
            'message': '❌ Connection timeout. Please try again.'
        }), 408
    except Exception as e:
        logger.error(f"Red Hat token test error: {str(e)}")
        return jsonify({
            'valid': False,
            'message': '❌ Could not connect to Red Hat API. Please check your network.'
        }), 400

# ----------------------------------------------------------------------------
# SLACK API TOKENS
# ----------------------------------------------------------------------------

@app.route('/api/settings/slack-tokens', methods=['GET', 'POST'])
def slack_tokens():
    """API endpoint to save/retrieve Slack API tokens"""
    if 'username' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    if request.method == 'POST':
        data = request.get_json()
        xoxc = data.get('xoxc', '').strip()
        xoxd = data.get('xoxd', '').strip()

        if not xoxc or not xoxd:
            return jsonify({
                'success': False,
                'message': 'Both xoxc and xoxd tokens are required'
            }), 400

        # Save to session
        session['slack_xoxc'] = xoxc
        session['slack_xoxd'] = xoxd

        # Save to persistent storage
        username = session['username']
        update_user_token(username, 'slack_xoxc', xoxc)
        update_user_token(username, 'slack_xoxd', xoxd)

        logger.info(f"Slack tokens saved for user {username}")
        return jsonify({
            'success': True,
            'message': 'Slack tokens saved successfully'
        })

    else:  # GET
        return jsonify({
            'xoxc': session.get('slack_xoxc', ''),
            'xoxd': session.get('slack_xoxd', '')
        })

@app.route('/api/settings/test-slack-tokens', methods=['POST'])
def test_slack_tokens():
    """Test Slack API tokens validity"""
    if 'username' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    data = request.get_json()
    xoxc = data.get('xoxc', '').strip()
    xoxd = data.get('xoxd', '').strip()

    if not xoxc or not xoxd:
        return jsonify({
            'valid': False,
            'message': '⚠️ Both tokens required'
        }), 400

    try:
        # Test with a simple auth.test API call
        # xoxc tokens require the d cookie and token as form data
        response = requests.post(
            'https://slack.com/api/auth.test',
            headers={'Cookie': f'd={xoxd}'},
            data={'token': xoxc},
            timeout=10
        )

        logger.info(f"Slack auth.test: status={response.status_code}, body={response.text[:300]}")

        try:
            data = response.json()
        except Exception:
            if xoxc.startswith('xoxc-') and xoxd.startswith('xoxd-'):
                return jsonify({
                    'valid': True,
                    'message': '⚠️ Could not verify with Slack API (network issue), but token format is valid. Tokens should work.'
                })
            return jsonify({
                'valid': False,
                'message': '❌ Invalid token format. xoxc token must start with "xoxc-" and xoxd token must start with "xoxd-"'
            }), 400

        if data.get('ok'):
            return jsonify({
                'valid': True,
                'message': f"✅ Connected to {data.get('team', 'Slack workspace')}",
                'workspace_info': data
            })
        else:
            error = data.get('error', 'Unknown error')
            if error in ('invalid_auth', 'token_revoked', 'account_inactive'):
                return jsonify({
                    'valid': False,
                    'message': f"❌ Slack API error: {error}"
                }), 401
            if xoxc.startswith('xoxc-') and xoxd.startswith('xoxd-'):
                return jsonify({
                    'valid': True,
                    'message': f'⚠️ Slack API returned "{error}", but token format is valid. Tokens should work.'
                })
            return jsonify({
                'valid': False,
                'message': f"❌ Slack API error: {error}"
            }), 401

    except requests.exceptions.Timeout:
        if xoxc.startswith('xoxc-') and xoxd.startswith('xoxd-'):
            return jsonify({
                'valid': True,
                'message': '⚠️ Connection timeout, but token format is valid. Tokens should work.'
            })
        return jsonify({
            'valid': False,
            'message': '❌ Connection timeout. Please try again.'
        }), 408
    except Exception as e:
        logger.error(f"Slack token test error: {type(e).__name__}: {str(e)}")
        if xoxc.startswith('xoxc-') and xoxd.startswith('xoxd-'):
            return jsonify({
                'valid': True,
                'message': '⚠️ Could not verify with Slack API, but token format is valid. Tokens should work.'
            })
        return jsonify({
            'valid': False,
            'message': f'❌ Error: {str(e)}'
        }), 400

# ----------------------------------------------------------------------------
# GITHUB API TOKEN
# ----------------------------------------------------------------------------

@app.route('/api/settings/github-token', methods=['GET', 'POST'])
def github_token():
    """API endpoint to save/retrieve GitHub API token with expiry date"""
    if 'username' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    if request.method == 'POST':
        data = request.get_json()
        token = data.get('token', '').strip()
        expiry_date = data.get('expiry_date', '').strip()

        if not token:
            return jsonify({
                'success': False,
                'message': 'Token is required'
            }), 400

        # Validate GitHub token format
        if not (token.startswith('ghp_') or token.startswith('github_pat_')):
            return jsonify({
                'success': False,
                'message': 'Invalid GitHub token format. Must start with ghp_ or github_pat_'
            }), 400

        # If no expiry date provided, auto-calculate 90 days from now (GitHub classic tokens can be set to expire)
        if not expiry_date:
            expiry_date = (datetime.now() + timedelta(days=90)).strftime('%Y-%m-%d')
            logger.info(f"Auto-calculated GitHub token expiry: {expiry_date}")

        # Save to session
        session['github_token'] = token
        session['github_token_expiry'] = expiry_date

        # Save to persistent storage
        username = session['username']
        update_user_token(username, 'github_token', token)
        update_user_token(username, 'github_token_expiry', expiry_date)

        logger.info(f"GitHub token saved for user {username}, expires: {expiry_date}")
        return jsonify({
            'success': True,
            'message': f'GitHub token saved successfully (expires: {expiry_date})'
        })

    else:  # GET
        token = session.get('github_token', '')
        expiry_date = session.get('github_token_expiry', '')

        if not token:
            return jsonify({
                'token': '',
                'expiry_date': '',
                'days_remaining': None
            })

        # Check expiry
        if expiry_date:
            try:
                expiry_date_obj = datetime.strptime(expiry_date, '%Y-%m-%d').date()
                today = datetime.now().date()
                days_remaining = (expiry_date_obj - today).days

                if days_remaining < 0:
                    logger.warning(f"GitHub token expired for user {session['username']}")
                    return jsonify({
                        'expired': True,
                        'message': 'Your GitHub API token has expired. Please update it in Settings.'
                    })

                return jsonify({
                    'token': token,
                    'expiry_date': expiry_date,
                    'days_remaining': days_remaining
                })
            except ValueError:
                logger.error(f"Invalid expiry date format for GitHub token: {expiry_date}")

        return jsonify({
            'token': token,
            'expiry_date': expiry_date,
            'days_remaining': None
        })

@app.route('/api/settings/test-github-token', methods=['POST'])
def test_github_token():
    """Test GitHub API token validity"""
    if 'username' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    data = request.get_json()
    token = data.get('token', '').strip()

    if not token:
        return jsonify({
            'valid': False,
            'message': '⚠️ Token required'
        }), 400

    logger.info(f"Testing GitHub token")

    try:
        # Test against GitHub API user endpoint
        response = requests.get(
            'https://api.github.com/user',
            headers={
                'Authorization': f'token {token}',
                'Accept': 'application/vnd.github.v3+json'
            },
            timeout=10
        )

        logger.info(f"GitHub API response status: {response.status_code}")

        if response.status_code == 200:
            user_info = response.json()
            logger.info(f"GitHub token valid for user: {user_info.get('login')}")
            return jsonify({
                'valid': True,
                'message': f"✅ Connected as {user_info.get('login', 'GitHub User')}",
                'user_info': user_info
            })
        elif response.status_code == 401:
            logger.warning(f"GitHub token test failed: Invalid credentials")
            return jsonify({
                'valid': False,
                'message': '❌ Invalid token. Please check your token.'
            }), 401
        else:
            return jsonify({
                'valid': False,
                'message': f'❌ Unexpected response: {response.status_code}'
            }), 400

    except requests.exceptions.Timeout:
        return jsonify({
            'valid': False,
            'message': '❌ Connection timeout. Please try again.'
        }), 408
    except Exception as e:
        logger.error(f"GitHub token test error: {str(e)}")
        return jsonify({
            'valid': False,
            'message': '❌ Could not connect to GitHub API. Please check your network.'
        }), 400

# ----------------------------------------------------------------------------
# GITLAB API TOKEN
# ----------------------------------------------------------------------------

@app.route('/api/settings/gitlab-token', methods=['GET', 'POST'])
def gitlab_token():
    """API endpoint to save/retrieve GitLab API token with expiry date"""
    if 'username' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    if request.method == 'POST':
        data = request.get_json()
        token = data.get('token', '').strip()
        url = data.get('url', 'https://gitlab.cee.redhat.com').strip()
        expiry_date = data.get('expiry_date', '').strip()

        if not token:
            return jsonify({
                'success': False,
                'message': 'Token is required'
            }), 400

        # Validate token length (GitLab tokens vary in format)
        if len(token) < 10:
            return jsonify({
                'success': False,
                'message': 'GitLab token appears to be too short'
            }), 400

        # If no expiry date provided, auto-calculate 90 days from now (GitLab tokens can be set to expire)
        if not expiry_date:
            expiry_date = (datetime.now() + timedelta(days=90)).strftime('%Y-%m-%d')
            logger.info(f"Auto-calculated GitLab token expiry: {expiry_date}")

        # Save to session
        session['gitlab_token'] = token
        session['gitlab_url'] = url
        session['gitlab_token_expiry'] = expiry_date

        # Save to persistent storage
        username = session['username']
        update_user_token(username, 'gitlab_token', token)
        update_user_token(username, 'gitlab_url', url)
        update_user_token(username, 'gitlab_token_expiry', expiry_date)

        logger.info(f"GitLab token saved for user {username}, expires: {expiry_date}")
        return jsonify({
            'success': True,
            'message': f'GitLab token saved successfully (expires: {expiry_date})'
        })

    else:  # GET
        token = session.get('gitlab_token', '')
        url = session.get('gitlab_url', 'https://gitlab.cee.redhat.com')
        expiry_date = session.get('gitlab_token_expiry', '')

        if not token:
            return jsonify({
                'token': '',
                'url': url,
                'expiry_date': '',
                'days_remaining': None
            })

        # Check expiry
        if expiry_date:
            try:
                expiry_date_obj = datetime.strptime(expiry_date, '%Y-%m-%d').date()
                today = datetime.now().date()
                days_remaining = (expiry_date_obj - today).days

                if days_remaining < 0:
                    logger.warning(f"GitLab token expired for user {session['username']}")
                    return jsonify({
                        'expired': True,
                        'message': 'Your GitLab API token has expired. Please update it in Settings.'
                    })

                return jsonify({
                    'token': token,
                    'url': url,
                    'expiry_date': expiry_date,
                    'days_remaining': days_remaining
                })
            except ValueError:
                logger.error(f"Invalid expiry date format for GitLab token: {expiry_date}")

        return jsonify({
            'token': token,
            'url': url,
            'expiry_date': expiry_date,
            'days_remaining': None
        })

@app.route('/api/settings/test-gitlab-token', methods=['POST'])
def test_gitlab_token():
    """Test GitLab API token validity"""
    if 'username' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    data = request.get_json()
    token = data.get('token', '').strip()
    url = data.get('url', 'https://gitlab.cee.redhat.com').strip()

    if not token:
        return jsonify({
            'valid': False,
            'message': '⚠️ Token required'
        }), 400

    logger.info(f"Testing GitLab token for URL: {url}")

    try:
        # Test against GitLab API user endpoint
        response = requests.get(
            f'{url}/api/v4/user',
            headers={
                'PRIVATE-TOKEN': token
            },
            timeout=10,
            verify=False
        )

        logger.info(f"GitLab API response status: {response.status_code}")

        if response.status_code == 200:
            user_info = response.json()
            logger.info(f"GitLab token valid for user: {user_info.get('username')}")
            return jsonify({
                'valid': True,
                'message': f"✅ Connected as {user_info.get('username', 'GitLab User')}",
                'user_info': user_info
            })
        elif response.status_code == 401:
            logger.warning(f"GitLab token test failed: Invalid credentials")
            return jsonify({
                'valid': False,
                'message': '❌ Invalid token. Please check your token.'
            }), 401
        else:
            return jsonify({
                'valid': False,
                'message': f'❌ Unexpected response: {response.status_code}'
            }), 400

    except requests.exceptions.ConnectionError:
        return jsonify({
            'valid': False,
            'message': f'❌ Could not connect to {url}. Check the URL and your network.'
        }), 503
    except requests.exceptions.Timeout:
        return jsonify({
            'valid': False,
            'message': '❌ Connection timeout. Please try again.'
        }), 408
    except Exception as e:
        logger.error(f"GitLab token test error: {str(e)}")
        return jsonify({
            'valid': False,
            'message': '❌ Could not validate token. Please try again.'
        }), 400

# ----------------------------------------------------------------------------
# AI CONFIG SETTINGS
# ----------------------------------------------------------------------------

@app.route('/api/settings/ai-config', methods=['GET', 'POST'])
def ai_config_settings():
    """API endpoint to save/retrieve AI API configuration"""
    if 'username' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    username = session['username']

    if request.method == 'POST':
        data = request.get_json()
        ai_url = data.get('ai_url', '').strip()
        ai_token = data.get('ai_token', '').strip()

        if not ai_url:
            return jsonify({'success': False, 'message': 'API URL is required'}), 400

        update_user_token(username, 'ai_api_url', ai_url)
        if ai_token:
            update_user_token(username, 'ai_api_token', ai_token)
        logger.info(f"AI config saved for user {username}")
        return jsonify({'success': True, 'message': 'AI configuration saved successfully'})
    else:
        tokens = load_user_tokens(username)
        return jsonify({
            'ai_url': tokens.get('ai_api_url', CLAUDE_API_BASE),
            'has_token': bool(tokens.get('ai_api_token') or CLAUDE_USER_KEY)
        })


@app.route('/api/settings/test-ai-config', methods=['POST'])
def test_ai_config():
    """Test AI API connection with given URL and token"""
    if 'username' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    data = request.get_json()
    ai_url = (data.get('ai_url', '') or '').strip() or CLAUDE_API_BASE
    username = session['username']
    tokens = load_user_tokens(username)
    ai_token = (data.get('ai_token', '') or '').strip() or tokens.get('ai_api_token', '') or CLAUDE_USER_KEY

    if not ai_token:
        return jsonify({'valid': False, 'message': '⚠️ No API token configured'}), 400

    try:
        endpoint = f"{ai_url}/sonnet/models/{CLAUDE_MODEL_ID}:streamRawPredict"
        headers = {
            'Authorization': f'Bearer {ai_token}',
            'Content-Type': 'application/json',
        }
        payload = {
            'anthropic_version': 'vertex-2023-10-16',
            'max_tokens': 7,
            'temperature': 0,
            'messages': [
                {'role': 'user', 'content': [{'type': 'text', 'text': 'Say hi'}]}
            ]
        }
        verify = _SYSTEM_CA if os.path.exists(_SYSTEM_CA) else True
        resp = requests.post(endpoint, headers=headers, json=payload, timeout=20, verify=verify)
        if resp.status_code == 200:
            return jsonify({'valid': True, 'message': '✅ Connection successful — AI API is reachable and authenticated'})
        elif resp.status_code in (401, 403):
            return jsonify({'valid': False, 'message': '❌ Authentication failed — check your API token'})
        elif resp.status_code == 400:
            # 400 still means we reached the API (payload issue, not auth/network)
            return jsonify({'valid': True, 'message': f'✅ API is reachable (HTTP 400 — endpoint responded)'})
        else:
            body = resp.text[:200] if resp.text else ''
            return jsonify({'valid': False, 'message': f'⚠️ Unexpected response: HTTP {resp.status_code} — {body}'})
    except requests.exceptions.Timeout:
        return jsonify({'valid': False, 'message': '❌ Connection timed out — check the API URL'})
    except Exception as e:
        return jsonify({'valid': False, 'message': f'❌ Connection failed: {str(e)}'})


# ----------------------------------------------------------------------------
# SLACK DEFAULT CHANNELS SETTINGS
# ----------------------------------------------------------------------------

_DEFAULT_SLACK_CHANNELS = [
    'forum-rosa-support', 'openshift-sre', 'team-sre', 'sre-alerts',
    'sre-general', 'rosa-sre', 'osd-sre', 'forum-managed-openshift', 'ask-sre'
]

@app.route('/api/settings/slack-channels', methods=['GET', 'POST'])
def slack_channels_settings():
    """API endpoint to save/retrieve the list of default Slack channels"""
    if 'username' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    username = session['username']

    if request.method == 'POST':
        data = request.get_json()
        channels = data.get('channels', [])
        if not isinstance(channels, list):
            return jsonify({'success': False, 'message': 'channels must be a list'}), 400
        channels = [str(c).strip().lstrip('#') for c in channels if str(c).strip()]
        update_user_token(username, 'default_slack_channels', channels)
        logger.info(f"Slack channels saved for user {username}: {channels}")
        return jsonify({'success': True, 'message': f'Saved {len(channels)} channel(s) successfully'})
    else:
        tokens = load_user_tokens(username)
        channels = tokens.get('default_slack_channels', None)
        if channels is None:
            channels = _DEFAULT_SLACK_CHANNELS
        return jsonify({'channels': channels})


# ----------------------------------------------------------------------------
# TOKEN STATUS SUMMARY
# ----------------------------------------------------------------------------

@app.route('/api/settings/token-status', methods=['GET'])
def token_status():
    """API endpoint to get status of all saved tokens"""
    if 'username' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    def check_token_expiry(expiry_date_str):
        """Helper to check token expiry status"""
        if not expiry_date_str:
            return {'configured': True, 'expired': False, 'days_remaining': None}

        try:
            expiry_date = datetime.strptime(expiry_date_str, '%Y-%m-%d').date()
            today = datetime.now().date()
            days_remaining = (expiry_date - today).days
            return {
                'configured': True,
                'expired': days_remaining < 0,
                'days_remaining': days_remaining,
                'expiry_date': expiry_date_str
            }
        except ValueError:
            return {'configured': True, 'expired': False, 'days_remaining': None}

    # Check Atlassian token with 24-hour revalidation
    atlassian_status = {'configured': False, 'expired': False}
    username = session.get('username')

    if session.get('atlassian_token'):
        atlassian_status = check_token_expiry(session.get('atlassian_token_expiry', ''))

        # Check if token was revoked by background validation
        if username:
            tokens = load_user_tokens(username)

            if tokens.get('atlassian_revoked') == 'true':
                # Token was revoked - clear from session and notify user
                atlassian_status['revoked'] = True
                atlassian_status['revoked_date'] = tokens.get('atlassian_revoked_date', '')
                atlassian_status['revoked_reason'] = tokens.get('atlassian_revoked_reason', 'Token has been revoked')

                # Clear from session
                session.pop('atlassian_token', None)
                session.pop('atlassian_token_expiry', None)

                logger.info(f"Notifying user {username} about revoked Atlassian token")
            else:
                # Token exists and not revoked - check if we need to revalidate
                last_validated = tokens.get('atlassian_last_validated', '')

                # Check if we need to revalidate (24 hours since last check)
                should_validate = False
                if not last_validated:
                    should_validate = True
                else:
                    try:
                        last_validated_dt = datetime.strptime(last_validated, '%Y-%m-%d %H:%M:%S')
                        if datetime.now() - last_validated_dt > timedelta(hours=24):
                            should_validate = True
                    except ValueError:
                        should_validate = True

                # DISABLED: Background validation causes race conditions and file corruption
                # Instead, we rely on expiry date notifications only
                # User will be notified 7 days before token expires
                if False and should_validate:
                    # Run validation in background thread to avoid blocking the request
                    import threading
                    threading.Thread(
                        target=validate_atlassian_token_background,
                        args=(username, session.get('atlassian_email', ''), session.get('atlassian_token', '')),
                        daemon=True
                    ).start()
                    logger.info(f"Started background validation for {username}'s Atlassian token")
    else:
        # No token in session - check if there's a revocation notification to show
        if username:
            tokens = load_user_tokens(username)
            if tokens.get('atlassian_revoked') == 'true':
                atlassian_status['revoked'] = True
                atlassian_status['revoked_date'] = tokens.get('atlassian_revoked_date', '')
                atlassian_status['revoked_reason'] = tokens.get('atlassian_revoked_reason', 'Token has been revoked')

    status = {
        'atlassian': atlassian_status,
        'redhat': check_token_expiry(session.get('redhat_token_expiry', '')) if session.get('redhat_token') else {'configured': False, 'expired': False},
        'slack': {
            'configured': bool(session.get('slack_xoxc') and session.get('slack_xoxd')),
            'expired': False
        },
        'github': check_token_expiry(session.get('github_token_expiry', '')) if session.get('github_token') else {'configured': False, 'expired': False},
        'gitlab': check_token_expiry(session.get('gitlab_token_expiry', '')) if session.get('gitlab_token') else {'configured': False, 'expired': False}
    }

    logger.info(f"Token status for {session.get('username')}: {status}")
    return jsonify(status)

@app.route('/api/settings/dismiss-notification', methods=['POST'])
def dismiss_notification():
    """Dismiss a notification for current session"""
    if 'username' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    data = request.get_json()
    notification_type = data.get('type', '')

    if not notification_type:
        return jsonify({'success': False, 'message': 'Notification type required'}), 400

    # Store dismissed notifications in session
    if 'dismissed_notifications' not in session:
        session['dismissed_notifications'] = []

    if notification_type not in session['dismissed_notifications']:
        session['dismissed_notifications'].append(notification_type)

    return jsonify({'success': True})

# ============================================================================
# SEARCH HISTORY API
# ============================================================================

@app.route('/api/search/history', methods=['GET'])
def get_search_history():
    """Get user's search history (last 30 days)"""
    if 'username' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    username = session['username']
    history = load_user_search_history(username)

    return jsonify({'history': history, 'total': len(history)})

@app.route('/api/search/save-history', methods=['POST'])
def save_search_history():
    """Save a search to user's history"""
    if 'username' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    data = request.get_json()
    query = data.get('query', '').strip()
    results_count = data.get('results_count', 0)
    sources = data.get('sources', [])

    if not query:
        return jsonify({'success': False, 'message': 'Query is required'}), 400

    username = session['username']
    add_search_to_history(username, query, results_count, sources)

    return jsonify({'success': True, 'message': 'Search saved to history'})

@app.route('/seekr/recent')
def recent_searches_page():
    """Recent searches page"""
    if 'username' not in session:
        return redirect('/seekr/login')
    return send_file('src/seekrai_recentsearch.html')

# ============================================================================
# HEALTH CHECK
# ============================================================================

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'service': 'seekrai-ui'})

# ============================================================================
# MAIN
# ============================================================================

# ============================================================================
# AI CASE SUMMARY + CHAT ENDPOINTS
# ============================================================================

@app.route('/api/ai/case-summary', methods=['POST'])
def ai_case_summary():
    """Generate AI summary for an SFDC case using Claude + ask-sre RAG."""
    if 'username' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    try:
        body        = request.get_json()
        case_number = body.get('case_number', '').strip()
        case_data   = body.get('case_data', {})
        if not case_number:
            return jsonify({'error': 'case_number is required'}), 400

        username    = session.get('username', '')
        user_tokens = load_user_tokens(username)
        sfdc_token  = user_tokens.get('redhat_token', '') or os.getenv('RH_API_OFFLINE_TOKEN', '')

        details  = fetch_sfdc_case_details_full(case_number, sfdc_token) if sfdc_token else {}
        subject  = details.get('subject',         case_data.get('summary', 'Unknown'))
        desc     = details.get('description', '') or case_data.get('description', '') or ''
        status   = details.get('status',          case_data.get('status', ''))
        severity = details.get('severity',         case_data.get('severity', ''))
        product  = details.get('product',          case_data.get('product', ''))
        created  = details.get('createdDate',      details.get('created_date', ''))

        def _extract_comments(raw):
            if isinstance(raw, list): return raw
            if isinstance(raw, dict):
                for k in ('comment', 'comments', 'data', 'results', 'items', 'notes', 'workNotes'):
                    v = raw.get(k)
                    if isinstance(v, list) and v: return v
            return []

        comment_list = []
        for k in list(details.keys()):
            if k.startswith('_ep_'):
                comment_list += _extract_comments(details[k])
        if not comment_list:
            comment_list = _extract_comments(details.get('comments', {}))

        comments_text = ''
        for c in comment_list[:15]:
            body_txt = str(c.get('commentBody') or c.get('body') or c.get('text') or '')[:3000].strip()
            author = c.get('author', c.get('createdByName', 'Unknown'))
            is_public = c.get('public', c.get('isPublic', True))
            ctype = 'Customer' if is_public else 'SRE/Internal'
            if body_txt:
                comments_text += f"\n[{ctype} - {author}]:\n{body_txt}\n"

        linked_resources = extract_linked_resources(desc, comments_text)
        is_closed = status.lower().strip() in CLOSED_STATUSES

        def lr_text(lr):
            parts = []
            if lr['kcs']:      parts.append("KCS: " + ' | '.join(lr['kcs'][:5]))
            if lr['jira']:     parts.append("Jira: " + ', '.join(j['key'] for j in lr['jira'][:6]))
            if lr['bugzilla']: parts.append("Bugs: " + ', '.join(f"BZ-{b['id']}" for b in lr['bugzilla'][:5]))
            if lr['docs']:     parts.append("Docs: " + ' | '.join(lr['docs'][:3]))
            return '\n'.join(parts) if parts else '(none detected)'

        mode_label = 'CLOSED — post-mortem summary' if is_closed else f'OPEN ({status}) — analysis & suggestions'

        prompt = f"""You are an expert Red Hat SRE analyst. Case is {mode_label}.
Produce a structured summary in clean HTML only (no markdown, no code fences).

CASE: {case_number} | {status} | Severity {severity} | {product}
SUBJECT: {subject}
CREATED: {created}

CONVERSATION THREAD (customer ↔ SRE):
{comments_text if comments_text else '(no comments available)'}

RESOURCES LINKED IN THIS CASE:
{lr_text(linked_resources)}

CRITICAL INSTRUCTIONS:
- Preserve verbatim CLI commands exactly as written — wrap them in <pre><code> blocks. Do not paraphrase or shorten commands.
- Include the full customer ↔ SRE Q&A exchanges from the conversation thread.
- Mention specific flags, registry names, cluster names, version numbers exactly as they appear.

Produce these HTML sections using <h3> headings:

<h3>Case Overview</h3> 2-3 sentence summary of the issue and outcome/current state.

<h3>Key Error Messages / Commands Run</h3> Exact error messages, log lines, and CLI commands, each in its own <pre><code> block. If none, write <p>(none found)</p>.

<h3>Problem Analysis</h3> Technical facts as <ul><li>. Include specific values (error codes, components, versions, flags).

<h3>Customer Questions &amp; Engineer Answers</h3> <ul><li> for each Q&A pair from the conversation thread.

<h3>Root Cause &amp; Resolution</h3> <ul><li> with <strong>Confirmed</strong>/<em>Probable</em> labels.
{('<h3>Suggested Next Steps</h3> Actionable <ol><li> items for the SRE team based on similar cases and SOPs.' if not is_closed else '')}

<h3>Linked Resources</h3> <ul> with every KCS article, Jira ticket, Bugzilla bug found in the case.

<h3>Key Learnings</h3> What to watch for in similar cases. <ul><li>.

Use <code> for inline commands/values, <strong> for emphasis. Never invent details not present in the case."""

        html = call_claude_api(prompt, max_tokens=3500)
        if html == "__TIMEOUT__":
            return jsonify({'timeout': True, 'html': ''}), 200

        return jsonify({
            'mode': 'closed' if is_closed else 'open',
            'status': status,
            'linked_resources': linked_resources,
            'html': html,
            'case_number': case_number,
        })
    except Exception as e:
        logger.error(f"ai_case_summary error: {e}")
        import traceback; traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/ai/case-chat', methods=['POST'])
def ai_case_chat():
    """Follow-up chat about a case — searches ask-sre SOPs + KCS before answering."""
    if 'username' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    try:
        body         = request.get_json()
        case_number  = body.get('case_number', '')
        case_summary = body.get('case_summary', '')
        messages     = body.get('messages', [])
        question     = body.get('question', '').strip()
        if not question:
            return jsonify({'error': 'question is required'}), 400

        username    = session.get('username', '')
        user_tokens = load_user_tokens(username)
        sfdc_token  = user_tokens.get('redhat_token', '') or os.getenv('RH_API_OFFLINE_TOKEN', '')

        sop_ctx, sop_refs = "", []
        kcs_ctx, kcs_refs = "", []
        with ThreadPoolExecutor(max_workers=2) as ex:
            sop_f = ex.submit(_chat_search_sop, question)
            kcs_f = ex.submit(_chat_search_kcs, question, sfdc_token)
            try: sop_ctx, sop_refs = sop_f.result(timeout=20)
            except Exception as e: logger.warning(f"SOP search timeout: {e}")
            try: kcs_ctx, kcs_refs = kcs_f.result(timeout=20)
            except Exception as e: logger.warning(f"KCS search timeout: {e}")

        summary_text = re.sub(r'<[^>]+>', ' ', case_summary)
        summary_text = re.sub(r'\s+', ' ', summary_text).strip()[:2500]

        system_parts = [f"You are an expert Red Hat SRE analyst helping with SFDC case {case_number}."]
        if summary_text: system_parts.append(f"\nCASE ANALYSIS CONTEXT:\n{summary_text}")
        if sop_ctx:      system_parts.append(f"\nRELEVANT SRE SOPs:\n{sop_ctx}")
        if kcs_ctx:      system_parts.append(f"\nRELEVANT KCS ARTICLES:\n{kcs_ctx}")
        system_parts.append(
            "\nAnswer the user's question using case context and SOP/KCS docs above. "
            "Be concise and technical. Use HTML formatting (<p>, <ul>, <li>, <code>, <strong>) — no markdown."
        )
        system_ctx = "\n".join(p for p in system_parts if p)

        api_messages = []
        for msg in messages:
            api_messages.append({"role": msg['role'], "content": [{"type": "text", "text": str(msg['content'])}]})
        api_messages.append({"role": "user", "content": [{"type": "text", "text": question}]})

        if _is_cluster_investigation(question):
            sre_system = SRE_INVESTIGATOR_SYSTEM_PROMPT
            if case_number:
                sre_system = f"You are investigating SFDC case {case_number}.\n\n" + sre_system
            if sop_ctx:
                sre_system += f"\n\nRELEVANT SRE SOPs:\n{sop_ctx}"
            if kcs_ctx:
                sre_system += f"\n\nRELEVANT KCS ARTICLES:\n{kcs_ctx}"
            answer = call_claude_with_tools("", system=sre_system, messages=api_messages, max_tokens=4000)
        else:
            answer = call_claude_api("", system=system_ctx, messages=api_messages, max_tokens=2500, timeout=(10, 90))

        if answer == "__TIMEOUT__":
            return jsonify({'error': 'Claude API timed out — please try again'}), 200

        return jsonify({'answer': answer, 'refs': sop_refs + kcs_refs})
    except Exception as e:
        logger.error(f"ai_case_chat error: {e}")
        import traceback; traceback.print_exc()
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    print("=" * 70)
    print(" 🎨 SeekrAI - Unified Search Interface")
    print("=" * 70)
    print()
    print("✨ Starting SeekrAI Web UI Server")
    print()
    print("🔒 Authentication: Kerberos (IPA.REDHAT.COM)")

    # Verify kinit is available
    try:
        kinit_check = subprocess.run(['which', 'kinit'], capture_output=True)
        if kinit_check.returncode == 0:
            print("   ✓ Kerberos tools installed")
        else:
            print("   ⚠️  WARNING: kinit not found - authentication will fail!")
            print("   Install with: sudo dnf install krb5-workstation")
    except:
        print("   ⚠️  WARNING: Could not verify Kerberos installation")

    print()
    print("Open your browser:")
    print("  👉 http://localhost:5501/seekr/login")
    print()
    print("Main application:")
    print("  👉 http://localhost:5501/seekr/main")
    print()
    print("Settings page:")
    print("  👉 http://localhost:5501/seekr/settings")
    print()
    print("Press CTRL+C to stop")
    print()

    app.run(
        host='0.0.0.0',
        port=5501,
        debug=True
    )
