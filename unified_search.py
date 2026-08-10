#!/usr/bin/env python3
"""
Unified Search Tool - Search across Jira, SFDC, and Slack simultaneously
Run with: python unified_search.py
Then open: http://localhost:5500
"""
from flask import Flask, render_template, request, jsonify, session
import requests
import requests.packages.urllib3
requests.packages.urllib3.disable_warnings(requests.packages.urllib3.exceptions.InsecureRequestWarning)
import subprocess
import json
import os
import re
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
    "atlassian_email": os.getenv("JIRA_EMAIL", ""),
    "atlassian_token": os.getenv("JIRA_API_TOKEN", ""),
    "jira_base_url": "https://redhat.atlassian.net/rest/api/3",  # Hardcoded for Red Hat
    "redhat_token": os.getenv("RH_API_OFFLINE_TOKEN", ""),
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

# Persistent credentials file (per-user token storage)
TOKENS_FILE = os.path.join(os.path.dirname(__file__), 'user_tokens.json')


def load_saved_credentials(username=''):
    """Load saved credentials from user_tokens.json for a specific user"""
    if not username or not os.path.exists(TOKENS_FILE):
        return {}
    try:
        with open(TOKENS_FILE, 'r') as f:
            all_tokens = json.load(f)
        user_tokens = all_tokens.get(username, {})
        if user_tokens:
            print(f"✅ Loaded saved credentials for user '{username}' from {TOKENS_FILE}")
        return user_tokens
    except Exception as e:
        print(f"⚠️  Failed to load saved credentials: {e}")
        return {}


def save_credentials_to_file(config: Dict, username=''):
    """Save credentials to user_tokens.json for a specific user"""
    if not username:
        print("⚠️  No username provided, skipping credential save")
        return False
    try:
        all_tokens = {}
        if os.path.exists(TOKENS_FILE):
            with open(TOKENS_FILE, 'r') as f:
                all_tokens = json.load(f)

        # Only save non-empty credentials for this user
        to_save = {k: v for k, v in config.items() if v}
        all_tokens[username] = to_save

        with open(TOKENS_FILE, 'w') as f:
            json.dump(all_tokens, f, indent=2)

        os.chmod(TOKENS_FILE, 0o600)

        print(f"💾 Saved credentials for user '{username}' to {TOKENS_FILE}")
        return True
    except Exception as e:
        print(f"⚠️  Failed to save credentials: {e}")
        return False


def get_config():
    """Get configuration from session or user_tokens.json"""
    if 'config' not in session:
        username = request.headers.get('X-Username', '')
        saved_creds = load_saved_credentials(username)

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
    redhat_token = config.get("redhat_token", "")

    # Debug logging
    print(f"🔍 Red Hat Token: {'SET (len=' + str(len(redhat_token)) + ')' if redhat_token else 'NOT SET'}")

    if not redhat_token:
        print("❌ Red Hat token not configured")
        return None

    payload = {
        "grant_type": "refresh_token",
        "client_id": "rhsm-api",
        "refresh_token": redhat_token
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
            # Only basic fields are available in search API - detailed fields require /cases/{id} endpoint
            "expression": "sort=score%20desc&fl=case_createdByName%2Ccase_createdDate%2Ccase_lastModifiedDate%2Cid%2Curi%2Ccase_summary%2Ccase_description%2Ccase_status%2Ccase_product%2Ccase_version%2Ccase_number%2Ccase_severity"
        }

        # No retries - fail fast when API is down
        try:
            response = requests.post(
                f"{SFDC_API_BASE}/hydra/rest/search/v2/cases",
                headers=headers,
                json=data,
                timeout=30,  # 30s timeout for SFDC search
                verify=True
            )

            # If 503 (Service Unavailable), fail immediately
            if response.status_code == 503:
                print(f"⚠️ SFDC API unavailable (503)")
                return {"cases": [], "total": 0, "error": "SFDC API temporarily unavailable"}

            response.raise_for_status()
            result = response.json()
        except requests.exceptions.Timeout:
            print(f"⚠️ SFDC API timeout (30s)")
            return {"cases": [], "total": 0, "error": "SFDC API timeout - try again later"}
        except requests.exceptions.HTTPError as http_err:
            status_code = http_err.response.status_code if http_err.response else 'Unknown'
            print(f"⚠️ SFDC API HTTP error: {status_code}")
            return {"cases": [], "total": 0, "error": f"SFDC API error ({status_code}) - Red Hat API is down"}
        except requests.exceptions.SSLError as ssl_err:
            print(f"⚠️ SFDC SSL error: {ssl_err}")
            return {"cases": [], "total": 0, "error": f"SSL error: {ssl_err}"}

        # Debug: Save first search result to see ALL available fields
        import json
        if "response" in result and "docs" in result["response"] and len(result["response"]["docs"]) > 0:
            with open('/tmp/sfdc_search_full.json', 'w') as f:
                f.write(json.dumps(result["response"]["docs"][0], indent=2))
            print(f"✓ Saved search result to /tmp/sfdc_search_full.json")

        cases = []
        if "response" in result and "docs" in result["response"]:
            for doc in result["response"]["docs"]:
                case_number = doc.get("case_number", "N/A")

                cases.append({
                    "case_number": case_number,
                    "summary": doc.get("case_summary", "No summary"),
                    "description": doc.get("case_description", ""),
                    "status": doc.get("case_status", "Unknown"),
                    "severity": doc.get("case_severity", "N/A"),
                    "product": doc.get("case_product", "N/A"),
                    "created_date": doc.get("case_createdDate", ""),
                    "last_modified_date": doc.get("case_lastModifiedDate", ""),
                    "owner": "N/A",
                    "account_number": "N/A",
                    "account_name": "N/A",
                    "internal_status": "N/A",
                    "sbt": "N/A",
                    "sbr": "N/A",
                    "urls": {
                        "caseview_plus": f"https://gss.my.salesforce.com/apex/Support#/cases/{case_number}",
                        "classic": f"https://gss--c.vf.force.com/apex/Case_View?sbstr={case_number}",
                        "customer_portal": f"https://access.redhat.com/support/cases/#/case/{case_number}"
                    }
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
            if node.get('type') == 'inlineCard' and 'attrs' in node and 'url' in node['attrs']:
                text_parts.append(node['attrs']['url'])
            if 'marks' in node:
                for mark in node['marks']:
                    if mark.get('type') == 'link' and 'attrs' in mark and 'href' in mark['attrs']:
                        href = mark['attrs']['href']
                        if href not in text_parts:
                            text_parts.append(href)
            if 'content' in node:
                for child in node['content']:
                    extract_from_node(child)
        elif isinstance(node, list):
            for item in node:
                extract_from_node(item)

    extract_from_node(adf_content)
    # Return full text with proper line breaks preserved
    full_text = '\n'.join(text_parts)
    return full_text


def search_jira(query: str, max_results: int = 20, config: Dict = None, created_after: str = None, created_before: str = None, custom_jql: str = None, search_logic: str = 'AND') -> Dict:
    """Search Jira issues with optional date filtering

    Args:
        query: Search query text
        max_results: Maximum number of results to return
        config: Configuration dictionary with credentials
        created_after: Filter issues created after this date (YYYY-MM-DD format)
        created_before: Filter issues created before this date (YYYY-MM-DD format)
    """
    if config is None:
        config = {}
    atlassian_email = config.get("atlassian_email", "")
    atlassian_token = config.get("atlassian_token", "")
    jira_base_url = config.get("jira_base_url", "https://redhat.atlassian.net/rest/api/3")

    # Debug logging
    print(f"🔍 Jira Search - Email: {atlassian_email}, Token: {'SET' if atlassian_token else 'NOT SET'}")

    if not atlassian_email or not atlassian_token:
        error_msg = "Jira credentials not configured"
        print(f"❌ Jira Search Failed: {error_msg}")
        return {"issues": [], "total": 0, "error": error_msg}

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    # Use custom JQL if provided, otherwise generate automatically
    if custom_jql:
        jql = custom_jql
        app.logger.info(f"🔍 Jira Custom JQL: {jql}")
        # Don't modify custom JQL - use it exactly as provided
    else:
        # Enhanced JQL query with multiple search strategies
        # 1. Check if query is a Jira key (e.g., OHSS-54143, SRE-1234)
        if '-' in query and query.replace('-', '').replace(' ', '').isalnum():
            # Looks like a Jira key, search by key first
            jql = f'key = "{query.strip()}" OR text ~ "{query}"'
            print(f"🔍 Jira JQL (key search): {jql}")
        else:
            # Regular text search with better word matching
            # Split query into words and search for any word match
            words = query.split()
            if len(words) > 1:
                significant_words = [word for word in words if len(word) > 2]
                separator = f' {search_logic} '
                word_conditions = separator.join([f'text ~ "{word}"' for word in significant_words])
                # OHSS tickets use OR logic so partial matches surface; other projects use the user's logic
                ohss_or_conditions = ' OR '.join([f'text ~ "{word}"' for word in significant_words])
                jql = f'(project = OHSS AND ({ohss_or_conditions})) OR ({word_conditions})'
                print(f"🔍 Jira JQL (multi-word, OHSS-boosted): {jql}")
            else:
                # Single word search
                jql = f'text ~ "{query}"'
                print(f"🔍 Jira JQL (single word): {jql}")

        # Add date filters if provided
        date_filters = []
        if created_after:
            date_filters.append(f'created >= "{created_after}"')
        if created_before:
            date_filters.append(f'created <= "{created_before}"')

        if date_filters:
            jql = f'{jql} AND {" AND ".join(date_filters)}'
            print(f"🔍 Jira JQL (with date filter): {jql}")

        # No ORDER BY — Jira returns text search results by relevance when unordered
        pass

    # End of if/else block for JQL generation

    try:
        from urllib.parse import urlencode
        from concurrent.futures import ThreadPoolExecutor

        def _jira_api_call(jql_query, limit):
            params = {"jql": jql_query, "maxResults": limit, "fields": "*all"}
            debug_url = f"{jira_base_url}/search/jql?{urlencode(params)}"
            app.logger.info(f"🌐 Jira API URL: {debug_url[:200]}...")
            resp = requests.get(f"{jira_base_url}/search/jql", headers=headers, params=params,
                                auth=(atlassian_email, atlassian_token), timeout=30)
            resp.raise_for_status()
            return resp.json()

        # Two parallel searches: OHSS-specific (OR logic) + general search
        words = query.split()
        significant_words = [w for w in words if len(w) > 2]
        if significant_words and len(words) > 1:
            ohss_or_conditions = ' OR '.join([f'text ~ "{w}"' for w in significant_words])
            ohss_jql = f'project = OHSS AND ({ohss_or_conditions})'
        elif significant_words:
            ohss_jql = f'project = OHSS AND text ~ "{query}"'
        else:
            ohss_jql = None

        with ThreadPoolExecutor(max_workers=2) as executor:
            general_future = executor.submit(_jira_api_call, jql, max_results)
            ohss_future = executor.submit(_jira_api_call, ohss_jql, max_results) if ohss_jql else None

        general_data = general_future.result()
        ohss_data = ohss_future.result() if ohss_future else {"issues": []}

        app.logger.info(f"📊 Jira general results: {len(general_data.get('issues', []))}, OHSS results: {len(ohss_data.get('issues', []))}")

        # Merge: OHSS results first, then general (deduplicate by key)
        seen_keys = set()
        all_raw_issues = []
        for issue in ohss_data.get('issues', []):
            key = issue.get('key', '')
            if key not in seen_keys:
                seen_keys.add(key)
                all_raw_issues.append(issue)
        for issue in general_data.get('issues', []):
            key = issue.get('key', '')
            if key not in seen_keys:
                seen_keys.add(key)
                all_raw_issues.append(issue)

        issues = []
        for issue in all_raw_issues:
            fields = issue['fields']

            # Debug: Print all field names for the first OHSS ticket to find custom field IDs
            if not issues and fields.get('project', {}).get('key') == 'OHSS':
                app.logger.info(f"📋 OHSS Ticket {issue['key']} - Available fields:")
                # Show specific fields we care about in full
                if fields.get('customfield_10868'):
                    app.logger.info(f"  customfield_10868 (Product): {fields.get('customfield_10868')}")
                if fields.get('issuetype'):
                    app.logger.info(f"  issuetype (Work Type?): {fields.get('issuetype')}")

            description = fields.get('description', '')
            if isinstance(description, dict):
                description = extract_text_from_adf(description)

            # Handle None values - Jira returns None for missing fields, not {}
            project = fields.get('project') or {}
            project_key = project.get('key', 'N/A')
            project_name = project.get('name', project_key)

            status = fields.get('status') or {}
            status_name = status.get('name', 'N/A')

            priority = fields.get('priority') or {}
            priority_name = priority.get('name', 'N/A')

            # Extract assignee
            assignee = fields.get('assignee') or {}
            assignee_name = assignee.get('displayName', 'Unassigned')

            # Extract reporter
            reporter = fields.get('reporter') or {}
            reporter_name = reporter.get('displayName', 'N/A')

            # Extract security level
            security = fields.get('security') or {}
            security_level = security.get('name', 'None')

            # Extract components
            components_list = fields.get('components', [])
            components = ', '.join([c.get('name', '') for c in components_list]) if components_list else 'None'

            # Extract custom fields
            # Work Type: Use issuetype (Task, Bug, Story, etc.)
            issuetype_obj = fields.get('issuetype') or {}
            if isinstance(issuetype_obj, dict):
                work_type = issuetype_obj.get('name', 'N/A')
            else:
                work_type = 'N/A'

            # Product: customfield_10868 (list of objects)
            product_list = fields.get('customfield_10868', [])
            if isinstance(product_list, list) and product_list:
                product = ', '.join([p.get('value', '') if isinstance(p, dict) else str(p) for p in product_list])
            elif isinstance(product_list, dict):
                product = product_list.get('value', 'N/A')
            else:
                product = 'N/A'

            issues.append({
                'key': issue['key'],
                'project': project_key,
                'project_name': project_name,
                'summary': fields.get('summary', 'N/A'),
                'status': status_name,
                'priority': priority_name,
                'description': description,
                'created': fields.get('created', 'N/A'),
                'updated': fields.get('updated', 'N/A'),
                'url': f"https://redhat.atlassian.net/browse/{issue['key']}",
                'is_ohss': project_key == 'OHSS',  # Flag for sorting
                'assignee': assignee_name,
                'reporter': reporter_name,
                'security_level': security_level,
                'components': components,
                'work_type': work_type,
                'product': product
            })

        app.logger.info(f"✅ Parsed {len(issues)} issues from Jira API")

        # Sort: OHSS tickets first, then by created date (newest first)
        # Use stable sort: first by date, then by project
        try:
            issues.sort(key=lambda x: x['created'], reverse=True)  # Step 1: newest first
            issues.sort(key=lambda x: 0 if x['is_ohss'] else 1)    # Step 2: OHSS first (stable sort)
            app.logger.info(f"✅ Sorted {len(issues)} issues successfully")
        except Exception as sort_err:
            app.logger.error(f"❌ Sorting failed: {sort_err}")
            # Don't fail - just return unsorted

        return {
            "issues": issues,
            "total": len(issues),  # Use actual count of issues returned
            "jql": jql  # Return the JQL query for display in UI
        }

    except Exception as e:
        app.logger.error(f"❌ Jira search error: {e}")
        import traceback
        app.logger.error(traceback.format_exc())
        return {"issues": [], "total": 0, "error": str(e), "jql": ""}


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
            "expression": "sort=score%20DESC&fq=documentKind%3A(%22Article%22%20OR%20%22Solution%22)%20AND%20accessState%3A(%22active%22%20OR%20%22private%22)&fl=allTitle%2CcaseCount%2CdocumentKind%2Cid%2Cscore%2Curi%2Cresource_uri%2Cview_uri%2Cenvironment%2Cissue%2Cresolution%2CverificationState%2CpublishState%2CmodifiedDate&showRetired=false",
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
                # Debug: Print all available fields for the first article
                if len(articles) == 0:
                    print(f"📋 KCS API fields available: {list(doc.keys())}")
                    print(f"🔍 Environment field: '{doc.get('environment')}'")
                    print(f"🔍 Issue field: '{doc.get('issue')}'")
                    print(f"🔍 Resolution field: '{doc.get('resolution')}'")
                    # Check for alternative field names
                    env_fields = [k for k in doc.keys() if 'env' in k.lower() or 'product' in k.lower() or 'platform' in k.lower()]
                    if env_fields:
                        print(f"🔍 Possible environment fields: {env_fields}")
                        for field in env_fields:
                            print(f"   - {field}: {doc.get(field)}")

                article = {
                    "id": doc.get("id", "N/A"),
                    "title": doc.get("allTitle", "No title"),
                    "document_kind": doc.get("documentKind", "Article"),
                    "score": doc.get("score", 0),
                    "view_uri": doc.get("view_uri", ""),
                    "url": doc.get("view_uri", "#"),
                    "environment": doc.get("environment", ""),
                    "issue": doc.get("issue", ""),
                    "resolution": doc.get("resolution", ""),
                    "verification_state": doc.get("verificationState", doc.get("publishState", "N/A")),
                    "publish_state": doc.get("publishState", "N/A"),
                    "modified_date": doc.get("modifiedDate", "N/A")
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
# SOP/Document Search Functions (ask-sre semantic search)
# ============================================================================

ASK_SRE_DIR = os.getenv("ASK_SRE_DIR", "/home/jayu/asksre/ask-sre")

# ask-sre MCP Server configuration (used by AI chat, not by SOP search)
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8000")
_mcp_session_id = None

def call_ask_sre(tool_name: str, arguments: Dict, timeout: int = 30) -> List[Dict]:
    """Call an ask-sre MCP tool via JSON-RPC over Streamable HTTP.
    Returns a list of result dicts on success, empty list on failure."""
    global _mcp_session_id

    mcp_endpoint = f"{MCP_SERVER_URL}/mcp/"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }

    def parse_sse_response(response_text):
        """Parse SSE-formatted response to extract JSON-RPC result"""
        for line in response_text.strip().split("\n"):
            if line.startswith("data: "):
                return json.loads(line[6:])
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            return None

    def initialize_session():
        """Perform MCP initialize handshake, return session ID"""
        init_resp = requests.post(mcp_endpoint, headers=headers, json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "seekrai-backend", "version": "1.0.0"}
            }
        }, timeout=timeout)
        session_id = init_resp.headers.get("Mcp-Session-Id", "")

        if session_id:
            notify_headers = {**headers, "Mcp-Session-Id": session_id}
            requests.post(mcp_endpoint, headers=notify_headers, json={
                "jsonrpc": "2.0",
                "method": "notifications/initialized"
            }, timeout=10)

        return session_id

    try:
        if not _mcp_session_id:
            _mcp_session_id = initialize_session()
            print(f"✅ ask-sre MCP session initialized: {_mcp_session_id[:20]}..." if _mcp_session_id else "⚠️ ask-sre: no session ID returned")

        call_headers = {**headers}
        if _mcp_session_id:
            call_headers["Mcp-Session-Id"] = _mcp_session_id

        resp = requests.post(mcp_endpoint, headers=call_headers, json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }, timeout=timeout)

        if resp.status_code == 400 or resp.status_code == 404:
            _mcp_session_id = initialize_session()
            call_headers["Mcp-Session-Id"] = _mcp_session_id
            resp = requests.post(mcp_endpoint, headers=call_headers, json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": arguments
                }
            }, timeout=timeout)

        parsed = parse_sse_response(resp.text)
        if not parsed:
            print("⚠️ ask-sre: could not parse response")
            return []

        if "error" in parsed:
            print(f"⚠️ ask-sre error: {parsed['error']}")
            return []

        content = parsed.get("result", {}).get("content", [])
        results = []
        for item in content:
            if item.get("type") == "text":
                try:
                    text_data = json.loads(item["text"])
                    if isinstance(text_data, list):
                        results.extend(text_data)
                    elif isinstance(text_data, dict):
                        results.append(text_data)
                except json.JSONDecodeError:
                    pass
        return results

    except requests.exceptions.ConnectionError:
        print("⚠️ ask-sre MCP server not reachable")
        return []
    except Exception as e:
        print(f"⚠️ ask-sre call error: {e}")
        return []


def _keyword_search_sop_db(query: str, limit: int = 20) -> List[Dict]:
    """Search ask-sre PostgreSQL directly for file paths and content matching query keywords.
    Prioritizes path matches over content-only matches."""
    try:
        query_words = [w.lower() for w in query.split() if len(w) > 2]
        if not query_words:
            return []

        # Build conditions for path matches and content matches
        path_conditions = " AND ".join(f"metadata->>'file_path' ILIKE '%{w}%'" for w in query_words)
        any_path_cond = " OR ".join(f"metadata->>'file_path' ILIKE '%{w}%'" for w in query_words)
        text_conditions = " AND ".join(f"document ILIKE '%{w}%'" for w in query_words)

        sql = f"""
        WITH ranked AS (
            SELECT DISTINCT ON (metadata->>'file_path', metadata->>'source')
                metadata->>'file_path' as file_path,
                metadata->>'source' as source,
                metadata->>'title' as title,
                metadata->>'file_name' as file_name,
                metadata->>'category' as category,
                metadata->>'severity' as severity,
                metadata->>'service_name' as service_name,
                LEFT(document, 500) as doc_text,
                CASE WHEN {path_conditions} THEN 2
                     WHEN {any_path_cond} THEN 1
                     ELSE 0 END as path_rank
            FROM sre_docs
            WHERE ({any_path_cond}) OR ({text_conditions})
            ORDER BY metadata->>'file_path', metadata->>'source'
        )
        SELECT file_path, source, title, file_name, category, severity, service_name, doc_text
        FROM ranked
        ORDER BY path_rank DESC
        LIMIT {limit};
        """

        result = subprocess.run(
            ["podman", "exec", "pgvector", "psql", "-U", "postgres", "-d", "ask_sre_db",
             "-t", "-A", "-F", "|||", "-c", sql],
            capture_output=True, text=True, timeout=10
        )

        if result.returncode != 0:
            print(f"⚠️ SOP keyword search DB error: {result.stderr[:200]}")
            return []

        results = []
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            parts = line.split("|||")
            if len(parts) >= 8:
                results.append({
                    "file_path": parts[0],
                    "source": parts[1],
                    "title": parts[2] or "No title",
                    "file_name": parts[3] or "",
                    "category": parts[4] or "",
                    "severity": parts[5] or "",
                    "service_name": parts[6] or "",
                    "summary": parts[7] or "",
                })

        print(f"✅ SOP keyword search: {len(results)} results from DB")
        return results

    except Exception as e:
        print(f"⚠️ SOP keyword search error: {e}")
        return []


# Inline Python script run under `poetry run` in the ask-sre venv
_SOP_SEARCH_SCRIPT = r"""
import sys, json

query = sys.argv[1]
max_results = int(sys.argv[2])

# Redirect stdout to stderr so ask_sre startup banners don't contaminate JSON output
_real_stdout = sys.stdout
sys.stdout = sys.stderr

term_map = [
    ("master node", "control plane"),
    ("master nodes", "control plane nodes"),
    ("worker node", "machine pool"),
    ("worker nodes", "machine pools"),
]
stop_words = {"how","to","the","a","an","on","in","for","of","is",
              "are","was","with","what","when","why","does","do","can"}

def expand(q):
    ql = q.lower()
    for src, dst in term_map:
        if src in ql and dst not in ql:
            return ql.replace(src, dst)
    return q

from ask_sre.mcp.main import search_sre_docs
try:
    from ask_sre.db.pgvector_db import PgVectorDB
    _pgvector_ok = True
except Exception:
    _pgvector_ok = False

expanded = expand(query)
queries = [query] if expanded == query else [query, expanded]
fetch_k = min(max_results * 3, 30)

ALLOWED_SOURCES = {"local_ops_sop", "managed_openshift_docs"}
seen = {}
for q in queries:
    for r in search_sre_docs(problem_statement=q, max_results=fetch_k):
        if r.get("source") not in ALLOWED_SOURCES:
            continue
        fp = r.get("file_path") or ""
        if not fp:
            continue
        dedup_key = r.get("source", "") + ":" + fp
        if dedup_key not in seen or r.get("similarity", 0) > seen[dedup_key].get("similarity", 0):
            seen[dedup_key] = r

if _pgvector_ok:
    kw_src = expanded if expanded != query else query
    keywords = [w for w in kw_src.lower().split() if len(w) > 3 and w not in stop_words]
    if keywords:
        try:
            db = PgVectorDB()
            conn = db.connect()
            cur = conn.cursor()
            conds = ["(metadata->>'file_path' ILIKE %s OR metadata->>'title' ILIKE %s)"] * len(keywords)
            params = []
            for w in keywords:
                params.extend([f"%{w}%", f"%{w}%"])
            cur.execute(
                "SELECT DISTINCT ON (metadata->>'file_path', metadata->>'source') metadata, document FROM sre_docs "
                "WHERE " + " AND ".join(conds) + " AND metadata->>'source' IN ('local_ops_sop', 'managed_openshift_docs') LIMIT 10",
                params
            )
            for row in cur.fetchall():
                m = row["metadata"]
                fp = m.get("file_path", "")
                src = m.get("source", "local_ops_sop")
                dedup_key = src + ":" + fp
                if fp and dedup_key not in seen:
                    seen[dedup_key] = {
                        "source": src,
                        "file_path": fp,
                        "title": m.get("title", fp),
                        "document_text": row.get("document", ""),
                        "similarity": 0.90,
                        "view_uri": "",
                    }
            conn.close()
        except Exception:
            pass

sops = sorted(seen.values(), key=lambda x: x.get("similarity", 0), reverse=True)
output = [
    {
        "id": r.get("file_path") or "N/A",
        "title": r.get("title", "No title"),
        "summary": (r.get("document_text") or "")[:400],
        "score": r.get("similarity", 0),
        "file_path": r.get("file_path", ""),
        "url": r.get("view_uri") or "",
        "source": r.get("source", "local_ops_sop"),
    }
    for r in sops
]
sys.stdout = _real_stdout
print(json.dumps(output))
"""


def search_sop(query: str, max_results: int = 20, config: Dict = None) -> Dict:
    """Search ops-sop docs via ask-sre semantic search (poetry run subprocess)."""
    try:
        result = subprocess.run(
            ["poetry", "run", "python3", "-c", _SOP_SEARCH_SCRIPT, query, str(min(max_results, 20))],
            capture_output=True, text=True, timeout=60,
            cwd=ASK_SRE_DIR
        )
        if result.returncode != 0:
            print(f"⚠️ SOP search stderr: {result.stderr[-500:]}")
            return {"sops": [], "total": 0, "error": result.stderr[-200:]}

        sops = json.loads(result.stdout)
        print(f"✅ ask-sre: Found {len(sops)} SOP results")
        return {"sops": sops, "total": len(sops)}

    except subprocess.TimeoutExpired:
        return {"sops": [], "total": 0, "error": "SOP search timed out"}
    except Exception as e:
        print(f"SOP search error: {e}")
        return {"sops": [], "total": 0, "error": str(e)}


# ============================================================================
# Slack Functions
# ============================================================================

_slack_user_cache = {}
_slack_usergroup_cache = None
_slack_channel_cache = {}

def _load_slack_usergroups(headers: dict, cookies: dict) -> dict:
    """Fetch all Slack user groups and cache them as {id: handle}."""
    global _slack_usergroup_cache
    if _slack_usergroup_cache is not None:
        return _slack_usergroup_cache
    _slack_usergroup_cache = {}
    try:
        resp = requests.get(
            "https://slack.com/api/usergroups.list",
            headers=headers, cookies=cookies, timeout=10
        )
        data = resp.json()
        if data.get('ok'):
            for group in data.get('usergroups', []):
                _slack_usergroup_cache[group['id']] = group.get('handle') or group.get('name', group['id'])
    except Exception:
        pass
    return _slack_usergroup_cache

def _resolve_slack_user_ids(text: str, slack_xoxc: str, slack_xoxd: str) -> str:
    """Replace <@USERID> and <!subteam^ID> mentions with display names."""
    headers = {'Authorization': f'Bearer {slack_xoxc}'}
    cookies = {'d': slack_xoxd}

    # Resolve user mentions: <@U...>
    user_ids = re.findall(r'<@(U[A-Z0-9]+)(?:\|[^>]*)?>', text)
    for uid in set(user_ids):
        if uid in _slack_user_cache:
            display_name = _slack_user_cache[uid]
        else:
            try:
                resp = requests.get(
                    "https://slack.com/api/users.info",
                    params={"user": uid},
                    headers=headers, cookies=cookies, timeout=10
                )
                data = resp.json()
                if data.get('ok'):
                    profile = data['user'].get('profile', {})
                    display_name = profile.get('display_name') or profile.get('real_name') or data['user'].get('name', uid)
                else:
                    display_name = uid
            except Exception:
                display_name = uid
            _slack_user_cache[uid] = display_name
        text = text.replace(f'<@{uid}>', f'<@{uid}|{display_name}>')

    # Resolve subteam/user group mentions: <!subteam^S...> or <@S...>
    subteam_ids = re.findall(r'<!subteam\^(S[A-Z0-9]+)(?:\|[^>]*)?>', text)
    subteam_ids += re.findall(r'<@(S[A-Z0-9]+)(?:\|[^>]*)?>', text)
    if subteam_ids:
        groups = _load_slack_usergroups(headers, cookies)
        for sid in set(subteam_ids):
            group_name = groups.get(sid, sid)
            text = text.replace(f'<!subteam^{sid}>', f'@{group_name}')
            text = text.replace(f'<@{sid}>', f'@{group_name}')

    # Resolve channel mentions: <#C...> without a name
    channel_ids = re.findall(r'<#(C[A-Z0-9]+)(?!\|)>', text)
    for cid in set(channel_ids):
        if cid in _slack_channel_cache:
            channel_name = _slack_channel_cache[cid]
        else:
            try:
                resp = requests.get(
                    "https://slack.com/api/conversations.info",
                    params={"channel": cid},
                    headers=headers, cookies=cookies, timeout=10
                )
                data = resp.json()
                if data.get('ok'):
                    channel_name = data['channel'].get('name', cid)
                else:
                    channel_name = cid
            except Exception:
                channel_name = cid
            _slack_channel_cache[cid] = channel_name
        text = text.replace(f'<#{cid}>', f'<#{cid}|{channel_name}>')

    return text


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
    print(f"🔔 Slack search called with query: '{query}', max_results: {max_results}")
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

        # Empty list means user deselected all channels — return nothing
        if channels is not None and len(channels) == 0:
            return {"messages": [], "total": 0, "channels": COMMON_SLACK_CHANNELS}

        # Build search query with optional channel filter (Slack's in:#channel syntax)
        search_query = query
        if channels and channels != ['ALL']:
            if len(channels) == 1:
                search_query = f"{query} in:#{channels[0]}"
            else:
                channel_parts = " OR ".join([f"in:#{ch}" for ch in channels])
                search_query = f"{query} {channel_parts}"
        print(f"  📝 Slack search query: {search_query}")

        # Use same directory as unified_search.py for slack_search_standalone.py and .mcp.json
        current_dir = os.path.dirname(os.path.abspath(__file__))
        slack_script = os.path.join(current_dir, 'slack_search_standalone.py')

        # Use direct python3 to run the slack search (MCP SDK is available in system Python)
        # Poetry is not set up in this directory
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
            cwd=current_dir,
            env=env
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
                print(f"  ✅ Parsed {len(messages)} messages from Slack API")

                # Prioritize messages from key channels (forum-*, sbr-*, mcs-*, itn-<number>)
                import re
                priority_pattern = re.compile(r'^(forum-|sbr-|mcs-|itn-\d)')

                def channel_priority(msg):
                    ch = msg.get('channel_name', msg.get('channel', ''))
                    return 0 if priority_pattern.match(ch) else 1

                filtered_messages = sorted(messages, key=channel_priority)
                all_channels = set()

                for msg in messages:
                    channel_name = msg.get('channel_name', msg.get('channel', ''))
                    all_channels.add(channel_name)

                # Resolve user, group, and channel mentions to display names
                for msg in filtered_messages:
                    msg_text = msg.get('text', '')
                    if '<@' in msg_text or '<!subteam' in msg_text or '<#C' in msg_text:
                        msg['text'] = _resolve_slack_user_ids(msg_text, slack_xoxc, slack_xoxd)

                # Log prioritization results
                priority_msgs = [m for m in filtered_messages if channel_priority(m) == 0]
                other_msgs = [m for m in filtered_messages if channel_priority(m) == 1]
                print(f"  📋 All channels found: {sorted(all_channels)}")
                print(f"  ⭐ Priority channels (forum-/sbr-/mcs-/itn-): {len(priority_msgs)} messages")
                for m in priority_msgs[:5]:
                    print(f"     → #{m.get('channel_name', m.get('channel', '?'))}")
                print(f"  📄 Other channels: {len(other_msgs)} messages")
                print(f"📊 Slack search completed: {len(filtered_messages)} messages ({len(priority_msgs)} prioritized)")

                return {
                    "messages": filtered_messages,
                    "total": len(filtered_messages),
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


def fetch_slack_thread(channel_id: str, thread_ts: str, config: Dict = None) -> Dict:
    """
    Fetch all replies in a Slack thread using conversations.replies API

    Args:
        channel_id: Channel ID (e.g., 'C1234567890')
        thread_ts: Thread timestamp (e.g., '1234567890.123456')
        config: Configuration dict with Slack credentials

    Returns:
        Dict with 'messages' list and 'total' count
    """
    print(f"🧵 Fetching Slack thread: channel={channel_id}, thread_ts={thread_ts}")
    try:
        if config is None:
            config = {}

        slack_xoxc = config.get("slack_xoxc", os.getenv("SLACK_XOXC_TOKEN", ""))
        slack_xoxd = config.get("slack_xoxd", os.getenv("SLACK_XOXD_TOKEN", ""))

        if not slack_xoxc or not slack_xoxd:
            return {
                "messages": [],
                "total": 0,
                "error": "Slack credentials not configured"
            }

        # Use Slack Web API to fetch thread
        url = "https://slack.com/api/conversations.replies"
        headers = {
            "Authorization": f"Bearer {slack_xoxc}",
            "Cookie": f"d={slack_xoxd}",
            "Content-Type": "application/json"
        }

        params = {
            "channel": channel_id,
            "ts": thread_ts,
            "limit": 100  # Max 100 replies per request
        }

        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        if not data.get("ok"):
            error_msg = data.get("error", "Unknown error")
            print(f"❌ Slack API error: {error_msg}")
            return {
                "messages": [],
                "total": 0,
                "error": f"Slack API error: {error_msg}"
            }

        messages = data.get("messages", [])
        print(f"✅ Fetched {len(messages)} messages in thread")

        # Format messages for frontend
        formatted_messages = []
        for msg in messages:
            text = msg.get("text", "")
            if '<@' in text or '<!subteam' in text or '<#C' in text:
                text = _resolve_slack_user_ids(text, slack_xoxc, slack_xoxd)

            user_id = msg.get("user", "Unknown")
            if user_id and re.match(r'^[A-Z0-9]+$', user_id):
                if user_id in _slack_user_cache:
                    user_display = _slack_user_cache[user_id]
                else:
                    try:
                        resp = requests.get(
                            "https://slack.com/api/users.info",
                            params={"user": user_id},
                            headers={"Authorization": f"Bearer {slack_xoxc}"},
                            cookies={"d": slack_xoxd}, timeout=10
                        )
                        udata = resp.json()
                        if udata.get('ok'):
                            profile = udata['user'].get('profile', {})
                            user_display = profile.get('display_name') or profile.get('real_name') or udata['user'].get('name', user_id)
                        else:
                            user_display = user_id
                    except Exception:
                        user_display = user_id
                    _slack_user_cache[user_id] = user_display
            else:
                user_display = user_id

            formatted_messages.append({
                "text": text,
                "user": user_display,
                "ts": msg.get("ts", ""),
                "timestamp": datetime.fromtimestamp(float(msg.get("ts", "0"))).strftime("%Y-%m-%d %H:%M:%S") if msg.get("ts") else "",
                "thread_ts": msg.get("thread_ts", thread_ts),
                "is_parent": msg.get("ts") == thread_ts,
                "reply_count": msg.get("reply_count", 0)
            })

        return {
            "messages": formatted_messages,
            "total": len(formatted_messages)
        }

    except Exception as e:
        print(f"❌ Slack thread fetch error: {e}")
        return {
            "messages": [],
            "total": 0,
            "error": str(e)
        }


# ============================================================================
# GitLab Search
# ============================================================================

GITLAB_GROUPS = ['mcs', 'service']

def search_gitlab(query: str, max_results: int = 20, config: Dict = None) -> Dict:
    """Search GitLab mcs and service group repos using project-level blob search (file content)."""
    try:
        if config is None:
            config = {}

        gitlab_token = config.get('gitlab_token', os.getenv('GITLAB_TOKEN', ''))
        gitlab_url = config.get('gitlab_url', 'https://gitlab.cee.redhat.com')

        print(f"🔍 GitLab Search: query='{query}', url={gitlab_url}, token={'SET' if gitlab_token else 'NOT SET'}")

        if not gitlab_token:
            return {'results': [], 'total': 0, 'error': 'GitLab token not configured. Add it in Settings.'}

        if len(query.strip()) < 3:
            return {'results': [], 'total': 0, 'error': 'Search query must be at least 3 characters'}

        headers = {'PRIVATE-TOKEN': gitlab_token}
        results = []

        # Step 1: Get projects from all configured groups
        projects = []
        for group in GITLAB_GROUPS:
            group_url = f'{gitlab_url}/api/v4/groups/{group}/projects'
            try:
                resp = requests.get(group_url, headers=headers, params={'per_page': 50, 'simple': 'true', 'order_by': 'last_activity_at'}, timeout=15, verify=False)
                if resp.status_code == 200:
                    group_projects = resp.json()
                    projects.extend(group_projects)
                    print(f"📊 GitLab: Found {len(group_projects)} projects in {group} group")
                else:
                    print(f"⚠️ GitLab: Failed to list {group} projects: {resp.status_code}")
            except Exception as e:
                print(f"⚠️ GitLab: Error listing {group} projects: {e}")

        if not projects:
            return {'results': [], 'total': 0, 'error': 'No projects found in mcs/service groups'}

        print(f"📊 GitLab: Searching file content across {len(projects)} total projects...")

        # Step 2: Search file content in each project using project-level blob search (parallel)
        def search_project_blobs(project):
            proj_id = project.get('id')
            proj_path = project.get('path_with_namespace', '')
            proj_name = project.get('name_with_namespace', project.get('name', ''))
            default_branch = project.get('default_branch', 'main')

            try:
                search_url = f'{gitlab_url}/api/v4/projects/{proj_id}/search'
                resp = requests.get(search_url, headers=headers,
                                    params={'scope': 'blobs', 'search': query, 'per_page': 5},
                                    timeout=10, verify=False)
                if resp.status_code != 200:
                    return []

                proj_results = []
                for blob in resp.json():
                    file_path = blob.get('path', blob.get('filename', ''))
                    filename = file_path.split('/')[-1] if file_path else ''
                    ref = blob.get('ref', default_branch)
                    file_url = f"{gitlab_url}/{proj_path}/-/blob/{ref}/{file_path}"

                    proj_results.append({
                        'filename': filename,
                        'path': file_path,
                        'project_id': proj_id,
                        'project_name': proj_name,
                        'ref': ref,
                        'url': file_url,
                        'summary': blob.get('data', '')[:300],
                        'startline': blob.get('startline', 0),
                        'priority': True,
                    })
                return proj_results
            except Exception:
                return []

        from concurrent.futures import as_completed
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = {executor.submit(search_project_blobs, p): p for p in projects}
            for future in as_completed(futures):
                proj_results = future.result()
                if proj_results:
                    results.extend(proj_results)
                if len(results) >= max_results:
                    break

        results = results[:max_results]
        print(f"✅ GitLab: Found {len(results)} results across mcs projects")
        return {'results': results, 'total': len(results)}

    except requests.exceptions.ConnectionError:
        print(f"❌ GitLab: Cannot connect to {gitlab_url}")
        return {'results': [], 'total': 0, 'error': f'Cannot connect to {gitlab_url}'}
    except Exception as e:
        print(f"❌ GitLab search error: {e}")
        import traceback
        traceback.print_exc()
        return {'results': [], 'total': 0, 'error': str(e)}


# ============================================================================
# Unified Search
# ============================================================================

def search_all(query: str, max_results_per_source: int = 20, slack_channels: List[str] = None, config: Dict = None,
               jira_created_after: str = None, jira_created_before: str = None, custom_jql: str = None, search_logic: str = 'AND') -> Dict:
    """Search all sources in parallel"""
    try:
        if config is None:
            config = {}

        with ThreadPoolExecutor(max_workers=6) as executor:
            # Submit all searches concurrently with config
            jira_future = executor.submit(search_jira, query, max_results_per_source, config, jira_created_after, jira_created_before, custom_jql, search_logic)
            sfdc_future = executor.submit(search_sfdc, query, max_results_per_source, config)
            slack_future = executor.submit(search_slack, query, max_results_per_source, slack_channels, config)
            kcs_future = executor.submit(search_kcs, query, max_results_per_source, config)
            sop_future = executor.submit(search_sop, query, max_results_per_source, config)
            gitlab_future = executor.submit(search_gitlab, query, max_results_per_source, config)

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

            try:
                sop_results = sop_future.result()
            except Exception as e:
                print(f"❌ SOP search exception: {e}")
                sop_results = {"sops": [], "total": 0, "error": str(e)}

            # GitHub results (ops-sop) and OpenShift Docs come from ask-sre SOP merge below
            github_results = {"results": [], "total": 0}
            docs_results = {"results": [], "total": 0}

            try:
                gitlab_results = gitlab_future.result()
            except Exception as e:
                print(f"❌ GitLab search exception: {e}")
                gitlab_results = {"results": [], "total": 0, "error": str(e)}

        # Merge ask-sre SOP results by source type
        if sop_results.get("sops"):
            for sop in sop_results["sops"]:
                source_type = sop.get("source", "")
                doc_text = sop.get("summary", "")[:300]

                if source_type == "local_ops_sop":
                    github_results["results"].append({
                        "name": sop.get("file_name", sop.get("title", "")),
                        "path": sop.get("file_path", ""),
                        "repository": "openshift/ops-sop",
                        "url": f"https://github.com/openshift/ops-sop/blob/master/{sop.get('file_path', '')}",
                        "language": "Markdown",
                        "ask_sre": True,
                        "similarity": sop.get("score", 0),
                        "summary": doc_text,
                        "title": sop.get("title", sop.get("file_name", "")),
                    })
                elif source_type == "managed_openshift_docs":
                    docs_results["results"].append({
                        "name": sop.get("file_name", sop.get("title", "")),
                        "path": sop.get("file_path", ""),
                        "repository": "openshift/openshift-docs",
                        "url": f"https://github.com/openshift/openshift-docs/blob/main/{sop.get('file_path', '')}",
                        "language": "AsciiDoc",
                        "ask_sre": True,
                        "similarity": sop.get("score", 0),
                        "summary": doc_text,
                        "title": sop.get("title", sop.get("file_name", "")),
                    })
                elif source_type == "redhat_customer_portal":
                    kcs_results.setdefault("articles", []).append({
                        "id": sop.get("id", ""),
                        "title": sop.get("title", "No title"),
                        "abstract": doc_text,
                        "url": "",
                        "ask_sre": True,
                        "similarity": sop.get("score", 0),
                        "category": sop.get("category", ""),
                    })

            # Update totals
            github_results["total"] = len(github_results["results"])
            docs_results["total"] = len(docs_results["results"])
            gitlab_results["total"] = len(gitlab_results.get("results", []))
            kcs_results["total"] = len(kcs_results.get("articles", []))

        return {
            "jira": jira_results,
            "sfdc": sfdc_results,
            "slack": slack_results,
            "kcs": kcs_results,
            "sop": sop_results,
            "github": github_results,
            "docs": docs_results,
            "gitlab": gitlab_results,
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
    has_saved_file = os.path.exists(TOKENS_FILE)

    # Return status of each credential (configured or not)
    status = {
        "jira": {
            "configured": bool(config.get("atlassian_email") and config.get("atlassian_token")),
            "email": config.get("atlassian_email", ""),
            "token_length": len(config.get("atlassian_token", "")),
            "has_env": bool(os.getenv("JIRA_EMAIL") and os.getenv("JIRA_API_TOKEN"))
        },
        "sfdc": {
            "configured": bool(config.get("redhat_token")),
            "token_length": len(config.get("redhat_token", "")),
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
    if 'atlassian_email' in data:
        new_config['atlassian_email'] = data['atlassian_email']
        print(f"  ✓ Atlassian Email: {data['atlassian_email']}")
    if 'atlassian_token' in data:
        new_config['atlassian_token'] = data['atlassian_token']
        print(f"  ✓ Atlassian Token: {'SET (len=' + str(len(data['atlassian_token'])) + ')' if data['atlassian_token'] else 'EMPTY'}")

    # Red Hat / SFDC configuration
    if 'redhat_token' in data:
        new_config['redhat_token'] = data['redhat_token']
        print(f"  ✓ Red Hat Token: {'SET (len=' + str(len(data['redhat_token'])) + ')' if data['redhat_token'] else 'EMPTY'}")

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
    """Clear saved credentials for the current user"""
    try:
        username = request.headers.get('X-Username', '')
        if not username:
            return jsonify({"status": "error", "message": "No username provided"}), 400

        if os.path.exists(TOKENS_FILE):
            with open(TOKENS_FILE, 'r') as f:
                all_tokens = json.load(f)
            if username in all_tokens:
                del all_tokens[username]
                with open(TOKENS_FILE, 'w') as f:
                    json.dump(all_tokens, f, indent=2)
                print(f"🗑️  Cleared credentials for user '{username}'")
                message = f"Credentials cleared for user '{username}'"
            else:
                message = f"No saved credentials found for user '{username}'"
        else:
            message = "No saved credentials file found"

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


@app.route('/api/sop-details', methods=['POST'])
def get_sop_details():
    """Get detailed SOP information via ask-sre semantic search"""
    try:
        data = request.json
        sop_id = data.get('sop_id')
        query = data.get('query', 'troubleshooting')

        if not sop_id:
            return jsonify({"error": "sop_id is required"}), 400

        results = call_ask_sre("search_sre_docs", {
            "problem_statement": query,
            "max_results": 1
        })

        if results:
            return jsonify(results[0])
        else:
            return jsonify({"error": "No SOP details found"}), 404

    except Exception as e:
        error_msg = f"Error fetching SOP details: {str(e)}"
        print(f"❌ {error_msg}")
        return jsonify({"error": error_msg}), 500


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
                "kcs": {"articles": [], "total": 0},
                "sop": {"sops": [], "total": 0}
            }), 400

        query = data.get('query', '').strip()
        max_results = int(data.get('max_results', 20))
        slack_channels = data.get('slack_channels', None)  # Optional channel filter for Slack
        jira_created_after = data.get('jira_created_after', None)  # Optional date filter for Jira
        jira_created_before = data.get('jira_created_before', None)  # Optional date filter for Jira
        custom_jql = data.get('custom_jql', None)  # Optional custom JQL for Jira
        jira_search_logic = data.get('jira_search_logic', 'AND')  # Search logic: AND or OR (default: AND)

        print(f"\n🔍 Search Request: query='{query}', max_results={max_results}, "
              f"jira_dates={jira_created_after or 'N/A'} to {jira_created_before or 'N/A'}, "
              f"custom_jql={'YES' if custom_jql else 'NO'}")

        if not query:
            return jsonify({
                "error": "Please enter a search query",
                "jira": {"issues": [], "total": 0},
                "sfdc": {"cases": [], "total": 0},
                "slack": {"messages": [], "total": 0, "channels": COMMON_SLACK_CHANNELS},
                "kcs": {"articles": [], "total": 0},
                "sop": {"sops": [], "total": 0}
            })

        # Get config from request body (sent by frontend proxy) or fall back to session
        config = data.get('config', None)
        if not config:
            config = get_config()

        # Debug: Check what tokens are in config
        print(f"🔑 Config tokens: GitHub={'SET' if config.get('github_token') else 'NOT SET'}, "
              f"GitLab={'SET' if config.get('gitlab_token') else 'NOT SET'}, "
              f"Slack XOXC={'SET' if config.get('slack_xoxc') else 'NOT SET'}, "
              f"Slack XOXD={'SET' if config.get('slack_xoxd') else 'NOT SET'}")

        # Search all sources
        results = search_all(query, max_results, slack_channels, config, jira_created_after, jira_created_before, custom_jql, jira_search_logic)

        print(f"✅ Search completed: Jira={results.get('jira', {}).get('total', 0)}, "
              f"SFDC={results.get('sfdc', {}).get('total', 0)}, "
              f"Slack={results.get('slack', {}).get('total', 0)}, "
              f"KCS={results.get('kcs', {}).get('total', 0)}, "
              f"SOP={results.get('sop', {}).get('total', 0)}")

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
            "kcs": {"articles": [], "total": 0, "error": str(e)},
            "sop": {"sops": [], "total": 0, "error": str(e)}
        }), 500


@app.route('/api/kcs-article-details', methods=['POST'])
def kcs_article_details():
    """Fetch full KCS article details including Environment and Resolution"""
    try:
        data = request.get_json()
        article_id = data.get('id')

        if not article_id:
            return jsonify({'success': False, 'error': 'Missing article ID'}), 400

        # Get Red Hat token
        config = data.get('config', get_config())
        token = get_sfdc_access_token(config)

        if not token:
            return jsonify({'success': False, 'error': 'Authentication failed'}), 401

        # Method 1: Scrape the article web page to get full content
        # This is the ONLY reliable way to get Environment, Issue, Resolution, and publish status
        publish_state = 'N/A'
        environment = ''
        issue = ''
        resolution = ''

        try:
            # Get URL from the request data if provided (from search results)
            article_web_url = data.get('url')
            document_kind = data.get('document_kind', '')
            app.logger.info(f"📍 Received URL: {article_web_url}, document_kind: {document_kind}")

            # Try both /solutions/ and /articles/ URLs
            headers_web = {
                "Authorization": f"Bearer {token}",
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
            }

            urls_to_try = [
                f"https://access.redhat.com/solutions/{article_id}",
                f"https://access.redhat.com/articles/{article_id}"
            ]

            web_response = None
            for url in urls_to_try:
                app.logger.info(f"🔍 Trying URL: {url}")
                try:
                    resp = requests.get(url, headers=headers_web, timeout=10)
                    app.logger.info(f"📥 HTTP Status: {resp.status_code}")

                    if resp.status_code == 200:
                        web_response = resp
                        article_web_url = url
                        app.logger.info(f"✅ SUCCESS! Found article at: {url}")
                        break
                except Exception as e:
                    app.logger.error(f"⚠️ Error fetching {url}: {e}")

            if not web_response:
                app.logger.error(f"❌ Could not fetch article {article_id} from any URL")
                raise Exception("Article not found at any URL")

            if web_response.status_code == 200:
                html = web_response.text
                app.logger.info(f"✅ Got HTML response, length: {len(html)}")

                # Save HTML for debugging
                with open(f'/tmp/kcs_{article_id}.html', 'w', encoding='utf-8') as f:
                    f.write(html)
                app.logger.info(f"💾 Saved HTML to /tmp/kcs_{article_id}.html")

                # Check verification and publish status
                if 'data-state="unpublished"' in html or 'class="unpublished"' in html or '>Unpublished<' in html:
                    publish_state = 'Unpublished'
                    app.logger.info(f"🔍 Detected UNPUBLISHED article: {article_id}")
                elif 'class="status verified"' in html or '>Solution Verified<' in html or "KCSState', 'verified'" in html:
                    publish_state = 'Solution Verified'
                    app.logger.info(f"✅ Detected SOLUTION VERIFIED: {article_id}")
                elif 'class="status unverified"' in html or '>Solution Unverified<' in html or "KCSState', 'unverified'" in html:
                    publish_state = 'Solution Unverified'
                    app.logger.info(f"⚠️ Detected SOLUTION UNVERIFIED: {article_id}")
                elif 'class="status inprogress"' in html or '>Solution In Progress<' in html or 'Solution in progress' in html or "KCSState', 'inprogress'" in html:
                    publish_state = 'Solution In Progress'
                    app.logger.info(f"🔄 Detected SOLUTION IN PROGRESS: {article_id}")
                elif 'data-state="published"' in html or 'class="published"' in html:
                    publish_state = 'Published'
                    app.logger.info(f"✅ Detected PUBLISHED article: {article_id}")
                else:
                    publish_state = 'Published'  # Default assumption

                # Extract Environment section
                import re
                # Try section-based structure first
                env_match = re.search(r'<section class="field_kcs_environment_txt"[^>]*>.*?<h2[^>]*>Environment</h2>(.*?)</section>', html, re.DOTALL | re.IGNORECASE)
                if env_match:
                    environment = env_match.group(1).strip()
                    # Extract list items
                    items = re.findall(r'<li>(.*?)</li>', environment, re.DOTALL)
                    if items:
                        # Join items with bullets, remove version numbers at the end
                        cleaned_items = []
                        for item in items:
                            clean_item = re.sub(r'<[^>]+>', '', item).strip()
                            # Remove trailing version numbers like " 4", " 4.x", etc.
                            clean_item = re.sub(r'\s+\d+(?:\.\w+)?$', '', clean_item)
                            cleaned_items.append(f"• {clean_item}")
                        environment = '\n'.join(cleaned_items)
                    else:
                        # Fallback: clean all HTML
                        environment = re.sub(r'<[^>]+>', ' ', environment)
                        environment = environment.replace('&nbsp;', ' ').strip()
                    app.logger.info(f"✅ Extracted Environment: {environment[:200]}")
                else:
                    # Fallback to div-based structure
                    env_match = re.search(r'<h2[^>]*>\s*Environment\s*</h2>\s*<div[^>]*>(.*?)</div>', html, re.DOTALL | re.IGNORECASE)
                    if env_match:
                        environment = env_match.group(1).strip()
                        environment = re.sub(r'<[^>]+>', '', environment)
                        environment = environment.replace('&nbsp;', ' ').strip()
                        app.logger.info(f"✅ Extracted Environment: {environment[:200]}")

                # Extract Issue section
                issue_match = re.search(r'<h2[^>]*>Issue</h2>(.*?)</section>', html, re.DOTALL | re.IGNORECASE)
                if issue_match:
                    issue = issue_match.group(1).strip()
                    # Extract list items
                    items = re.findall(r'<li>(.*?)</li>', issue, re.DOTALL)
                    if items:
                        # Join items with bullets
                        issue = '\n'.join(f"• {re.sub(r'<[^>]+>', '', item).strip()}" for item in items)
                    else:
                        # Fallback: clean all HTML
                        issue = re.sub(r'<[^>]+>', ' ', issue)
                        issue = issue.replace('&nbsp;', ' ').strip()
                    app.logger.info(f"✅ Extracted Issue: {issue[:200]}")

                # Extract Resolution section
                res_match = re.search(r'<section class="field_kcs_resolution_txt"[^>]*>.*?<h2[^>]*>Resolution</h2>(.*?)</section>', html, re.DOTALL | re.IGNORECASE)
                if res_match:
                    resolution = res_match.group(1).strip()
                    # Extract list items
                    items = re.findall(r'<li>(.*?)</li>', resolution, re.DOTALL)
                    if items:
                        # Join items with bullets
                        resolution = '\n'.join(f"• {re.sub(r'<[^>]+>', '', item).strip()}" for item in items)
                    else:
                        # Fallback: clean all HTML
                        resolution = re.sub(r'<[^>]+>', ' ', resolution)
                        resolution = resolution.replace('&nbsp;', ' ').strip()
                    app.logger.info(f"✅ Extracted Resolution: {resolution[:200]}")

        except Exception as scrape_err:
            app.logger.error(f"⚠️ Web scraping failed: {scrape_err}")

        # If scraping got data, return it immediately
        if environment or issue or resolution:
            app.logger.info(f"✅ Returning scraped data for article {article_id}")
            return jsonify({
                'success': True,
                'environment': environment,
                'issue': issue,
                'resolution': resolution,
                'abstract': '',
                'publish_state': publish_state
            })

        # Fetch full article using Red Hat API
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        # Try multiple API endpoints to get full article content

        # Method 2: Try direct article API endpoint
        try:
            article_url = f"{SFDC_API_BASE}/hydra/rest/cases/kcs/articles/{article_id}"
            print(f"🔍 Trying KCS article endpoint: {article_url}")

            response = requests.get(article_url, headers=headers, timeout=30)
            response.raise_for_status()
            doc = response.json()

            print(f"📋 KCS Article API response keys: {list(doc.keys())}")

            # Check various possible field names
            env_data = (doc.get('environment') or doc.get('environmentDescription') or
                       doc.get('product') or doc.get('productName') or '')

            # Convert arrays to strings
            issue_data = doc.get('issue', doc.get('issueDescription', doc.get('symptom', '')))
            if isinstance(issue_data, list):
                issue_data = '\n'.join(f"• {item}" for item in issue_data)

            resolution_data = doc.get('resolution', doc.get('resolutionDescription', doc.get('fix', '')))
            if isinstance(resolution_data, list):
                resolution_data = '\n'.join(f"• {item}" for item in resolution_data)

            return jsonify({
                'success': True,
                'environment': env_data,
                'issue': issue_data,
                'resolution': resolution_data,
                'abstract': doc.get('abstract', doc.get('description', '')),
                'publish_state': publish_state  # Use scraped value
            })
        except Exception as e1:
            print(f"⚠️ Method 2 failed: {e1}")

            # Method 3: Try solutions endpoint
            try:
                solutions_url = f"{SFDC_API_BASE}/hydra/rest/search/kcs/solutions/{article_id}"
                print(f"🔍 Trying KCS solutions endpoint: {solutions_url}")

                response = requests.get(solutions_url, headers=headers, timeout=30)
                response.raise_for_status()
                doc = response.json()

                print(f"📋 KCS Solutions API response keys: {list(doc.keys())}")

                # Convert arrays to strings
                issue_data = doc.get('issue', doc.get('issueDescription', ''))
                if isinstance(issue_data, list):
                    issue_data = '\n'.join(f"• {item}" for item in issue_data)

                resolution_data = doc.get('resolution', doc.get('resolutionDescription', ''))
                if isinstance(resolution_data, list):
                    resolution_data = '\n'.join(f"• {item}" for item in resolution_data)

                return jsonify({
                    'success': True,
                    'environment': doc.get('environment', doc.get('environmentDescription', '')),
                    'issue': issue_data,
                    'resolution': resolution_data,
                    'abstract': doc.get('abstract', doc.get('description', '')),
                    'publish_state': publish_state  # Use scraped value
                })
            except Exception as e2:
                print(f"⚠️ Method 3 failed: {e2}")

                # Method 4: Fallback to search API with all fields
                url = f"{SFDC_API_BASE}/hydra/rest/search/v2/kcs"
                request_data = {
                    "q": f"id:{article_id}",
                    "rows": 1,
                    "expression": "fl=*"  # Request ALL fields
                }

                response = requests.post(url, headers=headers, json=request_data, timeout=30)
                response.raise_for_status()
                result = response.json()

                if "response" in result and "docs" in result["response"] and len(result["response"]["docs"]) > 0:
                    doc = result["response"]["docs"][0]

                    # Debug: print all available fields
                    print(f"📋 KCS Search API all fields: {list(doc.keys())}")

                    # Convert arrays to strings
                    issue_data = doc.get('issue', doc.get('issueDescription', ''))
                    if isinstance(issue_data, list):
                        issue_data = '\n'.join(f"• {item}" for item in issue_data)

                    resolution_data = doc.get('resolution', doc.get('resolutionDescription', ''))
                    if isinstance(resolution_data, list):
                        resolution_data = '\n'.join(f"• {item}" for item in resolution_data)

                    return jsonify({
                        'success': True,
                        'environment': doc.get('environment', doc.get('environmentDescription', '')),
                        'issue': issue_data,
                        'resolution': resolution_data,
                        'abstract': doc.get('abstract', ''),
                        'publish_state': publish_state  # Use scraped value
                    })
                else:
                    return jsonify({'success': False, 'error': 'Article not found'}), 404

    except Exception as e:
        print(f"KCS article details error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/slack-thread', methods=['POST'])
def get_slack_thread():
    """Fetch Slack thread replies"""
    try:
        data = request.get_json()
        channel_id = data.get('channel_id')
        thread_ts = data.get('thread_ts')

        if not channel_id or not thread_ts:
            return jsonify({'success': False, 'error': 'Missing channel_id or thread_ts'}), 400

        # Get config from session or request
        config = data.get('config', get_config())

        # Fetch thread using the new function
        result = fetch_slack_thread(channel_id, thread_ts, config)

        if result.get('error'):
            return jsonify({'success': False, 'error': result['error']}), 500

        return jsonify({
            'success': True,
            'messages': result['messages'],
            'total': result['total']
        })

    except Exception as e:
        print(f"❌ Slack thread API error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/github-file-content', methods=['POST'])
def github_file_content():
    """Fetch first 20 lines of a GitHub file"""
    try:
        data = request.get_json()
        repository = data.get('repository')
        path = data.get('path')

        if not repository or not path:
            return jsonify({'success': False, 'error': 'Missing repository or path'}), 400

        # Get GitHub token from config
        config = data.get('config', get_config())
        github_token = config.get('github_token', os.getenv('GITHUB_TOKEN', ''))

        if not github_token:
            return jsonify({'success': False, 'error': 'GitHub token not configured'}), 401

        # Fetch file content from GitHub API
        url = f'https://api.github.com/repos/{repository}/contents/{path}'
        headers = {
            'Authorization': f'token {github_token}',
            'Accept': 'application/vnd.github.v3.raw'  # Get raw file content
        }

        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code == 404:
            return jsonify({'success': False, 'error': 'File not found'}), 404

        response.raise_for_status()

        # Get first 20 lines
        content = response.text
        lines = content.split('\n')[:20]
        preview = '\n'.join(lines)

        return jsonify({
            'success': True,
            'content': preview,
            'total_lines': len(content.split('\n'))
        })

    except Exception as e:
        print(f"❌ GitHub file content error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/gitlab-file-content', methods=['POST'])
def gitlab_file_content():
    """Fetch first 20 lines of a GitLab file"""
    try:
        data = request.get_json()
        project_id = data.get('project_id')
        path = data.get('path')
        ref = data.get('ref', 'main')

        if not project_id or not path:
            return jsonify({'success': False, 'error': 'Missing project_id or path'}), 400

        # Get GitLab token from config
        config = data.get('config', get_config())
        gitlab_token = config.get('gitlab_token', os.getenv('GITLAB_TOKEN', ''))
        gitlab_url = config.get('gitlab_url', 'https://gitlab.cee.redhat.com')

        if not gitlab_token:
            return jsonify({'success': False, 'error': 'GitLab token not configured'}), 401

        # Fetch file content from GitLab API
        url = f'{gitlab_url}/api/v4/projects/{project_id}/repository/files/{path.replace("/", "%2F")}/raw'
        headers = {
            'PRIVATE-TOKEN': gitlab_token
        }
        params = {
            'ref': ref
        }

        response = requests.get(url, headers=headers, params=params, timeout=10)

        if response.status_code == 404:
            return jsonify({'success': False, 'error': 'File not found'}), 404

        response.raise_for_status()

        # Get first 20 lines
        content = response.text
        lines = content.split('\n')[:20]
        preview = '\n'.join(lines)

        return jsonify({
            'success': True,
            'content': preview,
            'total_lines': len(content.split('\n'))
        })

    except Exception as e:
        print(f"❌ GitLab file content error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/jira-issue-links/<jira_key>', methods=['GET'])
def get_jira_issue_links(jira_key):
    """Fetch related content from Jira issue comments: KCS articles, Red Hat docs, Slack threads, and linked SFDC cases"""
    try:
        username = request.headers.get('X-Username', '')
        tokens_file = os.path.join(os.path.dirname(__file__), 'user_tokens.json')

        config = {}
        if username and os.path.exists(tokens_file):
            with open(tokens_file, 'r') as f:
                all_tokens = json.load(f)
                config = all_tokens.get(username, {})

        atlassian_email = config.get('atlassian_email', '')
        atlassian_token = config.get('atlassian_token', '')

        if not atlassian_email or not atlassian_token:
            return jsonify({'error': 'Jira credentials not configured'}), 401

        # First, fetch the OHSS ticket itself to look for linked cases in custom fields
        import time
        start_time = time.time()
        app.logger.info(f"🔗 Fetching OHSS ticket {jira_key} with all fields")

        headers_jira = {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }

        # Get the issue with ALL fields to find linked cases
        issue_url = f"https://redhat.atlassian.net/rest/api/3/issue/{jira_key}?fields=*all"
        issue_resp = requests.get(
            issue_url,
            headers=headers_jira,
            auth=(atlassian_email, atlassian_token),
            timeout=30
        )
        fetch_time = time.time() - start_time
        app.logger.info(f"⏱️ OHSS fetch took {fetch_time:.2f}s")

        jira_linked_cases = []

        # Check if OHSS ticket has linked cases in a custom field
        if issue_resp.status_code == 200:
            ohss_data = issue_resp.json()
            ohss_fields = ohss_data.get('fields', {})

            # Look for custom fields that might contain linked cases
            # Log all non-null custom fields to find the right one
            app.logger.info(f"📋 Searching OHSS {jira_key} custom fields for linked cases")

            import re

            # Search for custom fields containing linked cases (no debug logging for speed)
            for field_name, field_value in ohss_fields.items():
                if field_name.startswith('customfield_') and field_value:
                    # Check if it's a list of linked cases
                    if isinstance(field_value, list) and len(field_value) > 0:
                        first_item = field_value[0]
                        # Check if items have case-related properties
                        if isinstance(first_item, dict) and ('caseNumber' in first_item or 'case_number' in first_item or 'summary' in first_item or 'status' in first_item):
                            app.logger.info(f"  🎯 Found potential linked cases field: {field_name}")
                            app.logger.info(f"     Sample item: {first_item}")

                            # Extract case information from this field
                            for case_item in field_value:
                                if isinstance(case_item, dict):
                                    case_number = case_item.get('caseNumber') or case_item.get('case_number') or case_item.get('id', '')
                                    status = case_item.get('status', 'Unknown')
                                    summary = case_item.get('summary', f'Case {case_number}')

                                    # Validate case number format
                                    if re.match(r'^0[34]\d{6}$', str(case_number)):
                                        jira_linked_cases.append({
                                            'case_number': case_number,
                                            'salesforce_id': '',
                                            'problem_statement': summary,
                                            'summary': summary,
                                            'status': status,
                                            'url': f"https://access.redhat.com/support/cases/#/case/{case_number}",
                                            'urls': {
                                                'classic': f"https://gss--c.vf.force.com/apex/Case_View?sbstr={case_number}",
                                                'customer_portal': f"https://access.redhat.com/support/cases/#/case/{case_number}"
                                            },
                                            'source': 'ohss_linked_cases_field'
                                        })
                                        app.logger.info(f"  ✅ Found SFDC case from OHSS field: {case_number} - {summary} ({status})")

        # If no cases found in custom fields, fall back to checking issue links
        if issue_resp.status_code == 200:
            issue_data = issue_resp.json()
            issue_links = issue_data.get('fields', {}).get('issuelinks', [])
            app.logger.info(f"📋 Found {len(issue_links)} issue links in Jira")

            # Process each issue link
            for link in issue_links:
                # Issue links have either 'inwardIssue' or 'outwardIssue'
                linked_issue = link.get('inwardIssue') or link.get('outwardIssue')

                if linked_issue:
                    linked_key = linked_issue.get('key', '')
                    linked_fields = linked_issue.get('fields', {})
                    linked_summary = linked_fields.get('summary', '')
                    linked_status = linked_fields.get('status', {}).get('name', 'Unknown')

                    app.logger.info(f"  🔍 Linked issue: {linked_key}, Summary: {linked_summary}, Status: {linked_status}")

                    import re
                    case_match = re.search(r'\b(0[34]\d{6})\b', f"{linked_key} {linked_summary}")

                    if case_match:
                        case_number = case_match.group(1)
                        jira_linked_cases.append({
                            'case_number': case_number,
                            'salesforce_id': '',
                            'problem_statement': linked_summary or f'Case {case_number}',
                            'summary': linked_summary or f'Case {case_number}',
                            'status': linked_status,
                            'url': f"https://access.redhat.com/support/cases/#/case/{case_number}",
                            'urls': {
                                'classic': f"https://gss--c.vf.force.com/apex/Case_View?sbstr={case_number}",
                                'customer_portal': f"https://access.redhat.com/support/cases/#/case/{case_number}"
                            },
                            'source': 'jira_issuelink'
                        })
                        app.logger.info(f"  ✅ Found SFDC case from Jira issue link: {case_number} - {linked_summary}")
        else:
            app.logger.warning(f"⚠️ Failed to fetch Jira issue: {issue_resp.status_code}")

        # Fetch issue comments from Jira API
        start_time = time.time()
        jira_url = f"https://redhat.atlassian.net/rest/api/3/issue/{jira_key}/comment"
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }

        response = requests.get(
            jira_url,
            headers=headers,
            auth=(atlassian_email, atlassian_token),
            timeout=30
        )
        comments_time = time.time() - start_time
        app.logger.info(f"⏱️ Comments fetch took {comments_time:.2f}s")

        if response.status_code != 200:
            return jsonify({'error': f'Failed to fetch Jira comments: {response.status_code}'}), response.status_code

        data = response.json()
        comments = data.get('comments', [])
        app.logger.info(f"📋 Found {len(comments)} comments in {jira_key}")

        # Also get the issue description to extract case numbers
        issue_resp = requests.get(
            f"https://redhat.atlassian.net/rest/api/3/issue/{jira_key}",
            headers=headers,
            auth=(atlassian_email, atlassian_token),
            timeout=30
        )

        issue_description = ''
        if issue_resp.status_code == 200:
            issue_data = issue_resp.json()
            desc = issue_data.get('fields', {}).get('description', '')
            if isinstance(desc, dict):
                issue_description = extract_text_from_adf(desc)
            else:
                issue_description = str(desc)
            app.logger.info(f"📋 Issue description length: {len(issue_description)} chars")

        # Extract links from all comments
        kcs_articles = []
        redhat_docs = []
        slack_threads = []
        github_links = []
        case_numbers_found = []

        import re

        # First, extract case numbers from description and comments
        all_text = issue_description + '\n'
        for comment in comments:
            body = comment.get('body', {})
            comment_text = extract_text_from_adf(body) if isinstance(body, dict) else str(body)
            all_text += comment_text + '\n'

        # Extract Salesforce case numbers (8 digits, format: 03123456 or 04123456)
        case_pattern = r'\b(0[34]\d{6})\b'
        case_matches = re.findall(case_pattern, all_text)
        for case_num in case_matches:
            if case_num not in case_numbers_found:
                case_numbers_found.append(case_num)
                jira_linked_cases.append({
                    'case_number': case_num,
                    'salesforce_id': '',
                    'problem_statement': f'Case {case_num} (mentioned in ticket)',
                    'summary': f'Case {case_num}',
                    'status': 'Unknown',
                    'url': f"https://access.redhat.com/support/cases/#/case/{case_num}",
                    'urls': {
                        'classic': f"https://gss--c.vf.force.com/apex/Case_View?sbstr={case_num}",
                        'customer_portal': f"https://access.redhat.com/support/cases/#/case/{case_num}"
                    },
                    'source': 'jira_text'
                })
                app.logger.info(f"  ✅ Found SFDC case number in text: {case_num}")

        for comment in comments:
            # Extract text from ADF format
            body = comment.get('body', {})
            comment_text = extract_text_from_adf(body) if isinstance(body, dict) else str(body)

            # Extract KCS article links (access.redhat.com/solutions/XXXXXX or /articles/XXXXXX)
            kcs_pattern = r'https?://access\.redhat\.com/(solutions|articles)/(\d+)'
            kcs_matches = re.findall(kcs_pattern, comment_text)
            for match in kcs_matches:
                article_type, article_id = match
                url = f"https://access.redhat.com/{article_type}/{article_id}"
                if url not in [a['url'] for a in kcs_articles]:
                    kcs_articles.append({
                        'id': article_id,
                        'url': url,
                        'title': f'KCS {article_type.capitalize()} {article_id}'  # Will be updated with real title
                    })
                    app.logger.info(f"  ✅ Found KCS article: {article_id}")

            # Extract Red Hat documentation links (docs.redhat.com or access.redhat.com/documentation)
            docs_pattern = r'https?://(docs\.redhat\.com|access\.redhat\.com/documentation)/[^\s<>"\')]+'
            for doc_match in re.finditer(docs_pattern, comment_text):
                url = doc_match.group(0)
                if url not in [d['url'] for d in redhat_docs]:
                    path_parts = url.rstrip('/').split('/')
                    title = path_parts[-1].replace('-', ' ').replace('_', ' ') if path_parts else 'Red Hat Documentation'
                    redhat_docs.append({
                        'url': url,
                        'title': title
                    })

            # Extract Slack thread links (redhat-internal.slack.com only)
            slack_pattern = r'https?://redhat-internal\.slack\.com/archives/([A-Z0-9]+)/p(\d+)'
            slack_matches = re.findall(slack_pattern, comment_text)
            for match in slack_matches:
                channel_id, thread_ts = match
                # Convert timestamp format (p1234567890123456 -> 1234567890.123456)
                thread_ts_formatted = thread_ts[:10] + '.' + thread_ts[10:]
                url = f"https://redhat-internal.slack.com/archives/{channel_id}/p{thread_ts}"
                if url not in [s['url'] for s in slack_threads]:
                    slack_threads.append({
                        'channel_id': channel_id,
                        'thread_ts': thread_ts_formatted,
                        'url': url,
                        'title': f'Slack Thread in {channel_id}'
                    })
                    app.logger.info(f"  ✅ Found Slack thread: {channel_id}/p{thread_ts}")

            # Extract GitHub repository links
            github_pattern = r'https?://github\.com/[^\s<>"\')]+'
            for gh_match in re.finditer(github_pattern, comment_text):
                url = gh_match.group(0).rstrip('.,;:')
                if url not in [g['url'] for g in github_links]:
                    path_parts = url.replace('https://github.com/', '').split('/')
                    if len(path_parts) >= 2:
                        repo = f"{path_parts[0]}/{path_parts[1]}"
                        if len(path_parts) > 4 and path_parts[2] == 'blob':
                            title = f"{repo}: {path_parts[-1]}"
                        elif len(path_parts) > 4 and path_parts[2] == 'tree':
                            title = f"{repo}/{'/'.join(path_parts[4:])}"
                        else:
                            title = repo
                    else:
                        title = url.replace('https://github.com/', '')
                    github_links.append({
                        'url': url,
                        'title': title
                    })
                    app.logger.info(f"  ✅ Found GitHub link: {url[:80]}")

        # Get channel names for Related Content
        slack_xoxc = config.get('slack_xoxc', '')
        slack_xoxd = config.get('slack_xoxd', '')
        if slack_xoxc and slack_xoxd and slack_threads:
            unique_channel_ids = set(t['channel_id'] for t in slack_threads)
            channel_name_map = {}
            for ch_id in unique_channel_ids:
                try:
                    resp = requests.get(
                        'https://slack.com/api/conversations.info',
                        headers={
                            'Authorization': f'Bearer {slack_xoxc}',
                            'Cookie': f'd={slack_xoxd}'
                        },
                        params={'channel': ch_id},
                        timeout=10
                    )
                    if resp.status_code == 200:
                        ch_data = resp.json()
                        if ch_data.get('ok'):
                            channel_name_map[ch_id] = ch_data['channel']['name']
                            app.logger.info(f"  ✅ Resolved channel {ch_id} -> #{channel_name_map[ch_id]}")
                except Exception as e:
                    app.logger.warning(f"Failed to resolve channel name for {ch_id}: {e}")

            for thread in slack_threads:
                ch_name = channel_name_map.get(thread['channel_id'])
                if ch_name:
                    thread['channel_name'] = ch_name
                    thread['title'] = f'Slack thread in #{ch_name}'

        # Fetch KCS article titles from Red Hat API
        redhat_token = config.get('redhat_token', '')
        if redhat_token and kcs_articles:
            kcs_access_token = get_sfdc_access_token(config)
            if kcs_access_token:
                for article in kcs_articles:
                    try:
                        article_id = article['id']
                        kcs_api_url = f"https://access.redhat.com/hydra/rest/search/kcs?q={article_id}"
                        headers_rh = {
                            'Authorization': f'Bearer {kcs_access_token}',
                            'Accept': 'application/json'
                        }
                        resp = requests.get(kcs_api_url, headers=headers_rh, timeout=10)
                        if resp.status_code == 200:
                            kcs_data = resp.json()
                            docs = kcs_data.get('response', {}).get('docs', [])
                            if docs:
                                article['title'] = docs[0].get('publishedTitle', article['title'])
                                app.logger.info(f"  ✅ KCS {article_id} title: {article['title']}")
                    except Exception as e:
                        app.logger.warning(f"Failed to fetch KCS title for {article_id}: {e}")

        # Use Jira remote links as the primary source for linked SFDC cases
        linked_cases = jira_linked_cases  # Already fetched from Jira remote links
        redhat_token = config.get('redhat_token', '')

        app.logger.info(f"🔑 Red Hat token present: {'Yes' if redhat_token else 'No'}")
        if redhat_token:
            app.logger.info(f"🔑 Red Hat token (first 20 chars): {redhat_token[:20]}...")

        # Optional: Enrich linked cases with full details from SFDC API if we have Red Hat token
        # This adds problem_statement and accurate status, but isn't required
        if redhat_token and len(linked_cases) > 0:
            start_time = time.time()
            app.logger.info(f"🔍 Attempting to enrich {len(linked_cases)} SFDC cases with Red Hat API")

            # Exchange offline token for access token
            access_token = get_sfdc_access_token(config)
            token_time = time.time() - start_time
            app.logger.info(f"⏱️ Token exchange took {token_time:.2f}s")

            if not access_token:
                app.logger.warning(f"⚠️ Failed to get SFDC access token from offline token")
            else:
                app.logger.info(f"✅ Successfully obtained SFDC access token")

            for sfdc_case in linked_cases:
                if not access_token:
                    break

                try:
                    case_number = sfdc_case['case_number']
                    # Fetch full case details from SFDC API
                    case_start = time.time()
                    case_api_url = f"https://access.redhat.com/hydra/rest/cases/{case_number}"
                    headers_sfdc = {
                        'Authorization': f'Bearer {access_token}',  # Use access token, not offline token
                        'Accept': 'application/json'
                    }
                    resp = requests.get(case_api_url, headers=headers_sfdc, timeout=10)
                    case_fetch_time = time.time() - case_start
                    app.logger.info(f"⏱️ Case {case_number} fetch took {case_fetch_time:.2f}s")
                    if resp.status_code == 200:
                        case_data = resp.json()
                        # Override with full details from SFDC API
                        sfdc_case['problem_statement'] = case_data.get('summaryEnglish', case_data.get('summary', sfdc_case.get('problem_statement', 'No problem statement')))
                        sfdc_case['status'] = case_data.get('status', sfdc_case.get('status', 'Unknown'))
                        sfdc_case['salesforce_id'] = case_data.get('id', sfdc_case.get('salesforce_id', ''))
                        sfdc_case['urls']['classic'] = f"https://gss--c.vf.force.com/apex/Case_View?sbstr={case_number}"
                        app.logger.info(f"  ✅ Enriched case {case_number} with full SFDC details")
                    else:
                        error_text = resp.text[:500] if resp.text else 'No error message'
                        app.logger.warning(f"  ⚠️ Failed to enrich case {case_number}: HTTP {resp.status_code}")
                        app.logger.warning(f"  ⚠️ Error response: {error_text}")
                except Exception as e:
                    app.logger.warning(f"  ⚠️ Failed to enrich SFDC case {sfdc_case.get('case_number')}: {e}")
        else:
            if len(linked_cases) > 0:
                app.logger.info(f"📋 Using basic info from Jira remote links (no Red Hat token for enrichment)")

        # Fallback: Search SFDC if no remote links found
        if redhat_token and len(linked_cases) == 0:
            try:
                # Search for Salesforce cases that contain this Jira key
                sfdc_search_url = "https://access.redhat.com/hydra/rest/search/v2/cases"
                headers_sfdc = {
                    'Authorization': f'Bearer {redhat_token}',
                    'Accept': 'application/json',
                    'Content-Type': 'application/json'
                }

                # Search for the Jira key in case descriptions and comments
                search_payload = {
                    'q': jira_key,
                    'start': 0,
                    'rows': 20
                }

                app.logger.info(f"🔍 Searching SFDC for cases linked to {jira_key}")
                sfdc_resp = requests.post(sfdc_search_url, headers=headers_sfdc, json=search_payload, timeout=30)
                app.logger.info(f"📊 SFDC search response: status={sfdc_resp.status_code}")

                if sfdc_resp.status_code == 200:
                    sfdc_data = sfdc_resp.json()
                    docs = sfdc_data.get('response', {}).get('docs', [])
                    total_found = sfdc_data.get('response', {}).get('numFound', 0)
                    app.logger.info(f"📋 SFDC search found {total_found} cases mentioning {jira_key}")

                    for doc in docs:
                        case_number = doc.get('case_number', 'Unknown')
                        salesforce_id = doc.get('id', '')

                        linked_cases.append({
                            'case_number': case_number,
                            'salesforce_id': salesforce_id,
                            'summary': doc.get('subject', 'No summary'),
                            'problem_statement': doc.get('case_summaryEnglish', doc.get('case_summary', 'No problem statement')),
                            'status': doc.get('case_status', 'Unknown'),
                            'urls': {
                                'classic': f"https://gss--c.vf.force.com/apex/Case_View?sbstr={case_number}",
                                'customer_portal': f"https://access.redhat.com/support/cases/#/case/{case_number}"
                            },
                            'url': f"https://access.redhat.com/support/cases/#/case/{case_number}"
                        })

                    app.logger.info(f"✅ Found {len(linked_cases)} linked Salesforce cases for {jira_key}")
                else:
                    app.logger.warning(f"❌ SFDC search failed: {sfdc_resp.status_code} - {sfdc_resp.text[:200]}")
            except Exception as e:
                app.logger.error(f"❌ Failed to fetch linked Salesforce cases: {e}", exc_info=True)
        else:
            app.logger.warning(f"⚠️ No Red Hat token - cannot search for linked SFDC cases")

        result = {
            'kcs_articles': kcs_articles,
            'redhat_docs': redhat_docs,
            'slack_threads': slack_threads,
            'github_links': github_links,
            'cases': linked_cases
        }
        app.logger.info(f"📋 Jira {jira_key} - Found {len(kcs_articles)} KCS, {len(redhat_docs)} Docs, {len(slack_threads)} Slack, {len(github_links)} GitHub, {len(linked_cases)} SFDC cases")
        return jsonify(result)

    except Exception as e:
        app.logger.error(f"Jira issue links error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/sfdc/case/<case_number>', methods=['GET'])
def get_sfdc_case_details(case_number):
    """Fetch full SFDC case details on-demand (lazy loading)"""
    try:
        username = request.headers.get('X-Username', '')
        tokens_file = os.path.join(os.path.dirname(__file__), 'user_tokens.json')

        config = get_config()
        if username and os.path.exists(tokens_file):
            with open(tokens_file, 'r') as f:
                all_tokens = json.load(f)
                user_tokens = all_tokens.get(username, {})
                redhat_token = user_tokens.get('redhat_token', '')
                if redhat_token:
                    config['redhat_token'] = redhat_token

        # Get access token
        access_token = get_sfdc_access_token(config)

        # Fetch case details
        case_detail_url = f"{SFDC_API_BASE}/hydra/rest/cases/{case_number}"
        case_resp = requests.get(
            case_detail_url,
            headers={
                'Authorization': f'Bearer {access_token}',
                'Accept': 'application/json'
            },
            timeout=5
        )

        if case_resp.status_code != 200:
            return jsonify({'error': f'Failed to fetch case details: {case_resp.status_code}'}), case_resp.status_code

        case_detail = case_resp.json()

        # Extract the fields we need
        case_owner = case_detail.get('caseOwner', {})
        owner_name = case_owner.get('name', 'N/A') if isinstance(case_owner, dict) else 'N/A'

        account = case_detail.get('account', {})
        account_name = account.get('name', 'N/A') if isinstance(account, dict) else 'N/A'

        # Use 'sbt' field for numeric minutes, fallback to 'sbtState' for text status
        sbt_value = case_detail.get('sbt')
        if sbt_value is None or sbt_value == '':
            sbt_value = case_detail.get('sbtState', 'N/A')

        details = {
            'owner': owner_name,
            'account_number': case_detail.get('accountNumber', 'N/A'),
            'account_name': account_name,
            'internal_status': case_detail.get('internalStatus', 'N/A'),
            'sbt': sbt_value,
            'sbr': case_detail.get('sbrGroup', 'N/A'),
            'description': case_detail.get('description', case_detail.get('caseDescription', 'No description available'))
        }

        return jsonify(details)

    except Exception as e:
        app.logger.error(f"Error fetching SFDC case details for {case_number}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/sfdc/case/<case_number>/related-content', methods=['GET'])
def get_sfdc_case_related_content(case_number):
    """Fetch KCS articles, Red Hat docs, Slack threads, and ICM tickets from SFDC case comments"""
    try:
        username = request.headers.get('X-Username', '')
        tokens_file = os.path.join(os.path.dirname(__file__), 'user_tokens.json')

        config = get_config()
        redhat_token = ''
        user_tokens_data = {}
        if username and os.path.exists(tokens_file):
            with open(tokens_file, 'r') as f:
                all_tokens = json.load(f)
                user_tokens_data = all_tokens.get(username, {})
                redhat_token = user_tokens_data.get('redhat_token', '')
                if redhat_token:
                    config['redhat_token'] = redhat_token

        access_token = get_sfdc_access_token(config)
        if not access_token:
            return jsonify({'kcs_articles': [], 'redhat_docs': [], 'slack_threads': [], 'error': 'SFDC token not configured'})

        app.logger.info(f"🔍 Fetching Related Content for SFDC case {case_number}")

        # Fetch case comments from Hydra API
        comments_url = f"{SFDC_API_BASE}/hydra/rest/cases/{case_number}/comments"
        comments_resp = requests.get(
            comments_url,
            headers={
                'Authorization': f'Bearer {access_token}',
                'Accept': 'application/json'
            },
            timeout=15
        )

        kcs_articles = []
        redhat_docs = []
        slack_threads = []
        icm_tickets = []

        # Also fetch case description to parse for URLs
        case_url = f"{SFDC_API_BASE}/hydra/rest/cases/{case_number}"
        case_resp = requests.get(
            case_url,
            headers={
                'Authorization': f'Bearer {access_token}',
                'Accept': 'application/json'
            },
            timeout=10
        )

        all_texts = []

        # Parse case description
        if case_resp.status_code == 200:
            case_data = case_resp.json()
            description = case_data.get('description', '') or case_data.get('caseDescription', '') or ''
            if description:
                all_texts.append(description)

        # Parse comments
        if comments_resp.status_code == 200:
            comments_data = comments_resp.json()

            # Handle different response formats
            if isinstance(comments_data, list):
                comments = comments_data
            elif isinstance(comments_data, dict):
                comments = comments_data.get('comments', comments_data.get('body', []))
                if not isinstance(comments, list):
                    comments = [comments_data]
            else:
                comments = []

            app.logger.info(f"  📋 Found {len(comments)} comments for case {case_number}")

            for comment in comments:
                if isinstance(comment, str):
                    comment_text = comment
                elif isinstance(comment, dict):
                    comment_text = comment.get('text', comment.get('body', comment.get('commentBody', comment.get('caseComment', ''))))
                    if not comment_text:
                        comment_text = str(comment)
                else:
                    continue
                if comment_text:
                    all_texts.append(comment_text)
        else:
            app.logger.warning(f"  ⚠️ Failed to fetch comments: HTTP {comments_resp.status_code}")

        # Parse all texts for KCS, Docs, and Slack URLs (same regex as Jira implementation)
        for text in all_texts:
            # KCS articles
            kcs_pattern = r'https?://access\.redhat\.com/(solutions|articles)/(\d+)'
            kcs_matches = re.findall(kcs_pattern, text)
            for match in kcs_matches:
                article_type, article_id = match
                url = f"https://access.redhat.com/{article_type}/{article_id}"
                if url not in [a['url'] for a in kcs_articles]:
                    kcs_articles.append({
                        'id': article_id,
                        'url': url,
                        'title': f'KCS {article_type.capitalize()} {article_id}'
                    })
                    app.logger.info(f"  ✅ Found KCS article: {article_id}")

            # Red Hat documentation
            docs_pattern = r'https?://(docs\.redhat\.com|access\.redhat\.com/documentation)/[^\s<>"\')]+'
            for doc_match in re.finditer(docs_pattern, text):
                url = doc_match.group(0)
                if url not in [d['url'] for d in redhat_docs]:
                    path_parts = url.rstrip('/').split('/')
                    title = path_parts[-1].replace('-', ' ').replace('_', ' ') if path_parts else 'Red Hat Documentation'
                    redhat_docs.append({'url': url, 'title': title})
                    app.logger.info(f"  ✅ Found Red Hat doc: {url[:80]}")

            # Slack threads
            slack_pattern = r'https?://redhat-internal\.slack\.com/archives/([A-Z0-9]+)/p(\d+)'
            slack_matches = re.findall(slack_pattern, text)
            for match in slack_matches:
                channel_id, thread_ts = match
                thread_ts_formatted = thread_ts[:10] + '.' + thread_ts[10:]
                url = f"https://redhat-internal.slack.com/archives/{channel_id}/p{thread_ts}"
                if url not in [s['url'] for s in slack_threads]:
                    slack_threads.append({
                        'channel_id': channel_id,
                        'thread_ts': thread_ts_formatted,
                        'url': url,
                        'title': f'Slack Thread in {channel_id}'
                    })
                    app.logger.info(f"  ✅ Found Slack thread: {channel_id}/p{thread_ts}")

            # ICM tickets (Microsoft ICM portal)
            icm_pattern = r'https?://portal\.microsofticm\.com/imp/v\d+/incidents/details/(\d+)/summary/?'
            icm_matches = re.findall(icm_pattern, text)
            for incident_id in icm_matches:
                url = f"https://portal.microsofticm.com/imp/v5/incidents/details/{incident_id}/summary"
                if url not in [t['url'] for t in icm_tickets]:
                    icm_tickets.append({
                        'id': incident_id,
                        'url': url,
                        'title': f'ICM Incident {incident_id}'
                    })
                    app.logger.info(f"  ✅ Found ICM ticket: {incident_id}")

        # Resolve Slack channel IDs to channel names
        slack_xoxc = user_tokens_data.get('slack_xoxc', '') if user_tokens_data else ''
        slack_xoxd = user_tokens_data.get('slack_xoxd', '') if user_tokens_data else ''
        if slack_xoxc and slack_xoxd and slack_threads:
            unique_channel_ids = set(t['channel_id'] for t in slack_threads)
            channel_name_map = {}
            for ch_id in unique_channel_ids:
                try:
                    resp = requests.get(
                        'https://slack.com/api/conversations.info',
                        headers={
                            'Authorization': f'Bearer {slack_xoxc}',
                            'Cookie': f'd={slack_xoxd}'
                        },
                        params={'channel': ch_id},
                        timeout=10
                    )
                    if resp.status_code == 200:
                        ch_data = resp.json()
                        if ch_data.get('ok'):
                            channel_name_map[ch_id] = ch_data['channel']['name']
                            app.logger.info(f"  ✅ Resolved channel {ch_id} -> #{channel_name_map[ch_id]}")
                except Exception as e:
                    app.logger.warning(f"Failed to resolve channel name for {ch_id}: {e}")

            for thread in slack_threads:
                ch_name = channel_name_map.get(thread['channel_id'])
                if ch_name:
                    thread['channel_name'] = ch_name
                    thread['title'] = f'Slack thread in #{ch_name}'

        # Enrich KCS articles with titles from Hydra API
        if redhat_token and kcs_articles:
            kcs_access_token = get_sfdc_access_token(config)
            if kcs_access_token:
                for article in kcs_articles[:10]:
                    try:
                        article_id = article['id']
                        kcs_api_url = f"https://access.redhat.com/hydra/rest/search/kcs?q={article_id}"
                        resp = requests.get(
                            kcs_api_url,
                            headers={
                                'Authorization': f'Bearer {kcs_access_token}',
                                'Accept': 'application/json'
                            },
                            timeout=10
                        )
                        if resp.status_code == 200:
                            kcs_data = resp.json()
                            docs = kcs_data.get('response', {}).get('docs', [])
                            if docs:
                                article['title'] = docs[0].get('publishedTitle', article['title'])
                                app.logger.info(f"  ✅ KCS {article_id} title: {article['title']}")
                    except Exception as e:
                        app.logger.warning(f"Failed to fetch KCS title for {article_id}: {e}")

        app.logger.info(f"  📊 Related Content for {case_number}: {len(kcs_articles)} KCS, {len(redhat_docs)} Docs, {len(slack_threads)} Slack, {len(icm_tickets)} ICM")

        return jsonify({
            'kcs_articles': kcs_articles,
            'redhat_docs': redhat_docs,
            'slack_threads': slack_threads,
            'icm_tickets': icm_tickets
        })

    except Exception as e:
        app.logger.error(f"❌ Error fetching SFDC related content for {case_number}: {e}")
        import traceback
        app.logger.error(f"Traceback: {traceback.format_exc()}")
        return jsonify({
            'kcs_articles': [],
            'redhat_docs': [],
            'slack_threads': [],
            'icm_tickets': [],
            'error': str(e)
        }), 500


@app.route('/api/case-escalations/<case_number>', methods=['GET'])
def get_case_escalations(case_number):
    """Fetch OHSS tickets that link to this SFDC case"""
    try:
        username = request.headers.get('X-Username', '')
        tokens_file = os.path.join(os.path.dirname(__file__), 'user_tokens.json')

        atlassian_email = ''
        atlassian_token = ''

        if os.path.exists(tokens_file):
            with open(tokens_file, 'r') as f:
                all_tokens = json.load(f)
                user_tokens = all_tokens.get(username, {})
                atlassian_email = user_tokens.get('atlassian_email', '')
                atlassian_token = user_tokens.get('atlassian_token', '')

        if not atlassian_email or not atlassian_token:
            app.logger.warning(f"⚠️ Jira credentials not configured for case {case_number}")
            return jsonify({
                'external_trackers': [],
                'error': 'Jira credentials not configured'
            })

        app.logger.info(f"🔍 Searching Jira for OHSS tickets linked to case {case_number}")

        # Search Jira for tickets that mention this case number in description or comments
        # JQL: text ~ "04419323" AND project in (OHSS, SREP)
        jql = f'text ~ "{case_number}" AND project in (OHSS, SREP) ORDER BY created DESC'

        jira_search_url = "https://redhat.atlassian.net/rest/api/3/search/jql"

        params = {
            'jql': jql,
            'maxResults': 50,
            'fields': 'summary,status,description,comment'
        }

        app.logger.info(f"  JQL: {jql}")

        jira_resp = requests.get(
            jira_search_url,
            auth=(atlassian_email, atlassian_token),
            params=params,
            headers={'Accept': 'application/json'},
            timeout=15
        )

        external_trackers = []

        if jira_resp.status_code == 200:
            jira_data = jira_resp.json()
            issues = jira_data.get('issues', [])

            app.logger.info(f"  ✅ Found {len(issues)} OHSS/SREP tickets mentioning case {case_number}")

            for issue in issues:
                key = issue.get('key', 'Unknown')
                fields = issue.get('fields', {})
                summary = fields.get('summary', 'No title')
                status_obj = fields.get('status', {})
                status = status_obj.get('name', 'Unknown') if isinstance(status_obj, dict) else 'Unknown'

                external_trackers.append({
                    'resourceKey': key,
                    'resourceURL': f"https://issues.redhat.com/browse/{key}",
                    'title': summary,
                    'status': status,
                    'system': 'Jira'
                })

                app.logger.info(f"    ✓ {key}: {summary[:60]}")

        else:
            app.logger.warning(f"  ⚠️ Jira search failed: HTTP {jira_resp.status_code}")

        return jsonify({
            'external_trackers': external_trackers,
            'total': len(external_trackers)
        })

    except Exception as e:
        app.logger.error(f"❌ Error fetching external trackers for {case_number}: {e}")
        import traceback
        app.logger.error(f"Traceback: {traceback.format_exc()}")
        return jsonify({
            'external_trackers': [],
            'error': str(e)
        }), 500


if __name__ == '__main__':
    os.makedirs('templates_unified', exist_ok=True)

    print("=" * 70)
    print(" 🔍 Unified Search - Jira + SFDC + Slack + KCS + SOP")
    print("=" * 70)
    print("\n✨ Search all five systems with one query!\n")
    print("Open your browser:")
    print("  👉 http://localhost:5500\n")
    print("Features:")
    print("  • Parallel search across Jira, SFDC, Slack, KCS, and SOP")
    print("  • Category filtering (show/hide each source)")
    print("  • Result counts in sidebar")
    print("  • Clean, unified interface\n")
    print("Prerequisites:")
    print("  • MCP Server for SOP search: cd kush/mcp-server/mcp-server && ./start_server.sh")
    print("  • Set MCP_SERVER_URL env var (default: http://localhost:8000)\n")
    print("Press CTRL+C to stop")
    print("=" * 70 + "\n")

    app.run(debug=True, host='0.0.0.0', port=5500)
