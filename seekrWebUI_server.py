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
import getpass
from pathlib import Path

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

        # Forward to backend search API
        response = requests.post(
            f'{UNIFIED_SEARCH_API}/search',
            json={'query': query, 'config': config, 'sources': sources},
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
