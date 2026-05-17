# 🔍 Unified Search Tool

Search across **Jira, Slack, SFDC, and KCS** simultaneously with a single query!

[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Flask](https://img.shields.io/badge/flask-3.1.0-green.svg)](https://flask.palletsprojects.com/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

---

## 📖 Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Installation](#installation)
  - [Method 1: Podman/Docker (Recommended)](#method-1-podmandocker-recommended)
  - [Method 2: Local Installation](#method-2-local-installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [How to Get Tokens](#how-to-get-tokens)
- [Troubleshooting](#troubleshooting)

---

## ✨ Features

| System | Purpose | Search Capability |
|--------|---------|------------------|
| **Jira** | Issue tracking | Search by summary, description, assignee, labels |
| **Slack** | Team communication | Full-text search with **direct message links** |
| **SFDC** | Customer support cases | Case number, subject, description |
| **KCS** | Red Hat Knowledge Base | Solution articles, error messages |

**Key Features:**
- ⚡ **Parallel Search** - All systems searched simultaneously
- 🔗 **Direct Slack Links** - Click to jump to exact message in Slack
- 💾 **Persistent Credentials** - Save once, auto-load next time
- 🎯 **Filter Results** - Show/hide each system's results
- 🚀 **Fast** - Results in seconds

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Web Browser                           │
│                 http://localhost:5500                    │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│              Flask Application                           │
│            (unified_search.py)                           │
│                                                          │
│  ┌──────────────────────────────────────────────────┐   │
│  │         Settings UI                              │   │
│  │  - Save credentials to .saved_credentials.json   │   │
│  │  - Load credentials on startup                   │   │
│  │  - Permissions: 600 (read/write owner only)      │   │
│  └──────────────────────────────────────────────────┘   │
│                                                          │
│  ┌──────────────────────────────────────────────────┐   │
│  │      Search Orchestrator                         │   │
│  │  - Parallel execution (ThreadPoolExecutor)       │   │
│  │  - Timeout handling (30s per search)             │   │
│  │  - Error recovery                                │   │
│  └──────────────────────────────────────────────────┘   │
└───┬──────────┬──────────┬──────────┬───────────────────┘
    │          │          │          │
    ▼          ▼          ▼          ▼
┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐
│ Jira   │ │ Slack  │ │ SFDC   │ │  KCS   │
│ Search │ │ Search │ │ Search │ │ Search │
└───┬────┘ └───┬────┘ └───┬────┘ └───┬────┘
    │          │          │          │
    ▼          ▼          ▼          ▼
┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐
│  MCP   │ │ Web API│ │Requests│ │Requests│
│Atlassian│ │ +MCP  │ │Library │ │Library │
└───┬────┘ └───┬────┘ └───┬────┘ └───┬────┘
    │          │          │          │
    ▼          ▼          ▼          ▼
┌─────────────────────────────────────────┐
│         External Systems                │
│  - issues.redhat.com (Jira)            │
│  - redhat.enterprise.slack.com         │
│  - redhat.my.salesforce.com            │
│  - access.redhat.com (KCS)             │
└─────────────────────────────────────────┘
```

**How It Works:**
1. User enters search query in web interface
2. Flask app spawns 4 parallel search threads
3. Each thread searches one system with its API
4. Results combined and displayed in unified interface
5. Click on Slack result → Direct link to message

---

## 📦 Installation

### Method 1: Podman/Docker (Recommended)

**Fastest and simplest - everything in a container!**

#### Prerequisites
- Podman or Docker installed

#### Install Podman

**Fedora/RHEL:**
```bash
sudo dnf install podman
```

**Ubuntu/Debian:**
```bash
sudo apt install podman
```

**macOS:**
```bash
brew install podman
podman machine init
podman machine start
```

#### Quick Start

**Step 1: Clone Repository**
```bash
git clone https://github.com/sodoityu/SeekrAI1.git
cd SeekrAI1
```

**Step 2: Build Image**
```bash
podman build -t unified-search:latest .
```

**Step 3: Run with Your Credentials**

```bash
podman run -d \
  --network=host \
  --name unified-search \
  -e SLACK_XOXC_TOKEN='your-xoxc-token' \
  -e SLACK_XOXD_TOKEN='your-xoxd-token' \
  -e JIRA_URL='https://your-company.atlassian.net' \
  -e JIRA_EMAIL='your-email@company.com' \
  -e JIRA_API_TOKEN='your-jira-api-token' \
  -e RH_API_OFFLINE_TOKEN='your-redhat-offline-token' \
  unified-search:latest
```

**Step 4: Open Browser**
```
http://localhost:5500
```

**Done!** Start searching! ✅

#### Using Template Script (Easier)

```bash
# Copy template
cp RUN_WITH_MY_TOKENS.sh.example RUN_WITH_MY_TOKENS.sh

# Edit with your tokens
nano RUN_WITH_MY_TOKENS.sh

# Run it
chmod +x RUN_WITH_MY_TOKENS.sh
./RUN_WITH_MY_TOKENS.sh
```

---

### Method 2: Local Installation

**For development or when you don't want containers.**

#### Step 1: Install Python 3.10+

**macOS:**
```bash
brew install python@3.10
```

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install python3.10 python3.10-venv python3-pip
```

**Fedora/RHEL:**
```bash
sudo dnf install python3.10
```

**Windows:**
Download from [python.org](https://www.python.org/downloads/)

#### Step 2: Install Podman (for Slack MCP support)

**Required for Slack search to work!**

```bash
# Fedora/RHEL
sudo dnf install podman

# Ubuntu/Debian
sudo apt install podman

# macOS
brew install podman
podman machine init
podman machine start
```

#### Step 3: Clone Repository

```bash
git clone https://github.com/sodoityu/SeekrAI1.git
cd SeekrAI1
```

#### Step 4: Install Dependencies

```bash
# Install Python packages
pip3 install -r requirements.txt

# Pull Slack MCP container (for Slack search)
podman pull quay.io/redhat-ai-tools/slack-mcp
```

#### Step 5: Configure Credentials

**Option A: Environment Variables**
```bash
export SLACK_XOXC_TOKEN='your-xoxc-token'
export SLACK_XOXD_TOKEN='your-xoxd-token'
export JIRA_URL='https://your-company.atlassian.net'
export JIRA_EMAIL='your-email@company.com'
export JIRA_API_TOKEN='your-jira-api-token'
export RH_API_OFFLINE_TOKEN='your-redhat-offline-token'
```

**Option B: Edit .mcp.json**
```bash
nano .mcp.json
# Replace placeholders with your actual tokens
```

#### Step 6: Run

```bash
./run.sh
```

**Or directly:**
```bash
python3 unified_search.py
```

**Step 7: Open Browser**
```
http://localhost:5500
```

---

## ⚙️ Configuration

### How to Get Tokens

#### 1. Slack Tokens (xoxc + xoxd)

**Get from Browser Cookies:**

1. Open Slack in browser: https://your-workspace.slack.com
2. Press F12 (Developer Tools)
3. Go to "Application" tab (Chrome) or "Storage" tab (Firefox)
4. Click "Cookies" → Your Slack workspace URL
5. Find cookie named `d` → Copy **Value** → This is `SLACK_XOXD_TOKEN`
6. Go to "Network" tab → Refresh page → Click any API request
7. Look in "Request Headers" → Find `Authorization: Bearer xoxc-...`
8. Copy the `xoxc-...` part → This is `SLACK_XOXC_TOKEN`

#### 2. Jira API Token

1. Go to: https://id.atlassian.com/manage-profile/security/api-tokens
2. Click "Create API token"
3. Label: `unified-search-tool`
4. Click "Create"
5. **Copy the token immediately** (you won't see it again!)

**You also need:**
- `JIRA_URL`: Your Jira instance (e.g., `https://your-company.atlassian.net`)
- `JIRA_EMAIL`: Your email address

#### 3. Red Hat Offline Token (for SFDC/KCS)

1. Go to: https://access.redhat.com/management/api
2. Click "Generate Token"
3. Copy the offline token (starts with `eyJ...`)

#### 4. SFDC Session ID (Alternative)

1. Login to Salesforce
2. Press F12 (Developer Tools)
3. Go to "Application" → "Cookies"
4. Find cookie named `sid` → Copy the value

---

### Configuration Methods

**Method 1: Environment Variables (Recommended for Podman)**
```bash
-e SLACK_XOXC_TOKEN='your-token'
-e SLACK_XOXD_TOKEN='your-token'
```

**Method 2: UI Settings (Recommended for Local)**
1. Open http://localhost:5500
2. Click ⚙️ Settings (top right)
3. Enter all tokens
4. Click 💾 Save & Remember
5. Auto-loads next time! ✅

**Method 3: Config Files**
Edit `.mcp.json` with your tokens.

**Priority:** Environment Variables > UI Settings > Config Files

---

## 🚀 Usage

### Search

1. Open: http://localhost:5500
2. Enter search query (e.g., `ROSA cluster creation failed`)
3. Click "Search All"
4. Results appear from all 4 systems!

### Filter Results

- Toggle each system on/off with buttons on left sidebar
- See result counts for each system

### Slack Direct Links

Click "View in Slack" on any Slack result to jump directly to that message!

Format: `https://workspace.slack.com/archives/CHANNEL_ID/pTIMESTAMP`

---

## 🆘 Troubleshooting

### "No results from Slack"

**If using Podman:**
Make sure you used `--network=host` flag:
```bash
podman run -d --network=host ...
```

**If running locally:**
Make sure Slack MCP container is accessible:
```bash
podman pull quay.io/redhat-ai-tools/slack-mcp
```

### "Port 5500 already in use"

```bash
# Kill process using port 5500
lsof -ti:5500 | xargs kill -9

# Or use different port
podman run -p 5501:5500 ... unified-search:latest
# Access at: http://localhost:5501
```

### "Container exits immediately"

```bash
# Check logs
podman logs unified-search

# Common issues:
# - Missing MCP SDK: Rebuild image (podman build ...)
# - Port conflict: Use different port
```

### "Slack tokens expired"

Slack tokens expire after 6-12 months. Get fresh tokens:
1. Open Slack in browser
2. Get new xoxc/xoxd tokens from cookies
3. Update your configuration
4. Restart container or app

### "Jira authentication failed"

1. Check email is correct
2. Check API token is valid
3. Regenerate API token if needed: https://id.atlassian.com/manage-profile/security/api-tokens

---

## 🔧 Container Management

```bash
# View logs
podman logs -f unified-search

# Stop container
podman stop unified-search

# Start again
podman start unified-search

# Restart
podman restart unified-search

# Remove
podman rm -f unified-search

# Rebuild image
podman build -t unified-search:latest .
```

---

## 📝 File Structure

```
SeekrAI1/
├── unified_search.py              # Main Flask application
├── slack_search_standalone.py     # Slack integration
├── templates_unified/             # Web UI templates
│   └── unified_index.html
├── requirements.txt               # Python dependencies
├── Dockerfile                     # Container image definition
├── run.sh                         # Startup script
├── .mcp.json                      # MCP configuration template
├── .env.example                   # Environment variable template
├── RUN_WITH_MY_TOKENS.sh.example  # Quick setup template
└── README.md                      # This file
```

---

## 🔒 Security

**Files that are NEVER committed:**
- `.saved_credentials.json` - Your saved credentials
- `RUN_WITH_MY_TOKENS.sh` - Your setup script with real tokens
- `.env` - Environment variables

**Protected by .gitignore** ✅

**When sharing:**
1. Copy the template: `RUN_WITH_MY_TOKENS.sh.example`
2. Add your tokens
3. Your real tokens stay private!

---

## 🎯 Summary

**Podman (Recommended):**
```bash
podman build -t unified-search:latest .
podman run -d --network=host -e SLACK_XOXC_TOKEN='...' unified-search:latest
```

**Local:**
```bash
pip3 install -r requirements.txt
./run.sh
# Configure via UI at http://localhost:5500
```

**That's it!** Start searching across all 4 systems! 🚀

---

## 📄 License

MIT License - See LICENSE file

---

## 🤝 Contributing

Issues and pull requests welcome at: https://github.com/sodoityu/SeekrAI1

---

**Questions?** Check the troubleshooting section above or open an issue on GitHub!
