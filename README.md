# Unified Search - Web UI for Jira, SFDC, and Slack

Search across **Jira**, **SFDC/KCS**, and **Slack** simultaneously from a single web interface.

## 🎯 What is this?

A Flask web application that provides unified search across:
- **Jira** - Search issues and tickets
- **SFDC/KCS** - Search Red Hat Knowledge Centered Service articles
- **Slack** - Search messages across all channels

All from one simple web interface at `http://localhost:5500`

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Browser (localhost:5500)                │
│                   ┌─────────────────────┐                   │
│                   │   Search Interface  │                   │
│                   └──────────┬──────────┘                   │
└──────────────────────────────┼──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│              Flask App (unified_search.py)                  │
│  ┌────────────┐  ┌────────────┐  ┌──────────────────────┐  │
│  │Jira Search │  │SFDC Search │  │ Slack Search (MCP)   │  │
│  └─────┬──────┘  └─────┬──────┘  └──────────┬───────────┘  │
└────────┼───────────────┼────────────────────┼──────────────┘
         │               │                    │
         ▼               ▼                    ▼
┌──────────────┐ ┌──────────────┐  ┌──────────────────────┐
│ Jira API     │ │ Red Hat API  │  │ Slack MCP Server     │
│ (REST)       │ │ (SSO+SFDC)   │  │ (slack_search_       │
│              │ │              │  │  standalone.py)      │
└──────────────┘ └──────────────┘  └──────────────────────┘
```

**Key Components:**
- **unified_search.py** - Main Flask web server (port 5500)
- **slack_search_standalone.py** - Slack MCP server integration
- **templates_unified/** - HTML templates for web UI
- **Credentials** - Stored in Flask session or environment variables

---

## 📦 Method 1: Using Podman (Recommended)

**Fastest way to run - no local dependencies needed!**

### Step 1: Build the image

```bash
podman build -t unified-search:latest .
```

### Step 2: Get your credentials

See [How to Get Credentials](#-how-to-get-credentials) section below.

### Step 3: Create your run script

```bash
cp RUN_WITH_MY_TOKENS.sh.example RUN_WITH_MY_TOKENS.sh
nano RUN_WITH_MY_TOKENS.sh  # Edit and add your tokens
```

Replace these placeholders with your actual credentials:
- `YOUR-SLACK-XOXC-TOKEN-HERE`
- `YOUR-SLACK-XOXD-TOKEN-HERE`
- `your-email@redhat.com`
- `YOUR-JIRA-API-TOKEN-HERE`
- `YOUR-REDHAT-OFFLINE-TOKEN-HERE`

### Step 4: Run the container

```bash
./RUN_WITH_MY_TOKENS.sh
```

### Step 5: Open in browser

Open `http://localhost:5500` and start searching!

### Useful Podman commands

```bash
# View logs
podman logs -f unified-search

# Stop container
podman stop unified-search

# Restart container
podman start unified-search

# Remove container
podman rm unified-search
```

---

## 🛠️ Method 2: Local Installation

### Prerequisites

- **Python 3.8+** (Python 3.13+ recommended)
- **pip** package manager

### Installation Steps

#### **For Fedora Linux:**

```bash
# Install Python 3.13
sudo dnf install python3.13 python3.13-pip

# Clone the repository (if not already)
cd /path/to/unified-search

# Install dependencies
pip3.13 install -r requirements.txt
```

#### **For macOS:**

```bash
# Install Python 3.13 with Homebrew
brew install python@3.13

# Install dependencies
pip3.13 install -r requirements.txt
```

#### **For Ubuntu/Debian:**

```bash
# Install Python 3.13
sudo apt update
sudo apt install python3.13 python3.13-pip

# Install dependencies
pip3.13 install -r requirements.txt
```

### Setup Credentials

Create a `.env` file from the template:

```bash
cp .env.example .env
nano .env  # Edit and add your credentials
```

Load the environment variables:

```bash
source .env
```

### Run the Application

```bash
python3 unified_search.py
```

Open `http://localhost:5500` in your browser.

---

## 🔑 How to Get Credentials

### 1. Jira Credentials

**JIRA_EMAIL:**
- Your Red Hat email address (e.g., `yourname@redhat.com`)

**JIRA_API_TOKEN:**
1. Go to https://id.atlassian.com/manage-profile/security/api-tokens
2. Click **Create API token**
3. Give it a name (e.g., "Unified Search")
4. Copy the token

### 2. SFDC/KCS Credentials

**RH_API_OFFLINE_TOKEN:**
1. Go to https://access.redhat.com/management/api
2. Click **Generate Token** under "Offline Access"
3. Copy the offline token

### 3. Slack Credentials

**SLACK_XOXC_TOKEN and SLACK_XOXD_TOKEN:**

1. Open Slack in your browser (https://redhat.enterprise.slack.com)
2. Open Developer Tools (F12)
3. Go to **Application** → **Cookies** → `https://redhat.enterprise.slack.com`
4. Find and copy:
   - Cookie named `d` → This is your **SLACK_XOXD_TOKEN**
   - Cookie named `d-s` starts with `xoxc-` → This is your **SLACK_XOXC_TOKEN**

**Alternative method (from browser storage):**
1. Open Developer Tools (F12) → **Console** tab
2. Type: `JSON.parse(localStorage.localConfig_v2)["teams"]`
3. Find your workspace and copy the `token` (starts with `xoxc-`)

---

## 🎨 Using the Web Interface

1. **Open** `http://localhost:5500`

2. **Configure credentials** (if not using environment variables):
   - Click **Settings** (top right corner)
   - Enter your Jira, SFDC, and Slack credentials
   - Click **Save**

3. **Search**:
   - Enter your search query
   - Select which services to search (Jira, SFDC, Slack)
   - Click **Search**

4. **Results**:
   - Results from all selected services appear in separate tabs
   - Click on any result to view details
   - For Jira: Direct links to issues
   - For SFDC: Links to KCS articles
   - For Slack: Message content with channel and timestamp

---

## 🔧 Troubleshooting

### Slack returns 0 results

**Problem:** Slack search works in browser but returns 0 results in container.

**Solution:**
- Make sure you're using `--network=host` flag with Podman
- Verify MCP SDK is installed: `pip list | grep mcp`
- Check Slack tokens are correct (xoxc and xoxd)
- Verify tokens in Settings page match environment variables

### Jira authentication fails

**Problem:** "Unauthorized" or "401" errors from Jira.

**Solution:**
- Verify your JIRA_EMAIL is correct
- Regenerate your Jira API token from https://id.atlassian.com/manage-profile/security/api-tokens
- Make sure there are no extra spaces in email or token

### SFDC/KCS search fails

**Problem:** "Token expired" or "Invalid token" errors.

**Solution:**
- Regenerate your offline token from https://access.redhat.com/management/api
- The token format should be a long string (100+ characters)
- Make sure you copied the entire token

### Port 5500 already in use

**Problem:** "Address already in use" error.

**Solution:**
```bash
# Find what's using port 5500
sudo lsof -i :5500

# Kill the process or use a different port
# Edit unified_search.py and change the port at the bottom:
# app.run(debug=True, host='0.0.0.0', port=5500)
```

### Container won't start

**Problem:** Podman container exits immediately.

**Solution:**
```bash
# Check logs
podman logs unified-search

# Common issues:
# - Missing environment variables
# - Python syntax errors
# - Port conflicts

# Rebuild the image
podman build -t unified-search:latest .
./RUN_WITH_MY_TOKENS.sh
```

---

## 📁 File Structure

```
.
├── unified_search.py              # Main Flask application
├── slack_search_standalone.py     # Slack MCP server integration
├── requirements.txt               # Python dependencies
├── Dockerfile                     # Container build instructions
├── RUN_WITH_MY_TOKENS.sh.example  # Template for Podman run script
├── .env.example                   # Template for environment variables
├── templates_unified/             # HTML templates for web UI
│   ├── index.html                 # Main search page
│   └── settings.html              # Credentials settings page
└── README.md                      # This file
```

---

## 🔐 Security Notes

1. **Never commit credentials** to Git:
   - `RUN_WITH_MY_TOKENS.sh` is in `.gitignore`
   - `.env` is in `.gitignore`
   - `.saved_credentials.json` is in `.gitignore`

2. **Credentials priority**:
   - Environment variables (Podman `-e` flags or `source .env`)
   - UI Settings page (stored in Flask session)
   - Use environment variables for Podman, UI settings for local development

3. **Token security**:
   - Slack tokens are sensitive - treat like passwords
   - Jira API tokens can be revoked anytime at Atlassian
   - SFDC offline tokens should be regenerated periodically

---

## 🚀 Quick Start Summary

**Podman (5 minutes):**
```bash
podman build -t unified-search:latest .
cp RUN_WITH_MY_TOKENS.sh.example RUN_WITH_MY_TOKENS.sh
nano RUN_WITH_MY_TOKENS.sh  # Add your tokens
./RUN_WITH_MY_TOKENS.sh
# Open http://localhost:5500
```

**Local (10 minutes):**
```bash
pip3 install -r requirements.txt
cp .env.example .env
nano .env  # Add your credentials
source .env
python3 unified_search.py
# Open http://localhost:5500
```

---

## 📝 License

Internal Red Hat tool - not for public distribution.

---

## 🤝 Contributing

Report issues or suggestions to the development team.

---

**Questions?** Check the Troubleshooting section or reach out to the team!
