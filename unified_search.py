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
        "refresh_token": redhat_token,
        "scope": "api.graphql"  # Required for GraphQL API access
    }

    try:
        print(f"🔐 Requesting access token with GraphQL scope...", flush=True)
        response = requests.post(SSO_URL, data=payload, timeout=30)
        response.raise_for_status()

        data = response.json()
        _access_token = data["access_token"]
        _token_expiry = datetime.now() + timedelta(seconds=data.get("expires_in", 900) - 60)

        print(f"✅ Access token obtained successfully (expires in {data.get('expires_in', 900)}s)", flush=True)
        return _access_token
    except Exception as e:
        print(f"❌ SFDC token error: {e}", flush=True)
        if hasattr(e, 'response') and e.response is not None:
            print(f"❌ Response body: {e.response.text[:500]}", flush=True)
        return None


def search_sfdc_graphql(query: str, max_results: int = 20, config: Dict = None) -> Dict:
    """Search SFDC cases using GraphQL API (finds Lightning-only cases)"""
    try:
        token = get_sfdc_access_token(config)
        if not token:
            return {"cases": [], "total": 0, "error": "Authentication failed"}

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "apollographql-client-name": "seekr-ai",
            "apollographql-client-version": "1.0.0",
            "Apollo-Require-Preflight": "true"  # Required to bypass CSRF protection
        }

        # GraphQL query to search cases
        graphql_query = """
        query SearchCases($searchText: String, $first: Int) {
          redhat_support_uiapi {
            query {
              RedHatSupportCase(
                where: {
                  or: [
                    { CaseNumber__c: { like: $searchText } }
                    { Subject: { like: $searchText } }
                  ]
                }
                first: $first
                orderBy: { LastModifiedDate: { order: DESC } }
              ) {
                totalCount
                edges {
                  node {
                    Id
                    CaseNumber__c { value }
                    Subject { value }
                    Description { value }
                    Status { value }
                    Priority { value }
                    CreatedDate { value }
                    LastModifiedDate { value }
                    SBR_Group__c { value }
                    SBT__c { value }
                    Owner {
                      ... on RedHatSupportGroup {
                        Id
                        Name { value }
                      }
                      ... on RedHatSupportUser {
                        Id
                        Name { value }
                      }
                    }
                    Product {
                      Name { value }
                    }
                    RedHatSupportAccount {
                      Name { value }
                      AccountNumber { value }
                    }
                  }
                }
              }
            }
          }
        }
        """

        data = {
            "query": graphql_query,
            "variables": {
                "searchText": f"%{query}%",
                "first": max_results
            }
        }

        try:
            print(f"📡 Sending GraphQL request for query: {query}", flush=True)
            graphql_endpoint = "https://graphql.redhat.com"
            print(f"📡 Endpoint: {graphql_endpoint}", flush=True)
            print(f"📡 Headers: {list(headers.keys())}", flush=True)
            response = requests.post(
                graphql_endpoint,
                headers=headers,
                json=data,
                timeout=30,  # GraphQL queries can take longer
                verify=True
            )
            print(f"📡 GraphQL response status: {response.status_code}", flush=True)
            print(f"📡 GraphQL response body: {response.text[:500]}", flush=True)
            response.raise_for_status()
            result = response.json()
            print(f"📡 GraphQL response parsed successfully", flush=True)
        except requests.exceptions.Timeout:
            print(f"⚠️ GraphQL API timeout (10s) - falling back to REST v2", flush=True)
            return {"cases": [], "total": 0, "error": "GraphQL timeout"}
        except requests.exceptions.HTTPError as http_err:
            status_code = http_err.response.status_code if http_err.response else 'Unknown'
            error_body = http_err.response.text if http_err.response else 'No response body'
            print(f"⚠️ GraphQL API HTTP error: {status_code}", flush=True)
            print(f"⚠️ GraphQL error body: {error_body}", flush=True)
            # Try to parse error as JSON
            try:
                error_json = http_err.response.json() if http_err.response else {}
                print(f"⚠️ GraphQL error JSON: {error_json}", flush=True)
            except:
                pass
            return {"cases": [], "total": 0, "error": f"GraphQL error ({status_code})"}
        except Exception as e:
            print(f"⚠️ GraphQL unexpected error: {str(e)}", flush=True)
            return {"cases": [], "total": 0, "error": f"GraphQL error: {str(e)}"}

        # Parse GraphQL response
        cases = []
        edges = result.get("data", {}).get("redhat_support_uiapi", {}).get("query", {}).get("RedHatSupportCase", {}).get("edges", [])
        total_count = result.get("data", {}).get("redhat_support_uiapi", {}).get("query", {}).get("RedHatSupportCase", {}).get("totalCount", 0)

        for edge in edges:
            node = edge.get("node", {})
            salesforce_id = node.get("Id", "")
            case_number = node.get("CaseNumber__c", {}).get("value", "N/A")
            product_obj = node.get("Product", {})
            product = product_obj.get("Name", {}).get("value", "N/A") if product_obj else "N/A"
            account_obj = node.get("RedHatSupportAccount", {})
            account_name = account_obj.get("Name", {}).get("value", "N/A") if account_obj else "N/A"
            account_number = account_obj.get("AccountNumber", {}).get("value", "N/A") if account_obj else "N/A"

            sbr = node.get("SBR_Group__c", {}).get("value", "N/A") if node.get("SBR_Group__c") else "N/A"
            sbt = node.get("SBT__c", {}).get("value", "N/A") if node.get("SBT__c") else "N/A"

            # Extract Owner name from polymorphic Owner field (User or Group)
            owner_obj = node.get("Owner", {})
            if owner_obj and isinstance(owner_obj, dict):
                owner_name_obj = owner_obj.get("Name", {})
                owner = owner_name_obj.get("value", "N/A") if owner_name_obj else "N/A"
            else:
                owner = "N/A"

            # Build URLs conditionally based on Product and Account scenarios
            urls = {}

            # Debug logging for URL decision
            print(f"  🔍 Case {case_number}: Product='{product}', Account='{account_name}'")

            # Scenario 1: Azure Red Hat OpenShift (ARO) + MS-TEP account
            # Show all 4 links: CaseView+, Classic, Lightning, Customer Portal
            if product == "Azure Red Hat OpenShift" and account_name == "MS-TEP":
                print(f"  ✅ Scenario 1: ARO + MS-TEP → 4 links")
                urls = {
                    "caseview_plus": f"https://gss.my.salesforce.com/apex/Support#/cases/{case_number}",
                    "classic": f"https://gss--c.vf.force.com/apex/Case_View?sbstr={case_number}",
                    "lightning": f"https://redhatsupport.lightning.force.com/lightning/r/Case/{salesforce_id}/view",
                    "customer_portal": f"https://access.redhat.com/support/cases/#/case/{case_number}"
                }
            # Scenario 2 & 3: All others (ARO non-MS-TEP, ROSA, ROSA HCP, OSD, etc.)
            # Show only Lightning + Customer Portal
            else:
                print(f"  ✅ Scenario 2/3: ARO non-MS-TEP or other products → 2 links (Lightning + Portal)")
                urls = {
                    "lightning": f"https://redhatsupport.lightning.force.com/lightning/r/Case/{salesforce_id}/view",
                    "customer_portal": f"https://access.redhat.com/support/cases/#/case/{case_number}"
                }

            cases.append({
                "case_number": case_number,
                "summary": node.get("Subject", {}).get("value", "No summary"),
                "description": node.get("Description", {}).get("value", ""),
                "status": node.get("Status", {}).get("value", "Unknown"),
                "severity": node.get("Priority", {}).get("value", "N/A"),
                "product": product,
                "created_date": node.get("CreatedDate", {}).get("value", ""),
                "last_modified_date": node.get("LastModifiedDate", {}).get("value", ""),
                "owner": owner,
                "account_number": account_number,
                "account_name": account_name,
                "sbt": sbt,
                "sbr": sbr,
                "urls": urls,
                "salesforce_id": salesforce_id
            })

        return {
            "cases": cases,
            "total": total_count
        }

    except Exception as e:
        print(f"GraphQL search error: {e}")
        return {"cases": [], "total": 0, "error": str(e)}


def search_sfdc(query: str, max_results: int = 20, config: Dict = None) -> Dict:
    """Search SFDC cases - tries GraphQL first, falls back to REST v2"""
    # Try GraphQL first (finds all cases including Lightning-only new cases)
    print("🔍 Trying GraphQL search first...", flush=True)
    graphql_result = search_sfdc_graphql(query, max_results, config)

    print(f"📊 GraphQL result: {len(graphql_result.get('cases', []))} cases, error: {graphql_result.get('error', 'none')}", flush=True)

    # If GraphQL succeeds and returns results, use it
    if graphql_result.get("cases") and len(graphql_result["cases"]) > 0:
        print(f"✅ GraphQL found {len(graphql_result['cases'])} cases", flush=True)
        return graphql_result

    # If GraphQL fails or returns no results, fall back to REST v2
    print("⚠️ GraphQL returned no results, falling back to REST v2...", flush=True)

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
            # Request account fields for conditional URL logic (ARO/MS-TEP scenarios)
            "expression": "sort=score%20desc&fl=case_createdByName%2Ccase_createdDate%2Ccase_lastModifiedDate%2Cid%2Curi%2Ccase_summary%2Ccase_description%2Ccase_status%2Ccase_product%2Ccase_version%2Ccase_number%2Ccase_severity%2Ccase_accountName%2Ccase_accountNumber"
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
                case_id = doc.get("id", "")  # Salesforce internal ID for Lightning URL
                product = doc.get("case_product", "N/A")
                account_name = doc.get("case_accountName", "N/A")

                # REST API fallback - provide CaseView+ and Classic
                # Customer Portal is always available, Lightning will be added via lazy load
                urls = {
                    "caseview_plus": f"https://gss.my.salesforce.com/apex/Support#/cases/{case_number}",
                    "classic": f"https://gss--c.vf.force.com/apex/Case_View?sbstr={case_number}",
                    "customer_portal": f"https://access.redhat.com/support/cases/#/case/{case_number}"
                }

                cases.append({
                    "case_number": case_number,
                    "summary": doc.get("case_summary", "No summary"),
                    "description": doc.get("case_description", ""),
                    "status": doc.get("case_status", "Unknown"),
                    "severity": doc.get("case_severity", "N/A"),
                    "product": product,
                    "created_date": doc.get("case_createdDate", ""),
                    "last_modified_date": doc.get("case_lastModifiedDate", ""),
                    "owner": "N/A",
                    "account_number": doc.get("case_accountNumber", "N/A"),
                    "account_name": account_name,
                    "sbt": "N/A",
                    "sbr": "N/A",
                    "urls": urls
                })

        return {
            "cases": cases,
            "total": result.get("response", {}).get("numFound", 0)
        }

    except Exception as e:
        print(f"SFDC search error: {e}")
        return {"cases": [], "total": 0, "error": str(e)}


# ============================================================================
# Jira Project Detection
# ============================================================================

BIGRAM_PROJECT_MAP = {
    'support exception':  ['SUPPORTEX'],
    'support exceptions': ['SUPPORTEX'],
    'feature request':    ['RFE'],
    'feature requests':   ['RFE'],
    'ocp bug':            ['OCPBUGS'],
    'ocp bugs':           ['OCPBUGS'],
}

PRODUCT_PROJECT_MAP = {
    # Tier 1 — Product keywords
    'rosa':       ['ROSAENG', 'OHSS', 'OCPBUGS', 'OCM'],
    'aro':        ['ARO', 'OCPBUGS'],
    'osd':        ['OHSS', 'OCPBUGS'],
    'hypershift': ['ROSAENG', 'OCPBUGS'],
    'hcp':        ['ROSAENG', 'OHSS'],
    'ocm':        ['OCM', 'ROSAENG'],

    # Tier 2 — Explicit project key words
    'ocpbugs':   ['OCPBUGS'],
    'supportex': ['SUPPORTEX'],
    'rfe':       ['RFE'],
    'hpstrat':   ['HPSTRAT'],
    'ohss':      ['OHSS'],
}

TIER1_KEYWORDS = {'rosa', 'aro', 'osd', 'hypershift', 'hcp', 'ocm'}


def detect_product_projects(query: str):
    """
    Returns (projects_list, remaining_words).
    Detection order: Bigrams → Tier 1 → Tier 2 → None (all projects).
    """
    words_clean = [w.lower().strip('.,:-') for w in query.split()]
    raw_words   = query.split()

    # Step 1: Bigram check
    for i in range(len(words_clean) - 1):
        bigram = f"{words_clean[i]} {words_clean[i+1]}"
        if bigram in BIGRAM_PROJECT_MAP:
            projects  = BIGRAM_PROJECT_MAP[bigram]
            remaining = [raw_words[j] for j in range(len(raw_words)) if j not in (i, i+1)]
            return projects, remaining

    # Step 2: Tier 1 — product keywords
    for i, word in enumerate(words_clean):
        clean = ''.join(c for c in word if c.isalpha())
        if clean in TIER1_KEYWORDS:
            projects  = PRODUCT_PROJECT_MAP[clean]
            remaining = [raw_words[j] for j in range(len(raw_words)) if j != i]
            return projects, remaining

    # Step 3: Tier 2 — explicit project keys
    for i, word in enumerate(words_clean):
        clean = ''.join(c for c in word if c.isalpha())
        if clean in PRODUCT_PROJECT_MAP:
            projects  = PRODUCT_PROJECT_MAP[clean]
            remaining = [raw_words[j] for j in range(len(raw_words)) if j != i]
            return projects, remaining

    return None, query.split()


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

    # Default: no project detection (only set in the text-search branch below)
    detected_projects = None

    # Use custom JQL if provided, otherwise generate automatically
    if custom_jql:
        jql = custom_jql
        app.logger.info(f"🔍 Jira Custom JQL: {jql}")
        # Don't modify custom JQL - use it exactly as provided
    else:
        # 1. Check if query is a Jira key (e.g., OHSS-54143, SRE-1234)
        # Must be a single token: LETTERS-NUMBERS only, no spaces.
        # Prevents "aro control-plane resize" from matching due to hyphen.
        if re.match(r'^[A-Za-z]+-\d+$', query.strip()):
            jql = f'key = "{query.strip()}" OR text ~ "{query}"'
            print(f"🔍 Jira JQL (key search): {jql}")
        else:
            detected_projects, search_words = detect_product_projects(query)
            significant_words = [w for w in search_words if len(w) > 2] or search_words

            # Safeguard: remaining words all too short → fall back to full query
            if not significant_words:
                jql = f'summary ~ "{query}"'
                print(f"🔍 Jira JQL (empty significant_words safeguard): {jql}")

            elif len(significant_words) == 1:
                summary_cond = f'summary ~ "{significant_words[0]}"'
                if detected_projects:
                    proj_keys = ', '.join(f'"{p}"' for p in detected_projects)
                    jql = f'project in ({proj_keys}) AND {summary_cond}'
                    print(f"🔍 Jira JQL (project-scoped {detected_projects}, single word): {jql}")
                else:
                    jql = summary_cond
                    print(f"🔍 Jira JQL (all-projects, single word): {jql}")

            else:
                # Multiple words: summary ~ per word (AND, not phrase — avoids adjacency requirement)
                summary_cond = ' AND '.join([f'summary ~ "{w}"' for w in significant_words])
                if detected_projects:
                    proj_keys = ', '.join(f'"{p}"' for p in detected_projects)
                    jql = f'project in ({proj_keys}) AND {summary_cond}'
                    print(f"🔍 Jira JQL (project-scoped {detected_projects}): {jql}")
                else:
                    jql = summary_cond
                    print(f"🔍 Jira JQL (all-projects): {jql}")

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

        # Single unified query — project-aware JQL above handles scoping.
        # Removed separate OHSS OR query: redundant and caused OHSS to flood
        # results regardless of query intent.
        general_data = _jira_api_call(jql, max_results)
        app.logger.info(f"📊 Jira results: {len(general_data.get('issues', []))}")

        seen_keys = set()
        all_raw_issues = []
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

        # Determine priority project based on what was detected:
        #   rosa / hcp / osd → OHSS first
        #   aro              → ARO first
        #   others / no-match → trust Jira relevance (no sort)
        # Stable sort — Jira relevance order preserved within each group.
        priority_project = None
        if detected_projects:
            if 'OHSS' in detected_projects:
                priority_project = 'OHSS'
            elif 'ARO' in detected_projects:
                priority_project = 'ARO'

        if priority_project:
            try:
                issues.sort(key=lambda x: 0 if x['project'] == priority_project else 1)
                app.logger.info(f"✅ {priority_project} sorted first ({len(issues)} issues)")
            except Exception as sort_err:
                app.logger.error(f"❌ Sorting failed: {sort_err}")
        else:
            app.logger.info(f"✅ Returning {len(issues)} issues in Jira relevance order")

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

        # Check if query is a Salesforce case number (8 digits)
        import re
        case_number_pattern = r'^\d{8}$'
        if re.match(case_number_pattern, query.strip()):
            # Query is a case number - fetch KCS articles from case comments
            case_number = query.strip()
            print(f"🔍 KCS: Detected case number {case_number}, fetching linked KCS articles from comments")

            try:
                # Fetch case comments
                comments_url = f"{SFDC_API_BASE}/hydra/rest/cases/{case_number}/comments"
                comments_resp = requests.get(comments_url, headers=headers, timeout=15)

                # Fetch case description
                case_url = f"{SFDC_API_BASE}/hydra/rest/cases/{case_number}"
                case_resp = requests.get(case_url, headers=headers, timeout=10)

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
                    if isinstance(comments_data, list):
                        comments = comments_data
                    elif isinstance(comments_data, dict):
                        comments = comments_data.get('comments', comments_data.get('body', []))
                        if not isinstance(comments, list):
                            comments = [comments_data]
                    else:
                        comments = []

                    for comment in comments:
                        if isinstance(comment, str):
                            comment_text = comment
                        elif isinstance(comment, dict):
                            comment_text = comment.get('text', comment.get('body', comment.get('commentBody', comment.get('caseComment', ''))))
                        else:
                            continue
                        if comment_text:
                            all_texts.append(comment_text)

                # Extract KCS article IDs from all texts
                kcs_article_ids = []
                kcs_pattern = r'https?://access\.redhat\.com/(?:solutions|articles)/(\d+)'
                for text in all_texts:
                    matches = re.findall(kcs_pattern, text)
                    for article_id in matches:
                        if article_id not in kcs_article_ids:
                            kcs_article_ids.append(article_id)

                if not kcs_article_ids:
                    print(f"  ℹ️ No KCS articles found in case {case_number} comments")
                    return {"articles": [], "total": 0}

                print(f"  ✅ Found {len(kcs_article_ids)} KCS articles in case comments: {kcs_article_ids}")

                # Fetch full details for each KCS article
                articles = []
                for article_id in kcs_article_ids[:max_results]:
                    try:
                        # Search for this specific article to get full details
                        data = {
                            "q": article_id,
                            "rows": 1,
                            "expression": "sort=score%20DESC&fq=documentKind%3A(%22Article%22%20OR%20%22Solution%22)%20AND%20accessState%3A(%22active%22%20OR%20%22private%22)&fl=allTitle%2CcaseCount%2CdocumentKind%2Cid%2Cscore%2Curi%2Cresource_uri%2Cview_uri%2Cenvironment%2Cissue%2Cresolution%2CverificationState%2CpublishState%2CmodifiedDate&showRetired=false",
                            "start": 0,
                            "clientName": "unified-search"
                        }
                        resp = requests.post(
                            f"{SFDC_API_BASE}/hydra/rest/search/v2/kcs",
                            headers=headers,
                            json=data,
                            timeout=10
                        )
                        if resp.status_code == 200:
                            r = resp.json()
                            docs = r.get("response", {}).get("docs", [])
                            # Find the exact article by ID
                            for doc in docs:
                                if doc.get("id") == article_id:
                                    article = {
                                        "id": doc.get("id", "N/A"),
                                        "title": doc.get("allTitle", "No title"),
                                        "document_kind": doc.get("documentKind", "Article"),
                                        "score": doc.get("score", 0),
                                        "view_uri": doc.get("view_uri", ""),
                                        "url": doc.get("view_uri", f"https://access.redhat.com/solutions/{article_id}"),
                                        "environment": doc.get("environment", ""),
                                        "issue": doc.get("issue", ""),
                                        "resolution": doc.get("resolution", ""),
                                        "verification_state": doc.get("verificationState", doc.get("publishState", "N/A")),
                                        "publish_state": doc.get("publishState", "N/A"),
                                        "modified_date": doc.get("modifiedDate", "N/A")
                                    }
                                    articles.append(article)
                                    break
                    except Exception as e:
                        print(f"  ⚠️ Failed to fetch details for KCS {article_id}: {e}")

                return {"articles": articles, "total": len(articles)}

            except Exception as e:
                print(f"  ❌ Failed to fetch case comments for {case_number}: {e}")
                # Fall back to empty results for case number queries
                return {"articles": [], "total": 0}

        # Not a case number - do normal KCS search
        KCS_EXPRESSION = "sort=score%20DESC&fq=documentKind%3A(%22Article%22%20OR%20%22Solution%22)%20AND%20accessState%3A(%22active%22%20OR%20%22private%22)&fl=allTitle%2CcaseCount%2CdocumentKind%2Cid%2Cscore%2Curi%2Cresource_uri%2Cview_uri%2Cenvironment%2Cissue%2Cresolution%2CverificationState%2CpublishState%2CmodifiedDate&showRetired=false"

        def _kcs_api_call(q, rows):
            """Make a single KCS API call and return list of docs."""
            data = {
                "q": q,
                "rows": rows,
                "expression": KCS_EXPRESSION,
                "start": 0,
                "clientName": "unified-search"
            }
            for attempt in range(2):
                try:
                    resp = requests.post(
                        f"{SFDC_API_BASE}/hydra/rest/search/v2/kcs",
                        headers=headers,
                        json=data,
                        timeout=30,
                        verify=True
                    )
                    resp.raise_for_status()
                    r = resp.json()
                    return r.get("response", {}).get("docs", []), r.get("response", {}).get("numFound", 0)
                except requests.exceptions.SSLError as ssl_err:
                    if attempt == 0:
                        print(f"KCS SSL error on attempt {attempt + 1}, retrying... {ssl_err}")
                        continue
                    else:
                        raise
            return [], 0

        PRODUCT_TERMS = {
            'aro': 'ARO',
            'rosa': 'ROSA',
            'osd': 'OSD',
            'hcp': '"hosted control plane"',
        }
        PRODUCT_DETECT = {
            'aro': ['aro', 'azure red hat openshift'],
            'rosa': ['rosa', 'red hat openshift service on aws'],
            'osd': ['osd', 'openshift dedicated'],
            'hcp': ['hcp', 'hosted control plane'],
        }
        query_lower = query.lower()
        has_product = any(
            any(k in query_lower for k in keywords)
            for keywords in PRODUCT_DETECT.values()
        )

        if has_product:
            # Query already has a product term — single search
            docs, total_found = _kcs_api_call(query, max_results)
        else:
            # No product in query — search per product, then merge
            # Product-specific results first, generic results fill remaining slots
            print(f"🔍 KCS: Searching per managed product for: {query}")
            seen_ids = set()
            product_docs = []
            for prod, term in PRODUCT_TERMS.items():
                result_docs, _ = _kcs_api_call(f'{query} {term}', 5)
                for doc in result_docs:
                    doc_id = doc.get("id", "")
                    if doc_id not in seen_ids:
                        seen_ids.add(doc_id)
                        product_docs.append(doc)
                print(f"  📦 KCS {prod}: {len(result_docs)} results, {len(product_docs)} unique so far")

            # Fill remaining with generic results
            base_docs, total_found = _kcs_api_call(query, max_results)
            base_unique = []
            for doc in base_docs:
                doc_id = doc.get("id", "")
                if doc_id not in seen_ids:
                    seen_ids.add(doc_id)
                    base_unique.append(doc)

            docs = (product_docs + base_unique)[:max_results]
            print(f"🔍 KCS: Merged {len(product_docs)} product-specific + {len(base_unique)} generic = {len(docs)} articles")

        articles = []
        for doc in docs:
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

        def _to_str(val):
            if isinstance(val, list):
                return ' '.join(str(v) for v in val)
            return str(val) if val else ''

        # Product-aware sorting: prioritize articles matching the queried product
        PRODUCT_PATTERNS = {
            'aro': ['aro', 'azure red hat openshift'],
            'rosa': ['rosa', 'red hat openshift service on aws'],
            'osd': ['osd', 'openshift dedicated'],
            'hcp': ['hcp', 'hosted control plane'],
        }
        query_lower = query.lower()
        query_products = [p for p, keywords in PRODUCT_PATTERNS.items()
                          if any(k in query_lower for k in keywords)]

        if query_products:
            def _article_product_match(article):
                text = ' '.join([
                    _to_str(article.get('environment', '')),
                    _to_str(article.get('title', '')),
                    _to_str(article.get('issue', ''))
                ]).lower()
                for qp in query_products:
                    if any(k in text for k in PRODUCT_PATTERNS[qp]):
                        return 0  # matching product → top
                return 1  # non-matching → bottom

            articles.sort(key=lambda a: (_article_product_match(a), -a.get('score', 0)))
            matched = sum(1 for a in articles if _article_product_match(a) == 0)
            print(f"🔍 KCS product sort: query products={query_products}, "
                  f"{matched}/{len(articles)} articles match")

        return {
            "articles": articles,
            "total": total_found
        }

    except Exception as e:
        print(f"KCS search error: {e}")
        return {"articles": [], "total": 0, "error": str(e)}


# ============================================================================
# SOP/Document Search Functions (ask-sre semantic search)
# ============================================================================

# ask-sre MCP Server configuration
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8000")
_mcp_session_id = None

def call_ask_sre(tool_name: str, arguments: Dict, timeout: int = 30) -> List[Dict]:
    """Call an ask-sre MCP tool via JSON-RPC over Streamable HTTP.
    Returns a list of result dicts on success, empty list on failure."""
    global _mcp_session_id

    mcp_endpoint = f"{MCP_SERVER_URL}/mcp"
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

        result_obj = parsed.get("result", {})
        if result_obj.get("isError"):
            error_text = result_obj.get("content", [{}])[0].get("text", "Unknown error")
            print(f"⚠️ ask-sre tool error: {error_text}")
            return []

        content = result_obj.get("content", [])
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


OPS_SOP_LOCAL_PATH = os.getenv("OPS_SOP_PATH", os.path.expanduser("~/ops-sop"))

_WORD_BOUNDARY_CACHE = {}

def _word_in_text(word: str, text: str) -> bool:
    """Word-boundary-aware matching.
    Long words (>=6 chars): substring match — specific enough to avoid false positives.
    Short words (<6 chars): require word boundary so 'repo' won't match 'report'."""
    variants = {word, word.replace("-",""), word.replace("_","")}
    if len(word) > 5:
        for j in range(3, len(word) - 2):
            variants.add(word[:j] + "-" + word[j:])
    for v in variants:
        if len(v) >= 6:
            if v in text:
                return True
        else:
            if v not in _WORD_BOUNDARY_CACHE:
                _WORD_BOUNDARY_CACHE[v] = re.compile(r'(?<![a-z])' + re.escape(v) + r'(?![a-z])')
            if _WORD_BOUNDARY_CACHE[v].search(text):
                return True
    return False


def _search_ops_sop_local(query: str, limit: int = 20) -> List[Dict]:
    """Search local ops-sop clone for keyword matches in markdown files."""
    try:
        if not os.path.isdir(OPS_SOP_LOCAL_PATH):
            return []

        query_words = [w.lower() for w in query.split() if len(w) > 2]
        if not query_words:
            return []

        # Build grep variants: "breakglass" also matches "break-glass", "break_glass"
        grep_variants = set(query_words)
        for w in query_words:
            if len(w) > 5:
                for i in range(3, len(w) - 2):
                    grep_variants.add(w[:i] + "-" + w[i:])
                    grep_variants.add(w[:i] + "_" + w[i:])
            grep_variants.add(w.replace("-", ""))
            grep_variants.add(w.replace("_", ""))

        grep_pattern = "\\|".join(grep_variants)
        result = subprocess.run(
            ["grep", "-ril", "--include=*.md", grep_pattern, OPS_SOP_LOCAL_PATH],
            capture_output=True, text=True, timeout=10
        )

        if result.returncode not in (0, 1):
            return []

        scored = []
        for filepath in result.stdout.strip().split("\n"):
            if not filepath.strip():
                continue
            rel_path = os.path.relpath(filepath, OPS_SOP_LOCAL_PATH)
            if rel_path.startswith("."):
                continue

            try:
                with open(filepath, 'r', errors='ignore') as f:
                    content = f.read(2000)
            except Exception:
                content = ""

            content_lower = content.lower()
            path_lower = rel_path.lower()

            # Weight words by length — longer words are more specific and matter more
            content_weight = sum(len(w) for w in query_words if _word_in_text(w, content_lower))
            path_weight = sum(len(w) for w in query_words if _word_in_text(w, path_lower))
            total_weight = sum(len(w) for w in query_words)
            any_match = max(content_weight, path_weight) > 0
            if not any_match:
                continue

            title_line = ""
            for line in content.split("\n"):
                stripped = line.strip().lstrip("#").strip()
                if stripped:
                    title_line = stripped
                    break

            content_coverage = content_weight / total_weight
            path_coverage = path_weight / total_weight
            score = (content_coverage * 0.5) + (path_coverage * 0.5)
            scored.append({
                "file_path": rel_path,
                "source": "local_ops_sop",
                "title": title_line or rel_path.split("/")[-1],
                "file_name": os.path.basename(rel_path),
                "summary": content[:500],
                "document_text": content,
                "score": score,
                "category": rel_path.split("/")[0] if "/" in rel_path else "",
                "severity": "",
                "service_name": "",
            })

        scored.sort(key=lambda x: x["score"], reverse=True)
        print(f"✅ ops-sop local search: {len(scored)} files matched, returning top {limit}")
        return scored[:limit]

    except Exception as e:
        print(f"⚠️ ops-sop local search error: {e}")
        return []


def search_sop(query: str, max_results: int = 20, config: Dict = None) -> Dict:
    """Search SOP documents: keyword search on ops-sop (primary) + ask-sre semantic (supplement)"""
    try:
        query_words = [w.lower() for w in query.split() if len(w) > 2]
        keyword_variants = set(query_words)
        for w in query_words:
            keyword_variants.add(w.replace("-", ""))
            keyword_variants.add(w.replace("_", ""))
            keyword_variants.add(w.replace("-", "").replace("_", ""))

        seen = {}

        # Run keyword search and semantic search in parallel
        top_k = min(max(max_results * 3, 30), 60)
        with ThreadPoolExecutor(max_workers=3) as ex:
            kw_future = ex.submit(_search_ops_sop_local, query, max_results)
            sem_future = ex.submit(call_ask_sre, "search_sre_docs", {"problem_statement": query, "max_results": top_k})
            db_future = ex.submit(_keyword_search_sop_db, query, 10)

            ops_sop_results = kw_future.result()
            raw_results = sem_future.result() or []
            keyword_results = db_future.result()

        # === PRIMARY: Local ops-sop keyword search (most accurate for exact matches) ===
        for osr in ops_sop_results:
            file_path = osr.get("file_path", "")
            source = osr.get("source", "local_ops_sop")
            dedup_key = f"{source}:{file_path}"
            base_score = osr.get("score", 0)
            seen[dedup_key] = {
                "id": "N/A",
                "title": osr.get("title", "No title"),
                "summary": osr.get("summary", "")[:500],
                "document_text": osr.get("document_text", osr.get("summary", "")),
                "score": 1.0 + base_score,
                "category": osr.get("category", ""),
                "severity": osr.get("severity", ""),
                "source": source,
                "file_path": file_path,
                "file_name": osr.get("file_name", ""),
                "service_name": osr.get("service_name", ""),
                "url": ""
            }

        keyword_count = len(seen)

        # === SUPPLEMENT: Ask-sre semantic search (broader coverage) ===
        for result in raw_results:
            if result.get("note") or result.get("message") or result.get("error"):
                continue

            file_path = result.get("file_path", "")
            if not file_path:
                continue

            source = result.get("source", "")
            dedup_key = f"{source}:{file_path}"
            similarity = result.get("similarity", 0)
            distance = result.get("distance", 0)
            if similarity <= 0 and distance > 0:
                similarity = max(0.01, 1.0 / (1.0 + distance))

            title = result.get("title", "") or file_path.split("/")[-1]
            file_name = result.get("file_name", "") or file_path.split("/")[-1]
            doc_text = (result.get("document_text", "") or "")[:500]

            # Score semantic results by keyword coverage (word-boundary-aware, length-weighted)
            combined = (file_path + " " + title + " " + doc_text).lower()
            hit_weight = sum(len(w) for w in query_words if _word_in_text(w, combined))
            total_w = sum(len(w) for w in query_words)
            if hit_weight > 0 and total_w > 0:
                word_coverage = min(1.0, hit_weight / total_w)
                boosted_score = 1.0 + (word_coverage * 0.5) + (similarity * 0.5)
            else:
                boosted_score = similarity

            if dedup_key not in seen or boosted_score > seen[dedup_key]["score"]:
                seen[dedup_key] = {
                    "id": result.get("id", "N/A"),
                    "title": title,
                    "summary": doc_text,
                    "document_text": result.get("document_text", "") or "",
                    "score": boosted_score,
                    "category": result.get("category", "") or result.get("log_type", ""),
                    "severity": result.get("severity", ""),
                    "source": source,
                    "file_path": file_path,
                    "file_name": file_name,
                    "service_name": result.get("service_name", ""),
                    "url": ""
                }

        # === SUPPLEMENT: PostgreSQL keyword search ===
        for kr in keyword_results:
            file_path = kr.get("file_path", "")
            source = kr.get("source", "")
            dedup_key = f"{source}:{file_path}"

            if dedup_key not in seen:
                seen[dedup_key] = {
                    "id": "N/A",
                    "title": kr.get("title", "No title"),
                    "summary": kr.get("summary", "")[:500],
                    "document_text": kr.get("document_text", kr.get("summary", "")),
                    "score": 0.5,
                    "category": kr.get("category", ""),
                    "severity": kr.get("severity", ""),
                    "source": source,
                    "file_path": file_path,
                    "file_name": kr.get("file_name", ""),
                    "service_name": kr.get("service_name", ""),
                    "url": ""
                }

        # Sort by score and return top results
        sops = sorted(seen.values(), key=lambda x: x["score"], reverse=True)[:max_results]

        print(f"✅ search: {keyword_count} keyword + {len(raw_results)} semantic + {len(keyword_results)} db → {len(seen)} unique → {len(sops)} returned")
        return {
            "sops": sops,
            "total": len(sops)
        }

    except requests.exceptions.ConnectionError:
        return {
            "sops": [],
            "total": 0,
            "error": "ask-sre MCP server not running. Start it with: poetry run ask-sre mcp --transport http --port 8000"
        }
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

        # Slack doesn't support wildcards in channel names, so search all channels
        # then filter results by channel name patterns
        search_query = query
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
    """Search GitLab mcs and service group repos via project name + file tree matching."""
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
        query_words = [w.lower() for w in query.split() if len(w) > 2]
        skip_words = {'gitlab', 'github', 'repo', 'search'}
        query_words = [w for w in query_words if w not in skip_words] or [w.lower() for w in query.split() if len(w) > 2]

        # Step 1: Get ALL projects from both groups (parallel)
        def list_group_projects(group):
            found = []
            try:
                resp = requests.get(
                    f'{gitlab_url}/api/v4/groups/{group}/projects',
                    headers=headers,
                    params={'per_page': 100, 'simple': 'true', 'order_by': 'last_activity_at'},
                    timeout=15, verify=False)
                if resp.status_code == 200:
                    for p in resp.json():
                        p['_group'] = group
                        found.append(p)
                    print(f"📊 GitLab: {len(found)} projects in {group} group")
            except Exception as e:
                print(f"⚠️ GitLab: Error listing {group}: {e}")
            return found

        with ThreadPoolExecutor(max_workers=2) as ex:
            group_futures = [ex.submit(list_group_projects, g) for g in GITLAB_GROUPS]
            all_projects = []
            seen_ids = set()
            for f in group_futures:
                for p in f.result():
                    if p['id'] not in seen_ids:
                        seen_ids.add(p['id'])
                        all_projects.append(p)

        if not all_projects:
            return {'results': [], 'total': 0, 'error': 'No projects found in mcs/service groups'}

        # Step 2: Search file trees across ALL projects (parallel)
        def search_project_tree(project):
            proj_id = project['id']
            proj_path = project.get('path_with_namespace', '')
            proj_name = project.get('name_with_namespace', project.get('name', ''))
            default_branch = project.get('default_branch', 'main')
            group = project.get('_group', proj_path.split('/')[0] if '/' in proj_path else '')

            proj_results = []
            try:
                resp = requests.get(
                    f'{gitlab_url}/api/v4/projects/{proj_id}/repository/tree',
                    headers=headers,
                    params={'per_page': 100, 'recursive': 'true'},
                    timeout=10, verify=False)
                if resp.status_code != 200:
                    return []

                proj_name_lower = proj_path.lower()
                proj_name_match = sum(len(w) for w in query_words if w in proj_name_lower)
                total_weight = sum(len(w) for w in query_words)

                for item in resp.json():
                    if item['type'] != 'blob':
                        continue
                    fpath = item['path']
                    fname = fpath.split('/')[-1]
                    fpath_lower = fpath.lower()

                    file_match = sum(len(w) for w in query_words if w in fpath_lower)
                    score = (proj_name_match + file_match) / total_weight if total_weight else 0

                    if proj_name_match > 0 or file_match > 0:
                        file_url = f"{gitlab_url}/{proj_path}/-/blob/{default_branch}/{fpath}"
                        proj_results.append({
                            'filename': fname,
                            'path': fpath,
                            'project_id': proj_id,
                            'project_name': proj_name,
                            'project_path': proj_path,
                            'group': group,
                            'ref': default_branch,
                            'url': file_url,
                            'summary': '',
                            'startline': 0,
                            'score': score,
                            'priority': True,
                        })
            except Exception:
                pass
            return proj_results

        results = []
        from concurrent.futures import as_completed
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(search_project_tree, p): p for p in all_projects}
            for future in as_completed(futures):
                results.extend(future.result())

        # Sort: mcs group first, then service, then by score within each group
        group_priority = {'mcs': 0, 'service': 1}
        results.sort(key=lambda r: (group_priority.get(r.get('group', ''), 9), -r.get('score', 0)))
        results = results[:max_results]
        print(f"✅ GitLab: {len(results)} results (mcs + service, from {len(all_projects)} projects)")
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

            # GitHub results come from ask-sre SOP merge below
            github_results = {"results": [], "total": 0}

            try:
                gitlab_results = gitlab_future.result()
            except Exception as e:
                print(f"❌ GitLab search exception: {e}")
                gitlab_results = {"results": [], "total": 0, "error": str(e)}

        # Merge ask-sre SOP results into GitHub/KCS by source type
        # Both local_ops_sop (openshift/ops-sop) and managed_openshift_docs are GitHub repos
        if sop_results.get("sops"):
            for sop in sop_results["sops"]:
                source_type = sop.get("source", "")
                full_text = sop.get("document_text", "") or sop.get("summary", "")
                doc_text = full_text[:300]
                content_lines = full_text.split('\n')[:20]
                file_content = '\n'.join(content_lines)

                if source_type == "local_ops_sop":
                    github_results["results"].append({
                        "name": sop.get("file_name", sop.get("title", "")),
                        "path": sop.get("file_path", ""),
                        "repository": "openshift/ops-sop",
                        "url": f"https://github.com/openshift/ops-sop/blob/master/{sop.get('file_path', '')}",
                        "score": sop.get("score", 0) * 1000,
                        "language": "Markdown",
                        "ask_sre": True,
                        "similarity": sop.get("score", 0),
                        "category": sop.get("category", ""),
                        "severity": sop.get("severity", ""),
                        "summary": doc_text,
                        "file_content": file_content,
                        "total_lines": len(full_text.split('\n')),
                        "service_name": sop.get("service_name", ""),
                    })
                elif source_type == "managed_openshift_docs":
                    github_results["results"].append({
                        "name": sop.get("file_name", sop.get("title", "")),
                        "path": sop.get("file_path", ""),
                        "repository": "openshift/openshift-docs",
                        "url": f"https://github.com/openshift/openshift-docs/blob/main/{sop.get('file_path', '')}",
                        "score": sop.get("score", 0) * 1000,
                        "language": "Markdown",
                        "ask_sre": True,
                        "similarity": sop.get("score", 0),
                        "category": sop.get("category", ""),
                        "severity": sop.get("severity", ""),
                        "summary": doc_text,
                        "file_content": file_content,
                        "total_lines": len(full_text.split('\n')),
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
                elif source_type == "managed_notifications":
                    github_results["results"].append({
                        "name": sop.get("file_name", sop.get("title", "")),
                        "path": sop.get("file_path", ""),
                        "repository": "openshift/managed-notifications",
                        "url": f"https://github.com/openshift/managed-notifications/blob/master/{sop.get('file_path', '')}",
                        "score": max(0.01, sop.get("score", 0)) * 1000,
                        "language": "JSON",
                        "ask_sre": True,
                        "similarity": sop.get("score", 0),
                        "category": sop.get("category", ""),
                        "severity": sop.get("severity", ""),
                        "summary": doc_text,
                        "file_content": file_content,
                        "total_lines": len(full_text.split('\n')),
                        "service_name": sop.get("service_name", ""),
                    })

            # Sort GitHub results: ops-sop first, then by score
            repo_priority = {"openshift/ops-sop": 0, "openshift/openshift-docs": 1, "openshift/managed-notifications": 2}
            github_results["results"].sort(
                key=lambda r: (repo_priority.get(r.get("repository", ""), 9), -r.get("score", 0))
            )

            # Update totals
            github_results["total"] = len(github_results.get("results", []))
            gitlab_results["total"] = len(gitlab_results.get("results", []))
            kcs_results["total"] = len(kcs_results.get("articles", []))

        return {
            "jira": jira_results,
            "sfdc": sfdc_results,
            "slack": slack_results,
            "kcs": kcs_results,
            "sop": sop_results,
            "github": github_results,
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

@app.route('/')
def index():
    return jsonify({'status': 'ok'}), 200


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
        print(f"🔑 Config tokens: RedHat={'SET' if config.get('redhat_token') else 'NOT SET'}, "
              f"GitHub={'SET' if config.get('github_token') else 'NOT SET'}, "
              f"GitLab={'SET' if config.get('gitlab_token') else 'NOT SET'}, "
              f"Slack XOXC={'SET' if config.get('slack_xoxc') else 'NOT SET'}, "
              f"Slack XOXD={'SET' if config.get('slack_xoxd') else 'NOT SET'}")

        # Search all sources
        results = search_all(query, max_results, slack_channels, config, jira_created_after, jira_created_before, custom_jql, jira_search_logic)

        # Only fetch linked JIRA tickets if searching for a specific case number
        # For keyword searches, let JIRA and SFDC search independently to avoid overwhelming the server
        is_case_number = re.match(r'^\d{8}$', query.strip())

        sfdc_cases = results.get('sfdc', {}).get('cases', [])
        if sfdc_cases:
            if not is_case_number:
                print(f"ℹ️ Skipping linked JIRA ticket fetch for keyword search (found {len(sfdc_cases)} SFDC cases)")

        if sfdc_cases and is_case_number:
            try:
                # Limit to top 10 cases to avoid overwhelming the server
                max_cases_to_process = 10
                cases_to_process = sfdc_cases[:max_cases_to_process]
                print(f"🔗 Fetching linked JIRA tickets for {len(cases_to_process)} SFDC cases (out of {len(sfdc_cases)} total)")

                # Get Jira credentials
                username = request.headers.get('X-Username', '')
                tokens_file = os.path.join(os.path.dirname(__file__), 'user_tokens.json')
                atlassian_email = ''
                atlassian_token = ''

                if username and os.path.exists(tokens_file):
                    with open(tokens_file, 'r') as f:
                        all_tokens = json.load(f)
                        user_tokens = all_tokens.get(username, {})
                        atlassian_email = user_tokens.get('atlassian_email', '')
                        atlassian_token = user_tokens.get('atlassian_token', '')

                if atlassian_email and atlassian_token:
                    print(f"  ✅ Jira credentials found for user {username}")
                    linked_jira_keys = set()

                    # Step 1: Collect all linked JIRA ticket keys from SFDC cases (using GraphQL + Red Hat token)
                    for case in cases_to_process:
                        case_number = case.get('case_number', '')
                        if case_number:
                            print(f"  🔍 Processing case {case_number} for linked JIRA tickets")
                            try:
                                # Use the existing get_case_escalations function
                                with app.test_request_context(headers={'X-Username': username}):
                                    escalations_data = get_case_escalations(case_number)
                                    escalations = escalations_data.get_json()

                                    external_trackers = escalations.get('external_trackers', [])
                                    print(f"    📊 Found {len(external_trackers)} external trackers for case {case_number}")

                                    for tracker in external_trackers:
                                        # Note: get_case_escalations() returns camelCase field names
                                        jira_key = tracker.get('resourceKey', '')
                                        if jira_key:
                                            linked_jira_keys.add(jira_key)
                                            print(f"    ✓ Extracted JIRA key: {jira_key}")
                            except Exception as e:
                                print(f"  ⚠️ Failed to fetch escalations for case {case_number}: {e}")

                    # Step 2: Fetch full JIRA ticket details (using Atlassian API + Atlassian token)
                    if linked_jira_keys:
                        print(f"  📋 Found {len(linked_jira_keys)} linked JIRA tickets: {linked_jira_keys}")

                        jira_issues = results.get('jira', {}).get('issues', [])
                        existing_keys = set(issue.get('key', '') for issue in jira_issues)

                        for jira_key in linked_jira_keys:
                            if jira_key not in existing_keys:
                                try:
                                    # Fetch full JIRA ticket details via Atlassian API
                                    jira_api_url = f"https://redhat.atlassian.net/rest/api/3/issue/{jira_key}"
                                    jira_resp = requests.get(
                                        jira_api_url,
                                        auth=(atlassian_email, atlassian_token),
                                        headers={'Accept': 'application/json'},
                                        timeout=10
                                    )

                                    if jira_resp.status_code == 200:
                                        issue_data = jira_resp.json()
                                        fields = issue_data.get('fields', {})

                                        # Parse all fields same as regular JIRA search
                                        issuetype = fields.get('issuetype', {})
                                        work_type = issuetype.get('name', 'N/A') if issuetype else 'N/A'

                                        product_list = fields.get('customfield_10868', [])
                                        product = ', '.join([p.get('value', '') for p in product_list]) if product_list else 'N/A'

                                        priority = fields.get('priority', {})
                                        priority_name = priority.get('name', 'N/A') if priority else 'N/A'

                                        assignee = fields.get('assignee', {})
                                        assignee_name = assignee.get('displayName', 'Unassigned') if assignee else 'Unassigned'

                                        reporter = fields.get('reporter', {})
                                        reporter_name = reporter.get('displayName', 'N/A') if reporter else 'N/A'

                                        security_level = fields.get('security', {})
                                        security_level_name = security_level.get('name', 'None') if security_level else 'None'

                                        components = fields.get('components', [])
                                        components_str = ', '.join([c.get('name', '') for c in components]) if components else 'None'

                                        project = fields.get('project', {})
                                        project_name = project.get('name', 'N/A') if project else 'N/A'

                                        description = fields.get('description', '')
                                        if isinstance(description, dict):
                                            description = extract_text_from_adf(description)

                                        jira_issues.append({
                                            'key': jira_key,
                                            'summary': fields.get('summary', 'No title'),
                                            'status': fields.get('status', {}).get('name', 'Unknown'),
                                            'work_type': work_type,
                                            'type': work_type,
                                            'product': product,
                                            'priority': priority_name,
                                            'assignee': assignee_name,
                                            'reporter': reporter_name,
                                            'security_level': security_level_name,
                                            'components': components_str,
                                            'project': project_name,
                                            'description': description,
                                            'url': f"https://issues.redhat.com/browse/{jira_key}",
                                            'linked_from_sfdc': True  # Mark as linked from SFDC
                                        })
                                        print(f"  ✅ Added linked JIRA ticket: {jira_key}")
                                    else:
                                        print(f"  ⚠️ Failed to fetch JIRA ticket {jira_key}: HTTP {jira_resp.status_code}")
                                except Exception as e:
                                    print(f"  ⚠️ Failed to fetch JIRA ticket {jira_key}: {e}")

                        # Update results with merged JIRA tickets
                        results['jira']['issues'] = jira_issues
                        results['jira']['total'] = len(jira_issues)
                    else:
                        print(f"  ℹ️ No linked JIRA tickets found for SFDC cases")
                else:
                    print(f"  ⚠️ No Jira credentials found (username: {username}, email: {'SET' if atlassian_email else 'NOT SET'}, token: {'SET' if atlassian_token else 'NOT SET'})")
            except Exception as e:
                print(f"  ❌ Error fetching linked JIRA tickets: {e}")
                import traceback
                traceback.print_exc()

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
    """Fetch first 20 lines of a GitHub file — reads local clone first, falls back to API"""
    try:
        data = request.get_json()
        repository = data.get('repository')
        path = data.get('path')

        if not repository or not path:
            return jsonify({'success': False, 'error': 'Missing repository or path'}), 400

        # For openshift/ops-sop, read directly from local clone (fast, no token needed)
        if repository == 'openshift/ops-sop':
            local_file = os.path.join(OPS_SOP_LOCAL_PATH, path)
            if os.path.isfile(local_file):
                with open(local_file, 'r', errors='ignore') as f:
                    content = f.read()
                lines = content.split('\n')[:20]
                return jsonify({
                    'success': True,
                    'content': '\n'.join(lines),
                    'total_lines': len(content.split('\n'))
                })

        # Fall back to GitHub API for other repos
        config = data.get('config', get_config())
        github_token = config.get('github_token', os.getenv('GITHUB_TOKEN', ''))

        if not github_token:
            return jsonify({'success': False, 'error': 'GitHub token not configured'}), 401

        url = f'https://api.github.com/repos/{repository}/contents/{path}'
        headers = {
            'Authorization': f'token {github_token}',
            'Accept': 'application/vnd.github.v3.raw'
        }

        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code == 404:
            return jsonify({'success': False, 'error': 'File not found'}), 404

        response.raise_for_status()

        content = response.text
        lines = content.split('\n')[:20]

        return jsonify({
            'success': True,
            'content': '\n'.join(lines),
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

        response = requests.get(url, headers=headers, params=params, timeout=10, verify=False)

        if response.status_code == 404:
            return jsonify({'success': False, 'error': 'File not found'}), 404

        response.raise_for_status()

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

        # Fetch Remote Links from JIRA (this is where Salesforce cases are linked in the Activity tab)
        remotelinks_url = f"https://redhat.atlassian.net/rest/api/3/issue/{jira_key}/remotelink"
        try:
            remotelinks_resp = requests.get(
                remotelinks_url,
                headers=headers_jira,
                auth=(atlassian_email, atlassian_token),
                timeout=10
            )
            if remotelinks_resp.status_code == 200:
                remote_links = remotelinks_resp.json()
                app.logger.info(f"📋 Found {len(remote_links)} remote links for {jira_key}")

                # Parse remote links looking for Salesforce cases
                for remote_link in remote_links:
                    link_obj = remote_link.get('object', {})
                    link_url = link_obj.get('url', '')
                    link_title = link_obj.get('title', '')

                    app.logger.info(f"  🔗 Remote link: {link_title} → {link_url}")

                    # Check if this is a Salesforce case link
                    if 'salesforce' in link_url.lower() or 'force.com' in link_url.lower():
                        # Try to extract case number from URL or title
                        import re
                        case_match = re.search(r'\b(0[34]\d{6})\b', link_title + ' ' + link_url)
                        if case_match:
                            case_number = case_match.group(1)

                            # Check if URL is already a Lightning URL
                            if 'lightning.force.com' in link_url and '/Case/' in link_url:
                                salesforce_id = link_url.split('/Case/')[1].split('/')[0]
                            else:
                                salesforce_id = ''

                            jira_linked_cases.append({
                                'case_number': case_number,
                                'salesforce_id': salesforce_id,
                                'summary': link_title,
                                'problem_statement': link_title,
                                'status': 'Unknown',
                                'url': f"https://access.redhat.com/support/cases/#/case/{case_number}",
                                'urls': {
                                    'customer_portal': f"https://access.redhat.com/support/cases/#/case/{case_number}"
                                },
                                'source': 'jira_remotelink'
                            })
                            app.logger.info(f"  ✅ Found SFDC case from remote link: {case_number}")
            else:
                app.logger.warning(f"⚠️ Failed to fetch remote links: {remotelinks_resp.status_code}")
        except Exception as e:
            app.logger.error(f"❌ Error fetching remote links: {e}")

        # Query Salesforce GraphQL for cases that have external links to this Jira ticket
        app.logger.info(f"🔍 Querying Salesforce for cases linked to {jira_key}")
        redhat_token = config.get('redhat_token', '')

        if redhat_token:
            try:
                access_token = get_sfdc_access_token(config)
                if access_token:
                    # Query for external links that point to this Jira ticket
                    # The JIRA key is stored in ExternalURL__c (e.g., https://redhat.atlassian.net/browse/OHSS-58849)
                    jira_url = f"https://redhat.atlassian.net/browse/{jira_key}"
                    graphql_query = """
                    query GetCasesForJira($jiraUrl: String!) {
                      redhat_support_uiapi {
                        query {
                          RedHatSupportExternalLink__c(
                            where: {
                              ExternalURL__c: { eq: $jiraUrl }
                            }
                            first: 10
                          ) {
                            edges {
                              node {
                                Id
                                Case__c
                                ExternalId { value }
                                ExternalLinkName { value }
                                ExternalURL { value }
                                ExternalType { value }
                                Status { value }
                              }
                            }
                          }
                        }
                      }
                    }
                    """

                    graphql_resp = requests.post(
                        "https://graphql.redhat.com",
                        headers={
                            "Authorization": f"Bearer {access_token}",
                            "Content-Type": "application/json",
                            "apollographql-client-name": "seekr-ai",
                            "apollographql-client-version": "1.0.0",
                            "Apollo-Require-Preflight": "true"
                        },
                        json={
                            "query": graphql_query,
                            "variables": {"jiraUrl": jira_url}
                        },
                        timeout=30
                    )

                    if graphql_resp.status_code == 200:
                        graphql_result = graphql_resp.json()
                        link_edges = graphql_result.get("data", {}).get("redhat_support_uiapi", {}).get("query", {}).get("RedHatSupportExternalLink__c", {}).get("edges", [])

                        app.logger.info(f"  📋 Found {len(link_edges)} SFDC cases with external links to {jira_key}")

                        for link_edge in link_edges:
                            link_node = link_edge.get("node", {})
                            case_id = link_node.get("Case__c", "")

                            if case_id:
                                # Now query for the case details to get case number and create Lightning URL
                                case_query = """
                                query GetCaseDetails($caseId: ID!) {
                                  redhat_support_uiapi {
                                    query {
                                      RedHatSupportCase(where: { Id: { eq: $caseId } }, first: 1) {
                                        edges {
                                          node {
                                            Id
                                            CaseNumber__c { value }
                                            Subject { value }
                                            Status { value }
                                          }
                                        }
                                      }
                                    }
                                  }
                                }
                                """

                                case_resp = requests.post(
                                    "https://graphql.redhat.com",
                                    headers={
                                        "Authorization": f"Bearer {access_token}",
                                        "Content-Type": "application/json",
                                        "apollographql-client-name": "seekr-ai",
                                        "apollographql-client-version": "1.0.0",
                                        "Apollo-Require-Preflight": "true"
                                    },
                                    json={
                                        "query": case_query,
                                        "variables": {"caseId": case_id}
                                    },
                                    timeout=10
                                )

                                if case_resp.status_code == 200:
                                    case_result = case_resp.json()
                                    case_edges = case_result.get("data", {}).get("redhat_support_uiapi", {}).get("query", {}).get("RedHatSupportCase", {}).get("edges", [])

                                    if case_edges:
                                        case_node = case_edges[0].get("node", {})
                                        case_number = case_node.get("CaseNumber__c", {}).get("value", "")
                                        salesforce_id = case_node.get("Id", "")
                                        summary = case_node.get("Subject", {}).get("value", "")
                                        status = case_node.get("Status", {}).get("value", "")

                                        if case_number:
                                            jira_linked_cases.append({
                                                'case_number': case_number,
                                                'salesforce_id': salesforce_id,
                                                'problem_statement': summary,
                                                'summary': summary,
                                                'status': status,
                                                'url': f"https://access.redhat.com/support/cases/#/case/{case_number}",
                                                'urls': {
                                                    'lightning': f"https://redhatsupport.lightning.force.com/lightning/r/Case/{salesforce_id}/view",
                                                    'customer_portal': f"https://access.redhat.com/support/cases/#/case/{case_number}"
                                                },
                                                'source': 'sfdc_graphql_external_link'
                                            })
                                            app.logger.info(f"  ✅ Found SFDC case {case_number} linked to {jira_key} with Lightning URL")
                    else:
                        try:
                            error_body = graphql_resp.json()
                            app.logger.error(f"⚠️ SFDC GraphQL query failed: {graphql_resp.status_code}, Error: {error_body}")
                        except:
                            app.logger.error(f"⚠️ SFDC GraphQL query failed: {graphql_resp.status_code}, Response: {graphql_resp.text[:500]}")
            except Exception as e:
                app.logger.error(f"❌ Error querying SFDC for linked cases: {e}")
                import traceback
                app.logger.debug(f"Traceback: {traceback.format_exc()}")

        # Check if OHSS ticket has linked cases in a custom field
        if issue_resp.status_code == 200:
            ohss_data = issue_resp.json()
            ohss_fields = ohss_data.get('fields', {})

            # Look for custom fields that might contain linked cases
            # Log all non-null custom fields to find the right one
            app.logger.info(f"📋 Searching OHSS {jira_key} custom fields for linked cases")

            import re

            # Search for custom fields containing linked cases
            app.logger.info(f"📋 Total custom fields in OHSS ticket: {len([k for k in ohss_fields.keys() if k.startswith('customfield_')])}")

            # Get field metadata to see display names
            try:
                fields_meta_url = f"https://redhat.atlassian.net/rest/api/3/field"
                fields_meta_resp = requests.get(
                    fields_meta_url,
                    headers=headers_jira,
                    auth=(atlassian_email, atlassian_token),
                    timeout=10
                )
                if fields_meta_resp.status_code == 200:
                    all_fields_meta = fields_meta_resp.json()
                    # Create a mapping of field ID to field name
                    field_id_to_name = {f['id']: f.get('name', f['id']) for f in all_fields_meta if 'id' in f}

                    # Log custom fields with their display names
                    app.logger.info("📋 Custom fields with display names (non-null only):")
                    for field_id in sorted([k for k in ohss_fields.keys() if k.startswith('customfield_')]):
                        field_value = ohss_fields.get(field_id)
                        display_name = field_id_to_name.get(field_id, field_id)
                        if field_value:
                            if isinstance(field_value, list) and len(field_value) > 0:
                                app.logger.info(f"  {field_id} ({display_name}): {json.dumps(field_value, indent=2)[:500]}")
                            elif isinstance(field_value, dict):
                                app.logger.info(f"  {field_id} ({display_name}): {json.dumps(field_value, indent=2)[:300]}")
            except Exception as e:
                app.logger.error(f"❌ Failed to fetch field metadata: {e}")

            # Dump ALL custom fields to find where Lightning URL is stored
            for field_name, field_value in ohss_fields.items():
                if field_name.startswith('customfield_') and field_value:
                    # Check if this field contains "lightning" or case number anywhere
                    field_str = json.dumps(field_value).lower()
                    if 'lightning' in field_str or '04529104' in field_str or '500nr' in field_str:
                        app.logger.info(f"  🎯 FOUND POTENTIAL FIELD {field_name}: {json.dumps(field_value, indent=2)[:2000]}")
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
                                    app.logger.info(f"  🔍 case_item fields: {list(case_item.keys())}")
                                    app.logger.info(f"  🔍 Full case_item: {case_item}")

                                    case_number = case_item.get('caseNumber') or case_item.get('case_number', '')
                                    salesforce_id = case_item.get('id', '')
                                    status = case_item.get('status', 'Unknown')
                                    summary = case_item.get('summary', f'Case {case_number}')

                                    # Check for existing URL fields (try multiple possible field names)
                                    sfdc_link = case_item.get('url') or case_item.get('link') or case_item.get('sfdcLink') or case_item.get('caseUrl') or case_item.get('lightningUrl') or ''
                                    app.logger.info(f"  🔍 Extracted sfdc_link: {sfdc_link}")

                                    # Validate case number format
                                    if re.match(r'^0[34]\d{6}$', str(case_number)):
                                        case_urls = {
                                            'customer_portal': f"https://access.redhat.com/support/cases/#/case/{case_number}"
                                        }

                                        # Use the Lightning URL from Jira if available
                                        if sfdc_link and 'lightning.force.com' in sfdc_link:
                                            case_urls['lightning'] = sfdc_link
                                            # Extract salesforce_id from URL if not already set
                                            if not salesforce_id and '/Case/' in sfdc_link:
                                                salesforce_id = sfdc_link.split('/Case/')[1].split('/')[0]
                                            app.logger.info(f"  ✅ Using Lightning URL from Jira: {sfdc_link}")
                                        elif salesforce_id:
                                            # Create Lightning URL from salesforce_id
                                            case_urls['lightning'] = f"https://redhatsupport.lightning.force.com/lightning/r/Case/{salesforce_id}/view"
                                            app.logger.info(f"  ✅ Created Lightning URL with salesforce_id: {salesforce_id}")

                                        jira_linked_cases.append({
                                            'case_number': case_number,
                                            'salesforce_id': salesforce_id,
                                            'problem_statement': summary,
                                            'summary': summary,
                                            'status': status,
                                            'url': f"https://access.redhat.com/support/cases/#/case/{case_number}",
                                            'urls': case_urls,
                                            'source': 'ohss_linked_cases_field'
                                        })
                                        app.logger.info(f"  ✅ Found SFDC case from OHSS field: {case_number} - {summary} ({status})")

        # If no cases found in custom fields, fall back to checking issue links
        if issue_resp.status_code == 200:
            issue_data = issue_resp.json()
            issue_links = issue_data.get('fields', {}).get('issuelinks', [])
            app.logger.info(f"📋 Found {len(issue_links)} issue links in Jira")

            # Note: We do NOT extract SFDC cases from linked Jira tickets
            # Only fetch from "Linked Cases" custom field or Salesforce GraphQL reverse query
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

        # Fallback: Extract case numbers from description and comments
        # This helps find cases that are mentioned in JIRA text but not formally linked
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
                    'problem_statement': f'Case {case_num}',
                    'summary': f'Case {case_num}',
                    'status': 'Unknown',
                    'url': f"https://access.redhat.com/support/cases/#/case/{case_num}",
                    'urls': {
                        'customer_portal': f"https://access.redhat.com/support/cases/#/case/{case_num}"
                    },
                    'source': 'jira_text'
                })
                app.logger.info(f"  ✅ Found SFDC case number in JIRA text: {case_num}")

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
        app.logger.info(f"  🔍 Slack credentials available: xoxc={'✅' if slack_xoxc else '❌'}, xoxd={'✅' if slack_xoxd else '❌'}, threads={len(slack_threads)}")
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

        # Enrich all linked cases with Lightning URLs by querying Salesforce GraphQL
        app.logger.info(f"📋 Enriching {len(linked_cases)} cases with Lightning URLs from Salesforce GraphQL")
        if redhat_token and len(linked_cases) > 0:
            try:
                access_token = get_sfdc_access_token(config)
                if access_token:
                    for case_dict in linked_cases:
                        case_number = case_dict.get('case_number', '')
                        if not case_number:
                            continue

                        # Query Salesforce GraphQL for this case to get salesforce_id, summary, and status
                        case_query = """
                        query GetCaseDetails($caseNumber: String!) {
                          redhat_support_uiapi {
                            query {
                              RedHatSupportCase(where: { CaseNumber__c: { eq: $caseNumber } }, first: 1) {
                                edges {
                                  node {
                                    Id
                                    Subject { value }
                                    Status { value }
                                  }
                                }
                              }
                            }
                          }
                        }
                        """

                        try:
                            case_resp = requests.post(
                                "https://graphql.redhat.com",
                                headers={
                                    "Authorization": f"Bearer {access_token}",
                                    "Content-Type": "application/json",
                                    "apollographql-client-name": "seekr-ai",
                                    "apollographql-client-version": "1.0.0",
                                    "Apollo-Require-Preflight": "true"
                                },
                                json={
                                    "query": case_query,
                                    "variables": {"caseNumber": case_number}
                                },
                                timeout=10
                            )

                            if case_resp.status_code == 200:
                                case_result = case_resp.json()
                                case_edges = case_result.get("data", {}).get("redhat_support_uiapi", {}).get("query", {}).get("RedHatSupportCase", {}).get("edges", [])

                                if case_edges:
                                    case_node = case_edges[0].get("node", {})
                                    salesforce_id = case_node.get("Id", "")
                                    subject = case_node.get("Subject", {}).get("value", "")
                                    status = case_node.get("Status", {}).get("value", "")

                                    if salesforce_id:
                                        case_dict['salesforce_id'] = salesforce_id
                                        if subject:
                                            case_dict['summary'] = subject
                                            case_dict['problem_statement'] = subject
                                        if status:
                                            case_dict['status'] = status
                                        if 'urls' not in case_dict:
                                            case_dict['urls'] = {}
                                        case_dict['urls']['lightning'] = f"https://redhatsupport.lightning.force.com/lightning/r/Case/{salesforce_id}/view"
                                        app.logger.info(f"  ✅ Enriched case {case_number}: {subject} ({status})")
                        except Exception as e:
                            app.logger.warning(f"  ⚠️ Failed to enrich case {case_number}: {e}")
                            continue
            except Exception as e:
                app.logger.error(f"❌ Failed to enrich cases with Lightning URLs: {e}")

        # Fallback: Search SFDC if no remote links found
        if redhat_token and len(linked_cases) == 0:
            try:
                # Get the same access token used for GraphQL
                access_token = get_sfdc_access_token(config)
                if not access_token:
                    app.logger.warning("⚠️ No access token available for SFDC REST search")
                else:
                    # Search for Salesforce cases that contain this Jira key
                    sfdc_search_url = "https://access.redhat.com/hydra/rest/search/v2/cases"
                    headers_sfdc = {
                        'Authorization': f'Bearer {access_token}',
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

                            case_urls = {
                                'customer_portal': f"https://access.redhat.com/support/cases/#/case/{case_number}"
                            }
                            if salesforce_id:
                                case_urls['lightning'] = f"https://redhatsupport.lightning.force.com/lightning/r/Case/{salesforce_id}/view"

                            linked_cases.append({
                                'case_number': case_number,
                                'salesforce_id': salesforce_id,
                                'summary': doc.get('subject', 'No summary'),
                                'problem_statement': doc.get('case_summaryEnglish', doc.get('case_summary', 'No problem statement')),
                                'status': doc.get('case_status', 'Unknown'),
                                'urls': case_urls,
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


@app.route('/api/jira/<jira_key>/escalations', methods=['GET'])
def get_jira_escalations(jira_key):
    """Fetch linked Salesforce cases for a JIRA ticket"""
    try:
        # Reuse the existing jira-issue-links logic
        username = request.headers.get('X-Username', '')

        # Forward the request to the existing endpoint logic
        with app.test_request_context(headers={'X-Username': username}):
            response = get_jira_issue_links(jira_key)

            # If it's a tuple (response, status_code), handle error
            if isinstance(response, tuple):
                return response

            # Extract the JSON data
            data = response.get_json()

            # Return in the format expected by frontend
            return jsonify({
                'linked_cases': data.get('cases', [])
            })

    except Exception as e:
        app.logger.error(f"Error fetching JIRA escalations for {jira_key}: {e}")
        return jsonify({'error': str(e), 'linked_cases': []}), 500


@app.route('/api/sfdc/case/<case_number>', methods=['GET'])
def get_sfdc_case_details(case_number):
    """Fetch full SFDC case details on-demand (lazy loading) - tries GraphQL first, falls back to REST"""
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

        # Try GraphQL first (works for Lightning-only cases)
        try:
            access_token = get_sfdc_access_token(config)

            graphql_query = """
            query GetCaseDetails($caseNumber: String!) {
              redhat_support_uiapi {
                query {
                  RedHatSupportCase(
                    where: { CaseNumber__c: { eq: $caseNumber } }
                    first: 1
                  ) {
                    edges {
                      node {
                        Id
                        CaseNumber__c { value }
                        Subject { value }
                        Description { value }
                        Status { value }
                        Priority { value }
                        SBR_Group__c { value }
                        SBT__c { value }
                        Owner {
                          ... on RedHatSupportGroup {
                            Id
                            Name { value }
                          }
                          ... on RedHatSupportUser {
                            Id
                            Name { value }
                          }
                        }
                        Product { Name { value } }
                        RedHatSupportAccount {
                          Name { value }
                          AccountNumber { value }
                        }
                      }
                    }
                  }
                }
              }
            }
            """

            graphql_endpoint = "https://graphql.redhat.com"
            print(f"🔍 Fetching case details via GraphQL for {case_number}...", flush=True)
            graphql_response = requests.post(
                graphql_endpoint,
                json={
                    'query': graphql_query,
                    'variables': {'caseNumber': case_number}
                },
                headers={
                    'Authorization': f'Bearer {access_token}',
                    'Content-Type': 'application/json',
                    'apollographql-client-name': 'seekr-ai',
                    'apollographql-client-version': '1.0.0',
                    'Apollo-Require-Preflight': 'true'
                },
                timeout=10
            )

            print(f"📡 GraphQL case detail response status: {graphql_response.status_code}", flush=True)
            if graphql_response.status_code != 200:
                print(f"⚠️ GraphQL error response: {graphql_response.text[:500]}", flush=True)

            if graphql_response.status_code == 200:
                result = graphql_response.json()
                edges = result.get("data", {}).get("redhat_support_uiapi", {}).get("query", {}).get("RedHatSupportCase", {}).get("edges", [])
                print(f"🔍 GraphQL returned {len(edges)} case(s) for {case_number}", flush=True)

                if edges:
                    node = edges[0].get("node", {})

                    # Extract Owner name from polymorphic Owner field (User or Group)
                    owner_obj = node.get("Owner", {})
                    if owner_obj and isinstance(owner_obj, dict):
                        owner_name_obj = owner_obj.get("Name", {})
                        owner_name = owner_name_obj.get("value", "N/A") if owner_name_obj else "N/A"
                    else:
                        owner_name = "N/A"

                    account_obj = node.get("RedHatSupportAccount", {})
                    account_name = account_obj.get("Name", {}).get("value", "N/A") if account_obj else "N/A"
                    account_number = account_obj.get("AccountNumber", {}).get("value", "N/A") if account_obj else "N/A"

                    product_obj = node.get("Product", {})
                    product = product_obj.get("Name", {}).get("value", "N/A") if product_obj else "N/A"

                    sbr = node.get("SBR_Group__c", {}).get("value", "N/A") if node.get("SBR_Group__c") else "N/A"
                    sbt = node.get("SBT__c", {}).get("value", "N/A") if node.get("SBT__c") else "N/A"

                    details = {
                        'owner': owner_name,
                        'account_number': account_number,
                        'account_name': account_name,
                        'sbt': sbt,
                        'sbr': sbr,
                        'description': node.get("Description", {}).get("value", "No description available"),
                        'salesforce_id': node.get("Id", ""),
                        'product': product
                    }

                    print(f"✅ GraphQL case details for {case_number}: owner={owner_name}, sbr={sbr}, sbt={sbt}")
                    return jsonify(details)

        except Exception as graphql_error:
            print(f"⚠️ GraphQL case detail failed for {case_number}: {graphql_error}, falling back to REST...")

        # Fall back to REST API (for older cases)
        access_token = get_sfdc_access_token(config)
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
            return jsonify({'error': f'Case not found'}), 404

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

        # Extract Salesforce Object ID and product for Lightning URL construction
        salesforce_id = case_detail.get('id', case_detail.get('caseId', ''))
        product = case_detail.get('product', 'N/A')

        details = {
            'owner': owner_name,
            'account_number': case_detail.get('accountNumber', 'N/A'),
            'account_name': account_name,
            'sbt': sbt_value,
            'sbr': case_detail.get('sbrGroup', 'N/A'),
            'description': case_detail.get('description', case_detail.get('caseDescription', 'No description available')),
            'salesforce_id': salesforce_id,
            'product': product
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

        kcs_articles = []
        redhat_docs = []
        slack_threads = []
        icm_tickets = []
        all_texts = []
        text_to_author = {}  # Map text to author name

        # Try GraphQL first for better Lightning case support
        try:
            app.logger.info(f"  🔍 Trying GraphQL for case {case_number} comments (including private)")

            # First, get the case ID and description
            graphql_query_case = """
            query GetCase($caseNumber: String!) {
              redhat_support_uiapi {
                query {
                  RedHatSupportCase(where: { CaseNumber__c: { eq: $caseNumber } }, first: 1) {
                    edges {
                      node {
                        Id
                        Description { value }
                      }
                    }
                  }
                }
              }
            }
            """

            graphql_resp = requests.post(
                "https://graphql.redhat.com",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                    "apollographql-client-name": "seekr-ai",
                    "apollographql-client-version": "1.0.0",
                    "Apollo-Require-Preflight": "true"
                },
                json={
                    "query": graphql_query_case,
                    "variables": {"caseNumber": case_number}
                },
                timeout=30
            )

            if graphql_resp.status_code != 200:
                app.logger.warning(f"  ⚠️ GraphQL case query failed with HTTP {graphql_resp.status_code}, falling back to REST API")
                raise Exception(f"GraphQL HTTP {graphql_resp.status_code}")

            graphql_result = graphql_resp.json()
            edges = graphql_result.get("data", {}).get("redhat_support_uiapi", {}).get("query", {}).get("RedHatSupportCase", {}).get("edges", [])

            if not edges:
                app.logger.warning(f"  ⚠️ GraphQL found no case for {case_number}, falling back to REST API")
                raise Exception("GraphQL returned no case")

            node = edges[0].get("node", {})
            case_id = node.get("Id", "")

            # Get case description
            description = node.get("Description", {}).get("value", "")
            if description:
                all_texts.append(description)

            # Now fetch comments using the case ID
            graphql_query_comments = """
            query GetCaseComments($caseId: ID!) {
              redhat_support_uiapi {
                query {
                  RedHatSupportCaseComment__c(where: { Case__c: { eq: $caseId } }, first: 200) {
                    edges {
                      node {
                        Id
                        Body__c { value }
                        IsAssociate__c { value }
                        IsCustomer__c { value }
                        LastModifiedByName__c { value }
                      }
                    }
                  }
                }
              }
            }
            """

            # Fetch comments using case ID
            app.logger.info(f"  🔍 Querying GraphQL for comments with Case ID: {case_id}")
            comments_resp = requests.post(
                "https://graphql.redhat.com",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                    "apollographql-client-name": "seekr-ai",
                    "apollographql-client-version": "1.0.0",
                    "Apollo-Require-Preflight": "true"
                },
                json={
                    "query": graphql_query_comments,
                    "variables": {"caseId": case_id}
                },
                timeout=30
            )

            app.logger.info(f"  📡 GraphQL comments response: HTTP {comments_resp.status_code}")

            if comments_resp.status_code == 200:
                comments_result = comments_resp.json()

                # Check for GraphQL errors
                if "errors" in comments_result:
                    app.logger.error(f"  ❌ GraphQL errors: {comments_result['errors']}")
                    raise Exception(f"GraphQL errors: {comments_result['errors']}")

                comment_edges = comments_result.get("data", {}).get("redhat_support_uiapi", {}).get("query", {}).get("RedHatSupportCaseComment__c", {}).get("edges", [])

                app.logger.info(f"  📊 GraphQL returned {len(comment_edges)} comment edges")

                associate_count = 0
                customer_count = 0
                ai_assistant_count = 0

                for i, comment_edge in enumerate(comment_edges):
                    comment_node = comment_edge.get("node", {})
                    comment_body = comment_node.get("Body__c", {}).get("value", "")
                    is_associate = comment_node.get("IsAssociate__c", {}).get("value", False)
                    is_customer = comment_node.get("IsCustomer__c", {}).get("value", False)

                    # Get author name (LastModifiedByName__c contains the comment author)
                    author_name = comment_node.get("LastModifiedByName__c", {}).get("value", "")

                    if comment_body:
                        all_texts.append(comment_body)
                        text_to_author[comment_body] = author_name

                        if is_associate:
                            associate_count += 1
                        if is_customer:
                            customer_count += 1

                        if "Support AI Assistant Service Account" in author_name:
                            ai_assistant_count += 1

                        # Log first comment preview
                        if i == 0:
                            preview = comment_body[:150].replace('\n', ' ')
                            app.logger.info(f"    First comment preview: {preview}... (Author: {author_name})")

                app.logger.info(f"  ✅ GraphQL fetched {len(comment_edges)} comments for case {case_number} (Associate: {associate_count}, Customer: {customer_count}, AI Assistant: {ai_assistant_count})")
            else:
                # Log the response body for debugging
                try:
                    error_body = comments_resp.json()
                    app.logger.error(f"  ❌ GraphQL comments HTTP {comments_resp.status_code}: {error_body}")
                except:
                    app.logger.error(f"  ❌ GraphQL comments HTTP {comments_resp.status_code}: {comments_resp.text[:200]}")
                app.logger.warning(f"  ⚠️ GraphQL comments query failed with HTTP {comments_resp.status_code}, falling back to REST API")
                raise Exception(f"GraphQL HTTP {comments_resp.status_code}")

        except Exception as graphql_error:
            # Fall back to REST API
            app.logger.info(f"  🔄 Falling back to REST API: {graphql_error}")

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

                app.logger.info(f"  📋 REST API found {len(comments)} comments for case {case_number}")

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
                app.logger.warning(f"  ⚠️ REST API failed to fetch comments: HTTP {comments_resp.status_code}")

        # Parse all texts for KCS, Docs, and Slack URLs (same regex as Jira implementation)
        app.logger.info(f"  📝 Parsing {len(all_texts)} texts for URLs (description + comments)")
        if len(all_texts) > 0:
            for i, text in enumerate(all_texts[:3]):  # Log first 3 texts for debugging
                preview = text[:200].replace('\n', ' ') if text else ''
                app.logger.info(f"    Text {i+1} preview: {preview}...")

        # Decode HTML entities before parsing URLs
        import html
        decoded_texts = [html.unescape(text) if text else '' for text in all_texts]

        if len(decoded_texts) > 0:
            app.logger.info(f"  🔓 Decoded {len(decoded_texts)} texts from HTML entities")
            # Log a preview of decoded text
            for i, text in enumerate(decoded_texts[:2]):
                if 'slack' in text.lower():
                    preview = text[:300].replace('\n', ' ')
                    app.logger.info(f"    Decoded text {i+1} (contains 'slack'): {preview}...")

        # Track KCS articles found by AI Assistant
        kcs_from_ai = {}  # Map of KCS URL to author

        for i, text in enumerate(decoded_texts):
            # Get the original text to look up author
            original_text = all_texts[i] if i < len(all_texts) else ""
            author = text_to_author.get(original_text, "")

            # KCS articles
            kcs_pattern = r'https?://access\.redhat\.com/(solutions|articles)/(\d+)'
            kcs_matches = re.findall(kcs_pattern, text)
            for match in kcs_matches:
                article_type, article_id = match
                url = f"https://access.redhat.com/{article_type}/{article_id}"

                # Track if this KCS was found in an AI Assistant comment
                if "Support AI Assistant Service Account" in author:
                    kcs_from_ai[url] = author

                if url not in [a['url'] for a in kcs_articles]:
                    # Add label if from AI Assistant
                    title = f'KCS {article_type.capitalize()} {article_id}'
                    if url in kcs_from_ai:
                        title += ' (Support AI Assistant Service Account)'

                    kcs_articles.append({
                        'id': article_id,
                        'url': url,
                        'title': title,
                        'from_ai_assistant': url in kcs_from_ai
                    })
                    app.logger.info(f"  ✅ Found KCS article: {article_id}{' (AI Assistant)' if url in kcs_from_ai else ''}")

            # Red Hat documentation
            docs_pattern = r'https?://(docs\.redhat\.com|access\.redhat\.com/documentation)/[^\s<>"\')]+'
            for doc_match in re.finditer(docs_pattern, text):
                url = doc_match.group(0)
                if url not in [d['url'] for d in redhat_docs]:
                    path_parts = url.rstrip('/').split('/')
                    title = path_parts[-1].replace('-', ' ').replace('_', ' ') if path_parts else 'Red Hat Documentation'
                    redhat_docs.append({'url': url, 'title': title})
                    app.logger.info(f"  ✅ Found Red Hat doc: {url[:80]}")

            # Slack threads (match both redhat-internal and redhat.enterprise domains)
            slack_pattern = r'(https?://(redhat-internal|redhat\.enterprise)\.slack\.com/archives/([A-Z0-9]+)/p(\d+))'
            for match in re.finditer(slack_pattern, text):
                url = match.group(1)  # Full URL
                channel_id = match.group(3)
                thread_ts = match.group(4)
                thread_ts_formatted = thread_ts[:10] + '.' + thread_ts[10:]

                if url not in [s['url'] for s in slack_threads]:
                    slack_threads.append({
                        'channel_id': channel_id,
                        'thread_ts': thread_ts_formatted,
                        'url': url,
                        'title': f'Slack Thread in {channel_id}'
                    })
                    app.logger.info(f"  ✅ Found Slack thread: {channel_id}/p{thread_ts} ({url})")

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

        # Log summary of what was found
        app.logger.info(f"  📊 Related Content for {case_number}: {len(kcs_articles)} KCS, {len(redhat_docs)} Docs, {len(slack_threads)} Slack, {len(icm_tickets)} ICM")

        # Resolve Slack channel IDs to channel names
        slack_xoxc = user_tokens_data.get('slack_xoxc', '') if user_tokens_data else ''
        slack_xoxd = user_tokens_data.get('slack_xoxd', '') if user_tokens_data else ''
        app.logger.info(f"  🔍 Slack credentials available: xoxc={'✅' if slack_xoxc else '❌'}, xoxd={'✅' if slack_xoxd else '❌'}, threads={len(slack_threads)}")
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
                                fetched_title = docs[0].get('publishedTitle', article['title'])
                                # Preserve AI Assistant label if present
                                if article.get('from_ai_assistant'):
                                    article['title'] = fetched_title + ' (Support AI Assistant Service Account)'
                                else:
                                    article['title'] = fetched_title
                                app.logger.info(f"  ✅ KCS {article_id} title: {article['title']}")
                    except Exception as e:
                        app.logger.warning(f"Failed to fetch KCS title for {article_id}: {e}")

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
    """Fetch external trackers (JIRA) linked to this SFDC case"""
    try:
        username = request.headers.get('X-Username', '')
        tokens_file = os.path.join(os.path.dirname(__file__), 'user_tokens.json')

        config = get_config()
        redhat_token = ''
        atlassian_email = ''
        atlassian_token = ''

        if username and os.path.exists(tokens_file):
            with open(tokens_file, 'r') as f:
                all_tokens = json.load(f)
                user_tokens = all_tokens.get(username, {})
                redhat_token = user_tokens.get('redhat_token', '')
                if redhat_token:
                    config['redhat_token'] = redhat_token
                atlassian_email = user_tokens.get('atlassian_email', '')
                atlassian_token = user_tokens.get('atlassian_token', '')

        external_trackers = []

        # First, try to fetch external trackers from Salesforce via GraphQL
        app.logger.info(f"🔍 Fetching external trackers from Salesforce for case {case_number}")

        try:
            access_token = get_sfdc_access_token(config)
            if access_token:
                # First get the case ID, then query for external links using the case ID
                # Step 1: Get case ID
                case_id_query = """
                query GetCaseId($caseNumber: String!) {
                  redhat_support_uiapi {
                    query {
                      RedHatSupportCase(where: { CaseNumber__c: { eq: $caseNumber } }, first: 1) {
                        edges {
                          node {
                            Id
                          }
                        }
                      }
                    }
                  }
                }
                """

                case_id_resp = requests.post(
                    "https://graphql.redhat.com",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json",
                        "apollographql-client-name": "seekr-ai",
                        "apollographql-client-version": "1.0.0",
                        "Apollo-Require-Preflight": "true"
                    },
                    json={
                        "query": case_id_query,
                        "variables": {"caseNumber": case_number}
                    },
                    timeout=30
                )

                if case_id_resp.status_code != 200:
                    app.logger.error(f"  ❌ Failed to get case ID: HTTP {case_id_resp.status_code}")
                    raise Exception(f"Failed to get case ID")

                case_id_result = case_id_resp.json()
                case_edges = case_id_result.get("data", {}).get("redhat_support_uiapi", {}).get("query", {}).get("RedHatSupportCase", {}).get("edges", [])

                if not case_edges:
                    app.logger.warning(f"  ⚠️ No case found for {case_number}")
                    raise Exception("No case found")

                case_id = case_edges[0].get("node", {}).get("Id", "")
                app.logger.info(f"  📍 Case ID: {case_id}")

                # Step 2: Query for external links using the case ID
                # Try different field name patterns since the schema is unclear
                graphql_query = """
                query GetExternalLinks($caseId: ID!) {
                  redhat_support_uiapi {
                    query {
                      RedHatSupportExternalLink__c(where: { Case__c: { eq: $caseId } }, first: 20) {
                        edges {
                          node {
                            Id
                            ExternalId { value }
                            ExternalLinkName { value }
                            ExternalURL { value }
                            ExternalType { value }
                            Status { value }
                          }
                        }
                      }
                    }
                  }
                }
                """

                graphql_resp = requests.post(
                    "https://graphql.redhat.com",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json",
                        "apollographql-client-name": "seekr-ai",
                        "apollographql-client-version": "1.0.0",
                        "Apollo-Require-Preflight": "true"
                    },
                    json={
                        "query": graphql_query,
                        "variables": {"caseId": case_id}
                    },
                    timeout=30
                )

                if graphql_resp.status_code == 200:
                    graphql_result = graphql_resp.json()

                    if "errors" in graphql_result:
                        app.logger.error(f"  ❌ GraphQL errors: {graphql_result['errors']}")
                    else:
                        # Check for external links from the separate query
                        tracker_edges = graphql_result.get("data", {}).get("redhat_support_uiapi", {}).get("query", {}).get("RedHatSupportExternalLink__c", {}).get("edges", [])

                        app.logger.info(f"  ✅ GraphQL found {len(tracker_edges)} external links")

                        for tracker_edge in tracker_edges:
                            tracker_node = tracker_edge.get("node", {})
                            external_id = tracker_node.get("ExternalId", {}).get("value", "")
                            external_name = tracker_node.get("ExternalLinkName", {}).get("value", "")
                            external_url = tracker_node.get("ExternalURL", {}).get("value", "")
                            external_type = tracker_node.get("ExternalType", {}).get("value", "")
                            status = tracker_node.get("Status", {}).get("value", "")

                            # Extract JIRA ticket ID from the URL (e.g., RFE-9044 from https://redhat.atlassian.net/browse/RFE-9044)
                            resource_key = None
                            if external_url:
                                # Parse URL to extract ticket ID
                                # Format: https://redhat.atlassian.net/browse/TICKET-ID or https://issues.redhat.com/browse/TICKET-ID
                                match = re.search(r'/browse/([A-Z]+-\d+)', external_url)
                                if match:
                                    resource_key = match.group(1)
                                else:
                                    # Fallback to external_name if URL parsing fails
                                    resource_key = external_name or external_id
                            else:
                                resource_key = external_name or external_id

                            if resource_key and external_url:
                                external_trackers.append({
                                    'resourceKey': resource_key,
                                    'resourceURL': external_url,
                                    'title': resource_key,  # Use ticket ID as title
                                    'status': status or 'Unknown',
                                    'system': external_type or 'Jira'
                                })
                                app.logger.info(f"    ✓ {resource_key} ({external_type or 'External Link'}): {external_url}")
                else:
                    try:
                        error_body = graphql_resp.json()
                        app.logger.error(f"  ❌ GraphQL HTTP {graphql_resp.status_code}: {error_body}")
                    except:
                        app.logger.error(f"  ❌ GraphQL HTTP {graphql_resp.status_code}: {graphql_resp.text[:300]}")
        except Exception as e:
            app.logger.warning(f"  ⚠️ Failed to fetch from Salesforce GraphQL: {e}")
            import traceback
            app.logger.debug(f"Traceback: {traceback.format_exc()}")

        # If no external trackers found in Salesforce and we have Jira credentials, search Jira
        if not external_trackers and atlassian_email and atlassian_token:
            app.logger.info(f"🔍 Searching Jira for tickets linked to case {case_number}")

            # Search Jira for tickets that mention this case number in description or comments
            # Search across all projects to catch RFE, OHSS, SREP, etc.
            jql = f'text ~ "{case_number}" ORDER BY created DESC'

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

            if jira_resp.status_code == 200:
                jira_data = jira_resp.json()
                issues = jira_data.get('issues', [])

                app.logger.info(f"  ✅ Found {len(issues)} Jira tickets mentioning case {case_number}")

                for issue in issues:
                    key = issue.get('key', 'Unknown')
                    fields = issue.get('fields', {})
                    summary = fields.get('summary', 'No title')
                    status_obj = fields.get('status', {})
                    status = status_obj.get('name', 'Unknown') if isinstance(status_obj, dict) else 'Unknown'

                    # Avoid duplicates from GraphQL results
                    if not any(t['resourceKey'] == key for t in external_trackers):
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
    print("  • MCP Server for SOP search: ask-sre server must be running on MCP_SERVER_URL")
    print("  • Set MCP_SERVER_URL env var (default: http://localhost:8000)\n")
    print("Press CTRL+C to stop")
    print("=" * 70 + "\n")

    app.run(debug=True, host='0.0.0.0', port=5500)
