#!/usr/bin/env python3
"""
Unified Search Tool - Search across Jira, SFDC, and Slack simultaneously
Run with: python unified_search.py
Then open: http://localhost:5500
"""
from flask import Flask, render_template, request, jsonify, session
import requests
import subprocess
import json
import os
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import asyncio
from concurrent.futures import ThreadPoolExecutor

app = Flask(__name__, template_folder='templates_unified')
# Use a fixed secret key so sessions persist across restarts
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'unified-search-secret-key-change-in-production')
app.config['SESSION_TYPE'] = 'filesystem'  # Store sessions on disk
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)  # Session lasts 7 days

# ============================================================================
# Configuration with Environment Variable Fallback
# ============================================================================

# Default configuration - reads from environment variables
# If not set in environment, these will be None/empty
DEFAULT_CONFIG = {
    "jira_email": os.getenv("JIRA_EMAIL", ""),
    "jira_token": os.getenv("JIRA_API_TOKEN", ""),
    "jira_base_url": "https://redhat.atlassian.net/rest/api/3",  # Hardcoded for Red Hat
    "sfdc_token": os.getenv("RH_API_OFFLINE_TOKEN", ""),
    "slack_xoxc": os.getenv("SLACK_XOXC_TOKEN", ""),
    "slack_xoxd": os.getenv("SLACK_XOXD_TOKEN", ""),
    "slack_workspace_url": "https://redhat.enterprise.slack.com",  # Hardcoded for Red Hat
    "logs_channel_id": os.getenv("LOGS_CHANNEL_ID", ""),
}

SSO_URL = "https://sso.redhat.com/auth/realms/redhat-external/protocol/openid-connect/token"
SFDC_API_BASE = "https://access.redhat.com"

# Token cache for SFDC
_access_token = None
_token_expiry = None

# Persistent credentials file
CREDENTIALS_FILE = os.path.join(os.path.dirname(__file__), '.saved_credentials.json')


def load_saved_credentials():
    """Load saved credentials from file"""
    if os.path.exists(CREDENTIALS_FILE):
        try:
            with open(CREDENTIALS_FILE, 'r') as f:
                saved = json.load(f)
            print(f"✅ Loaded saved credentials from {CREDENTIALS_FILE}")
            return saved
        except Exception as e:
            print(f"⚠️  Failed to load saved credentials: {e}")
            return {}
    return {}


def save_credentials_to_file(config: Dict):
    """Save credentials to file for persistence"""
    try:
        # Only save non-empty credentials
        to_save = {k: v for k, v in config.items() if v}

        with open(CREDENTIALS_FILE, 'w') as f:
            json.dump(to_save, f, indent=2)

        # Set restrictive permissions (owner read/write only)
        os.chmod(CREDENTIALS_FILE, 0o600)

        print(f"💾 Saved credentials to {CREDENTIALS_FILE}")
        return True
    except Exception as e:
        print(f"⚠️  Failed to save credentials: {e}")
        return False


def get_config():
    """Get configuration from session or default environment variables"""
    if 'config' not in session:
        # Try to load saved credentials first
        saved_creds = load_saved_credentials()

        # Merge: env vars (lowest) -> saved file -> session (highest)
        config = DEFAULT_CONFIG.copy()
        config.update(saved_creds)

        session['config'] = config
        session.permanent = True
        session.modified = True
    return session['config']


def update_config(new_config: Dict):
    """Update configuration in session and optionally save to file"""
    config = get_config()
    config.update(new_config)
    session['config'] = config
    session.permanent = True
    session.modified = True

    # Debug logging
    print("\n" + "="*70)
    print("🔧 Configuration Updated:")
    for key, value in new_config.items():
        if 'token' in key.lower() or 'password' in key.lower():
            print(f"  {key}: {'***SET***' if value else 'NOT SET'}")
        else:
            print(f"  {key}: {value}")
    print("="*70 + "\n")


# ============================================================================
# SFDC Functions
# ============================================================================

def get_sfdc_access_token(config: Dict = None):
    """Get a valid SFDC access token, refreshing if necessary."""
    global _access_token, _token_expiry

    if _access_token and _token_expiry and datetime.now() < _token_expiry:
        return _access_token

    if config is None:
        config = {}
    sfdc_token = config.get("sfdc_token", "")

    # Debug logging
    print(f"🔍 SFDC Token: {'SET (len=' + str(len(sfdc_token)) + ')' if sfdc_token else 'NOT SET'}")

    if not sfdc_token:
        print("❌ SFDC token not configured")
        return None

    payload = {
        "grant_type": "refresh_token",
        "client_id": "rhsm-api",
        "refresh_token": sfdc_token
    }

    try:
        response = requests.post(SSO_URL, data=payload, timeout=30)
        response.raise_for_status()

        data = response.json()
        _access_token = data["access_token"]
        _token_expiry = datetime.now() + timedelta(seconds=data.get("expires_in", 900) - 60)

        return _access_token
    except Exception as e:
        print(f"SFDC token error: {e}")
        return None


def search_sfdc(query: str, max_results: int = 20, config: Dict = None) -> Dict:
    """Search SFDC cases"""
    try:
        token = get_sfdc_access_token(config)
        if not token:
            return {"cases": [], "total": 0, "error": "Authentication failed"}

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        data = {
            "q": query,
            "start": 0,
            "rows": max_results,
            "partnerSearch": False,
            "expression": "sort=case_lastModifiedDate%20desc&fl=case_createdByName%2Ccase_createdDate%2Ccase_lastModifiedDate%2Cid%2Curi%2Ccase_summary%2Ccase_status%2Ccase_product%2Ccase_version%2Ccase_number%2Ccase_severity"
        }

        # Retry up to 2 times for SSL errors
        for attempt in range(2):
            try:
                response = requests.post(
                    f"{SFDC_API_BASE}/hydra/rest/search/v2/cases",
                    headers=headers,
                    json=data,
                    timeout=30,
                    verify=True
                )
                response.raise_for_status()
                result = response.json()
                break  # Success, exit retry loop
            except requests.exceptions.SSLError as ssl_err:
                if attempt == 0:  # First attempt failed, retry once
                    print(f"SSL error on attempt {attempt + 1}, retrying... {ssl_err}")
                    continue
                else:  # Second attempt also failed
                    raise
        else:
            # This shouldn't happen, but just in case
            raise Exception("Failed after retries")

        cases = []
        if "response" in result and "docs" in result["response"]:
            for doc in result["response"]["docs"]:
                cases.append({
                    "case_number": doc.get("case_number", "N/A"),
                    "summary": doc.get("case_summary", "No summary"),
                    "status": doc.get("case_status", "Unknown"),
                    "severity": doc.get("case_severity", "N/A"),
                    "product": doc.get("case_product", "N/A"),
                    "url": f"https://access.redhat.com/support/cases/#/case/{doc.get('case_number', '')}"
                })

        return {
            "cases": cases,
            "total": result.get("response", {}).get("numFound", 0)
        }

    except Exception as e:
        print(f"SFDC search error: {e}")
        return {"cases": [], "total": 0, "error": str(e)}


# ============================================================================
# Jira Functions
# ============================================================================

def extract_text_from_adf(adf_content: Dict) -> str:
    """Extract plain text from Atlassian Document Format"""
    if not isinstance(adf_content, dict):
        return ""

    text_parts = []

    def extract_from_node(node):
        if isinstance(node, dict):
            if 'text' in node:
                text_parts.append(node['text'])
            if 'content' in node:
                for child in node['content']:
                    extract_from_node(child)
        elif isinstance(node, list):
            for item in node:
                extract_from_node(item)

    extract_from_node(adf_content)
    return ' '.join(text_parts)[:200]  # Limit to 200 chars


def search_jira(query: str, max_results: int = 20, config: Dict = None) -> Dict:
    """Search Jira issues"""
    if config is None:
        config = {}
    jira_email = config.get("jira_email", "")
    jira_token = config.get("jira_token", "")
    jira_base_url = config.get("jira_base_url", "https://redhat.atlassian.net/rest/api/3")

    # Debug logging
    print(f"🔍 Jira Search - Email: {jira_email}, Token: {'SET' if jira_token else 'NOT SET'}")

    if not jira_email or not jira_token:
        error_msg = "Jira credentials not configured"
        print(f"❌ Jira Search Failed: {error_msg}")
        return {"issues": [], "total": 0, "error": error_msg}

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    # Simple JQL query
    jql = f'text ~ "{query}" ORDER BY updated DESC'

    params = {
        "jql": jql,
        "maxResults": max_results,
        "fields": "key,summary,description,status,priority,updated,project"
    }

    try:
        response = requests.get(
            f"{jira_base_url}/search/jql",
            headers=headers,
            params=params,
            auth=(jira_email, jira_token),
            timeout=30
        )
        response.raise_for_status()
        data = response.json()

        issues = []
        for issue in data.get('issues', []):
            fields = issue['fields']

            description = fields.get('description', '')
            if isinstance(description, dict):
                description = extract_text_from_adf(description)

            issues.append({
                'key': issue['key'],
                'project': fields.get('project', {}).get('key', 'N/A'),
                'summary': fields.get('summary', 'N/A'),
                'status': fields.get('status', {}).get('name', 'N/A'),
                'priority': fields.get('priority', {}).get('name', 'N/A'),
                'description': description,
                'url': f"https://redhat.atlassian.net/browse/{issue['key']}"
            })

        return {
            "issues": issues,
            "total": len(issues)  # Use actual count of issues returned
        }

    except Exception as e:
        print(f"Jira search error: {e}")
        return {"issues": [], "total": 0, "error": str(e)}


# ============================================================================
# KCS Functions
# ============================================================================

def search_kcs(query: str, max_results: int = 20, config: Dict = None) -> Dict:
    """Search Red Hat KCS (Knowledge Centered Service) articles and solutions"""
    try:
        token = get_sfdc_access_token(config)
        if not token:
            return {"articles": [], "total": 0, "error": "Authentication failed"}

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        data = {
            "q": query,
            "rows": max_results,
            "expression": "sort=score%20DESC&fq=documentKind%3A(%22Article%22%20OR%20%22Solution%22)%20AND%20accessState%3A(%22active%22%20OR%20%22private%22)&fl=allTitle%2CcaseCount%2CdocumentKind%2Cid%2Cscore%2Curi%2Cresource_uri%2Cview_uri&showRetired=false",
            "start": 0,
            "clientName": "unified-search"
        }

        # Retry up to 2 times for SSL errors
        for attempt in range(2):
            try:
                response = requests.post(
                    f"{SFDC_API_BASE}/hydra/rest/search/v2/kcs",
                    headers=headers,
                    json=data,
                    timeout=30,
                    verify=True
                )
                response.raise_for_status()
                result = response.json()
                break
            except requests.exceptions.SSLError as ssl_err:
                if attempt == 0:
                    print(f"KCS SSL error on attempt {attempt + 1}, retrying... {ssl_err}")
                    continue
                else:
                    raise
        else:
            raise Exception("Failed after retries")

        articles = []
        if "response" in result and "docs" in result["response"]:
            for doc in result["response"]["docs"]:
                article = {
                    "id": doc.get("id", "N/A"),
                    "title": doc.get("allTitle", "No title"),
                    "document_kind": doc.get("documentKind", "Article"),
                    "score": doc.get("score", 0),
                    "view_uri": doc.get("view_uri", ""),
                    "url": doc.get("view_uri", "#")
                }
                articles.append(article)

        return {
            "articles": articles,
            "total": result.get("response", {}).get("numFound", 0)
        }

    except Exception as e:
        print(f"KCS search error: {e}")
        return {"articles": [], "total": 0, "error": str(e)}


# ============================================================================
# Slack Functions
# ============================================================================

# Common Slack channels for filtering
COMMON_SLACK_CHANNELS = [
    "forum-rosa-support",
    "openshift-sre",
    "team-sre",
    "sre-alerts",
    "sre-general",
    "rosa-sre",
    "osd-sre",
    "forum-managed-openshift",
    "ask-sre",
]

def search_slack(query: str, max_results: int = 100, channels: List[str] = None, config: Dict = None) -> Dict:
    """Search Slack via subprocess with optional channel filtering"""
    try:
        if config is None:
            config = {}
        slack_xoxc = config.get("slack_xoxc", "")
        slack_xoxd = config.get("slack_xoxd", "")
        slack_workspace_url = config.get("slack_workspace_url", "https://redhat.enterprise.slack.com")
        logs_channel_id = config.get("logs_channel_id", "")

        # If Slack credentials are not configured in session, fall back to environment
        if not slack_xoxc or not slack_xoxd:
            slack_xoxc = slack_xoxc or os.getenv("SLACK_XOXC_TOKEN", "")
            slack_xoxd = slack_xoxd or os.getenv("SLACK_XOXD_TOKEN", "")

        # Check if we have Slack credentials
        if not slack_xoxc or not slack_xoxd:
            return {
                "messages": [],
                "total": 0,
                "channels": COMMON_SLACK_CHANNELS,
                "error": "Slack credentials not configured. Please set SLACK_XOXC_TOKEN and SLACK_XOXD_TOKEN."
            }

        # Debug: Print credential status
        print(f"🔍 Slack Search Debug:")
        print(f"  XOXC Token: {'SET (' + slack_xoxc[:10] + '...' + slack_xoxc[-10:] + ')' if slack_xoxc else 'NOT SET'}")
        print(f"  XOXD Token: {'SET (' + slack_xoxd[:10] + '...' + slack_xoxd[-10:] + ')' if slack_xoxd else 'NOT SET'}")
        print(f"  Workspace: {slack_workspace_url}")

        # Build query with channel filter if needed
        search_query = query
        if channels and channels != ['ALL']:
            # Add channel filter to query (Slack syntax)
            if len(channels) == 1:
                # Single channel: "query in:#channel"
                search_query = f"{query} in:#{channels[0]}"
            else:
                # Multiple channels: "query in:#channel1 OR in:#channel2"
                channel_parts = " OR ".join([f"in:#{ch}" for ch in channels])
                search_query = f"{query} {channel_parts}"

        # Use same directory as unified_search.py for slack_search_standalone.py and .mcp.json
        current_dir = os.path.dirname(os.path.abspath(__file__))
        slack_script = os.path.join(current_dir, 'slack_search_standalone.py')

        # Use poetry to run the slack search (needs MCP SDK)
        # Check if we have poetry available
        import shutil
        poetry_cmd = shutil.which('poetry')

        if poetry_cmd:
            cmd = [
                "poetry", "run", "python", slack_script,
                search_query,
                "--limit", str(max_results),
                "--json"
            ]
        else:
            # Fallback to direct python (may fail if MCP not installed)
            cmd = [
                "python3", slack_script,
                search_query,
                "--limit", str(max_results),
                "--json"
            ]

        # Prepare environment with Slack credentials
        env = os.environ.copy()
        env['SLACK_XOXC_TOKEN'] = slack_xoxc
        env['SLACK_XOXD_TOKEN'] = slack_xoxd
        env['SLACK_WORKSPACE_URL'] = slack_workspace_url
        env['MCP_TRANSPORT'] = 'stdio'

        # Set logs channel ID if configured
        if logs_channel_id:
            env['LOGS_CHANNEL_ID'] = logs_channel_id

        # Debug: Print command being run
        print(f"  Command: {' '.join(cmd[:3])} ... (query: {search_query[:50]})")
        print(f"  Working dir: {current_dir}")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=current_dir,  # Run from finaltoolMay17 directory where .mcp.json exists
            env=env  # Pass environment variables with Slack credentials
        )

        # Debug: Print subprocess result
        print(f"  Return code: {result.returncode}")
        print(f"  STDOUT length: {len(result.stdout)}")
        print(f"  STDERR length: {len(result.stderr)}")
        if result.stderr:
            print(f"  STDERR: {result.stderr[:200]}")

        if result.returncode != 0:
            print(f"  ❌ Subprocess failed!")
            return {
                "messages": [],
                "total": 0,
                "channels": COMMON_SLACK_CHANNELS,
                "error": f"Search failed: {result.stderr}"
            }

        # Parse JSON output
        print(f"  Parsing output...")
        json_found = False
        for line in result.stdout.split('\n'):
            line = line.strip()
            if line.startswith('{'):
                json_found = True
                print(f"  Found JSON line: {line[:100]}...")
                data = json.loads(line)
                messages = data.get("messages", [])
                print(f"  ✅ Parsed {len(messages)} messages")
                return {
                    "messages": messages,
                    "total": len(messages),
                    "channels": COMMON_SLACK_CHANNELS
                }

        if not json_found:
            print(f"  ❌ No JSON found in output!")
            print(f"  Full STDOUT: {result.stdout[:500]}")

        return {"messages": [], "total": 0, "channels": COMMON_SLACK_CHANNELS, "error": "No JSON output"}

    except subprocess.TimeoutExpired:
        return {"messages": [], "total": 0, "channels": COMMON_SLACK_CHANNELS, "error": "Timeout"}
    except Exception as e:
        print(f"Slack search error: {e}")
        return {"messages": [], "total": 0, "channels": COMMON_SLACK_CHANNELS, "error": str(e)}


# ============================================================================
# Unified Search
# ============================================================================

def search_all(query: str, max_results_per_source: int = 20, slack_channels: List[str] = None, config: Dict = None) -> Dict:
    """Search all sources in parallel"""
    try:
        if config is None:
            config = {}

        with ThreadPoolExecutor(max_workers=4) as executor:
            # Submit all searches concurrently with config
            jira_future = executor.submit(search_jira, query, max_results_per_source, config)
            sfdc_future = executor.submit(search_sfdc, query, max_results_per_source, config)
            slack_future = executor.submit(search_slack, query, max_results_per_source, slack_channels, config)
            kcs_future = executor.submit(search_kcs, query, max_results_per_source, config)

            # Get results with error handling for each
            try:
                jira_results = jira_future.result()
            except Exception as e:
                print(f"❌ Jira search exception: {e}")
                jira_results = {"issues": [], "total": 0, "error": str(e)}

            try:
                sfdc_results = sfdc_future.result()
            except Exception as e:
                print(f"❌ SFDC search exception: {e}")
                sfdc_results = {"cases": [], "total": 0, "error": str(e)}

            try:
                slack_results = slack_future.result()
            except Exception as e:
                print(f"❌ Slack search exception: {e}")
                slack_results = {"messages": [], "total": 0, "channels": COMMON_SLACK_CHANNELS, "error": str(e)}

            try:
                kcs_results = kcs_future.result()
            except Exception as e:
                print(f"❌ KCS search exception: {e}")
                kcs_results = {"articles": [], "total": 0, "error": str(e)}

        return {
            "jira": jira_results,
            "sfdc": sfdc_results,
            "slack": slack_results,
            "kcs": kcs_results,
            "query": query
        }
    except Exception as e:
        print(f"❌ search_all exception: {e}")
        import traceback
        traceback.print_exc()
        raise


# ============================================================================
# Flask Routes
# ============================================================================

@app.route('/')
def index():
    """Render the main unified search page"""
    return render_template('unified_index.html')


@app.route('/debug')
def debug():
    """Render debug page for troubleshooting"""
    return render_template('debug.html')


@app.route('/api/config', methods=['GET'])
def get_config_status():
    """Get current configuration status (without exposing actual tokens)"""
    config = get_config()

    # Debug: Print what's in session
    print("\n🔍 DEBUG - Current Session Config:")
    for key, value in config.items():
        if 'token' in key.lower():
            print(f"  {key}: {'SET (len=' + str(len(value)) + ')' if value else 'NOT SET'}")
        else:
            print(f"  {key}: {value}")
    print()

    # Check if credentials are saved to file
    has_saved_file = os.path.exists(CREDENTIALS_FILE)

    # Return status of each credential (configured or not)
    status = {
        "jira": {
            "configured": bool(config.get("jira_email") and config.get("jira_token")),
            "email": config.get("jira_email", ""),
            "token_length": len(config.get("jira_token", "")),
            "has_env": bool(os.getenv("JIRA_EMAIL") and os.getenv("JIRA_API_TOKEN"))
        },
        "sfdc": {
            "configured": bool(config.get("sfdc_token")),
            "token_length": len(config.get("sfdc_token", "")),
            "has_env": bool(os.getenv("RH_API_OFFLINE_TOKEN"))
        },
        "slack": {
            "configured": bool(config.get("slack_xoxc") and config.get("slack_xoxd")),
            "has_env": bool(os.getenv("SLACK_XOXC_TOKEN") and os.getenv("SLACK_XOXD_TOKEN")),
            "workspace_url": config.get("slack_workspace_url", "https://redhat.enterprise.slack.com"),
            "logs_channel_id": config.get("logs_channel_id", "")
        },
        "has_saved_credentials": has_saved_file
    }

    return jsonify(status)


@app.route('/api/config', methods=['POST'])
def update_config_endpoint():
    """Update configuration with user-provided credentials"""
    data = request.json

    print("\n📥 Received config update request:")
    print(f"  Data keys: {list(data.keys())}")

    new_config = {}

    # Jira configuration
    if 'jira_email' in data:
        new_config['jira_email'] = data['jira_email']
        print(f"  ✓ Jira Email: {data['jira_email']}")
    if 'jira_token' in data:
        new_config['jira_token'] = data['jira_token']
        print(f"  ✓ Jira Token: {'SET (len=' + str(len(data['jira_token'])) + ')' if data['jira_token'] else 'EMPTY'}")

    # SFDC configuration
    if 'sfdc_token' in data:
        new_config['sfdc_token'] = data['sfdc_token']
        print(f"  ✓ SFDC Token: {'SET (len=' + str(len(data['sfdc_token'])) + ')' if data['sfdc_token'] else 'EMPTY'}")

    # Slack configuration
    if 'slack_xoxc' in data:
        new_config['slack_xoxc'] = data['slack_xoxc']
    if 'slack_xoxd' in data:
        new_config['slack_xoxd'] = data['slack_xoxd']
    if 'slack_workspace_url' in data:
        new_config['slack_workspace_url'] = data['slack_workspace_url']
    if 'logs_channel_id' in data:
        new_config['logs_channel_id'] = data['logs_channel_id']

    # Check if user wants to save credentials
    save_to_file = data.get('save_credentials', True)  # Default to True

    if not new_config:
        print("  ⚠️  No configuration provided!")
        return jsonify({
            "status": "error",
            "message": "No configuration data provided"
        }), 400

    update_config(new_config)

    # Save to file if requested
    if save_to_file:
        current_config = get_config()
        saved = save_credentials_to_file(current_config)
        saved_msg = "and saved to file" if saved else "but failed to save to file"
    else:
        saved_msg = "(not saved to file)"

    return jsonify({
        "status": "success",
        "message": f"Configuration updated successfully {saved_msg}",
        "updated_keys": list(new_config.keys()),
        "saved_to_file": save_to_file and saved
    })


@app.route('/api/config/reset', methods=['POST'])
def reset_config():
    """Reset configuration to environment variables"""
    session['config'] = DEFAULT_CONFIG.copy()
    session.modified = True

    return jsonify({
        "status": "success",
        "message": "Configuration reset to environment variables"
    })


@app.route('/api/config/clear-saved', methods=['POST'])
def clear_saved_credentials():
    """Clear saved credentials file"""
    try:
        if os.path.exists(CREDENTIALS_FILE):
            os.remove(CREDENTIALS_FILE)
            print(f"🗑️  Deleted saved credentials file: {CREDENTIALS_FILE}")
            message = "Saved credentials cleared successfully"
        else:
            message = "No saved credentials file found"

        # Also reset session to env vars
        session['config'] = DEFAULT_CONFIG.copy()
        session.modified = True

        return jsonify({
            "status": "success",
            "message": message
        })
    except Exception as e:
        print(f"❌ Error clearing saved credentials: {e}")
        return jsonify({
            "status": "error",
            "message": f"Failed to clear saved credentials: {str(e)}"
        }), 500


@app.route('/search', methods=['POST'])
def search():
    """Handle unified search requests"""
    try:
        data = request.json
        if not data:
            return jsonify({
                "error": "Invalid request: No JSON data",
                "jira": {"issues": [], "total": 0},
                "sfdc": {"cases": [], "total": 0},
                "slack": {"messages": [], "total": 0, "channels": COMMON_SLACK_CHANNELS},
                "kcs": {"articles": [], "total": 0}
            }), 400

        query = data.get('query', '').strip()
        max_results = int(data.get('max_results', 20))
        slack_channels = data.get('slack_channels', None)  # Optional channel filter for Slack

        print(f"\n🔍 Search Request: query='{query}', max_results={max_results}")

        if not query:
            return jsonify({
                "error": "Please enter a search query",
                "jira": {"issues": [], "total": 0},
                "sfdc": {"cases": [], "total": 0},
                "slack": {"messages": [], "total": 0, "channels": COMMON_SLACK_CHANNELS},
                "kcs": {"articles": [], "total": 0}
            })

        # Get config from session and pass it to search functions
        config = get_config()

        # Search all sources
        results = search_all(query, max_results, slack_channels, config)

        print(f"✅ Search completed: Jira={results.get('jira', {}).get('total', 0)}, "
              f"SFDC={results.get('sfdc', {}).get('total', 0)}, "
              f"Slack={results.get('slack', {}).get('total', 0)}, "
              f"KCS={results.get('kcs', {}).get('total', 0)}")

        return jsonify(results)

    except Exception as e:
        error_msg = f"Search error: {str(e)}"
        print(f"❌ {error_msg}")
        import traceback
        traceback.print_exc()

        return jsonify({
            "error": error_msg,
            "jira": {"issues": [], "total": 0, "error": str(e)},
            "sfdc": {"cases": [], "total": 0, "error": str(e)},
            "slack": {"messages": [], "total": 0, "channels": COMMON_SLACK_CHANNELS, "error": str(e)},
            "kcs": {"articles": [], "total": 0, "error": str(e)}
        }), 500


if __name__ == '__main__':
    os.makedirs('templates_unified', exist_ok=True)

    print("=" * 70)
    print(" 🔍 Unified Search - Jira + SFDC + Slack + KCS")
    print("=" * 70)
    print("\n✨ Search all four systems with one query!\n")
    print("Open your browser:")
    print("  👉 http://localhost:5500\n")
    print("Features:")
    print("  • Parallel search across Jira, SFDC, Slack, and KCS")
    print("  • Category filtering (show/hide each source)")
    print("  • Result counts in sidebar")
    print("  • Clean, unified interface\n")
    print("Press CTRL+C to stop")
    print("=" * 70 + "\n")

    app.run(debug=True, host='0.0.0.0', port=5500)
