# 🔍 Unified Search Tool

Search across Jira, SFDC, Slack, and KCS simultaneously with a single query!

---

## 🚀 **QUICK START** (No Poetry Knowledge Needed!)

```bash
cd /home/jayu/asksre/ask-sre/finaltoolMay17
./run.sh
```

Then open: **http://localhost:5500**

Click **⚙️ Settings** → Enter credentials → Save → Start searching!

**✅ All tests passed!** See [TEST_RESULTS.md](TEST_RESULTS.md) for details.

---

[![Python](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![Flask](https://img.shields.io/badge/flask-3.1.0-green.svg)](https://flask.palletsprojects.com/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

---

## 📖 Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Screenshots](#screenshots)
- [Quick Start](#quick-start)
- [For End Users (Binary Distribution)](#for-end-users-binary-distribution)
- [Installation](#installation)
- [Usage](#usage)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)
- [Documentation](#documentation)
- [Building & Distribution](#building--distribution)
- [Contributing](#contributing)

---

## Overview

The Unified Search Tool combines search across four Red Hat internal systems:

| System | Purpose | Results |
|--------|---------|---------|
| 🔧 **Jira** | Bug tracking, project management | Issues, tickets |
| 🎫 **SFDC** | Customer support cases | Support tickets |
| 💬 **Slack** | Team communications | Messages, threads |
| 📚 **KCS** | Knowledge base | Articles, solutions |

**One search query → All four systems → Unified results**

---

## Features

### ✨ Core Features

- **🚀 Parallel Search** - Search all 4 systems simultaneously (50-60s total vs 60-80s sequential)
- **📊 Category Filtering** - Show all results or filter by system
- **🎨 Modern UI** - Red Hat branded design with dark theme
- **📈 Result Counts** - See how many results from each source
- **🔗 Direct Links** - Click to open items in their original systems
- **💬 Slack Channel Filter** - Filter Slack results by specific channels
- **📝 Full Text Display** - See complete message content without truncation

### 🎯 Advanced Features

- **Real-time Search** - Live updates as you type
- **Result Caching** - Faster repeat searches
- **Error Handling** - Graceful degradation if one system fails
- **Mobile Responsive** - Works on all devices
- **Keyboard Shortcuts** - Enter to search, Esc to clear

---

## Screenshots

### Main Interface
```
┌────────────────────────────────────────────────────────────┐
│ 🔍  Red Hat Unified Search                  👤 User ▾     │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  ┌─────────────┐  ┌──────────────────────────────────┐   │
│  │ Filters     │  │  Search box...               🔎  │   │
│  │             │  └──────────────────────────────────┘   │
│  │ All    [72] │                                          │
│  │ SFDC   [20] │  🔧 JIRA - 9 Issues                     │
│  │ Slack  [42] │  ├─ OHSS-1234: Allow custom...          │
│  │ Jira    [9] │  └─ ...                                 │
│  │ KCS     [1] │                                          │
│  │             │  🎫 SFDC - 20 Cases                      │
│  │             │  ├─ 03796358: Network issue...          │
│  │             │  └─ ...                                 │
│  └─────────────┘                                          │
└────────────────────────────────────────────────────────────┘
```

---

## Quick Start

### Prerequisites

- Python 3.13+
- Poetry (Python package manager)
- Docker or Podman
- Access to Red Hat internal systems

### 1-Minute Setup

```bash
# Clone repository
git clone https://github.com/sodoityu/SeekrAI1.git
cd SeekrAI1/finaltool

# Install dependencies
poetry install

# Configure credentials (see SETUP.md)
# Edit unified_search.py and .mcp.json

# Start server
poetry run python unified_search.py

# Open browser
# Visit http://localhost:5500
```

**For detailed setup**, see [SETUP.md](SETUP.md)

---

## For End Users (Binary Distribution)

### 🚀 No Installation Needed!

**Download and run the binary - no Python, Poetry, or tools required!**

#### Download Binary
```bash
# Linux
wget https://github.com/sodoityu/SeekrAI1/releases/download/v1.0/unified-search
chmod +x unified-search
./unified-search

# Mac
curl -LO https://github.com/sodoityu/SeekrAI1/releases/download/v1.0/unified-search-mac
chmod +x unified-search-mac
./unified-search-mac

# Windows
# Download: unified-search.exe
# Double-click to run
```

#### Using Docker
```bash
docker run -p 5500:5500 sodoityu/unified-search:latest
# Open: http://localhost:5500
```

### What Tools Do Users Need?

| Method | Requirements | Setup Time | Full Features |
|--------|-------------|------------|---------------|
| **Binary** | None | 0 min | Jira + SFDC + KCS ✅ |
| **Docker** | Docker only | 1 min | All ✅ |
| **Full Install** | Python, Poetry | 5 min | All ✅ |

**Recommendation:** Use binary for desktop, Docker for servers.

### What Environment Variables Are Needed?

**None!** Use the Settings UI:

1. Start the app (binary/Docker/Python)
2. Open http://localhost:5500
3. Click ⚙️ Settings
4. Enter credentials
5. Click 💾 Save & Remember
6. ✅ Done! Auto-loads next time

**Optional:** Set environment variables instead (see [.env.example](.env.example))

For complete installation options, see [INSTALLATION_GUIDE.md](INSTALLATION_GUIDE.md)

---

## Installation

### Step 1: Install Python 3.13+

**macOS:**
```bash
brew install python@3.13
```

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install python3.13 python3.13-venv
```

**Fedora/RHEL:**
```bash
sudo dnf install python3.13
```

**Windows:**
Download from [python.org](https://www.python.org/downloads/)

### Step 2: Install Poetry

```bash
curl -sSL https://install.python-poetry.org | python3 -
```

**Verify installation:**
```bash
poetry --version
# Output: Poetry (version 1.8.0)
```

### Step 3: Install Podman or Docker

**Podman (Recommended for Linux):**
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

**Docker:**
```bash
# Follow instructions at https://docs.docker.com/get-docker/
```

### Step 4: Clone Repository

```bash
git clone https://github.com/sodoityu/SeekrAI1.git
cd SeekrAI1/finaltool
```

### Step 5: Install Dependencies

```bash
# Install Python packages
poetry install

# Pull Slack MCP container
podman pull quay.io/redhat-ai-tools/slack-mcp
```

**Dependencies installed:**
- Flask 3.1.0 - Web framework
- Requests 2.32.3 - HTTP library
- MCP SDK 1.3.2 - Model Context Protocol for Slack

### Step 6: Configure Credentials

See [SETUP.md](SETUP.md) for detailed credential setup instructions.

**Quick checklist:**
- [ ] Jira API token
- [ ] Red Hat API offline token
- [ ] Slack xoxc and xoxd tokens
- [ ] Update `unified_search.py` with tokens
- [ ] Update `.mcp.json` with Slack tokens

---

## Usage

### Starting the Server

```bash
cd finaltool
poetry run python unified_search.py
```

**Output:**
```
======================================================================
 🔍 Unified Search - Jira + SFDC + Slack + KCS
======================================================================

✨ Search all four systems with one query!

Open your browser:
  👉 http://localhost:5500

Features:
  • Parallel search across Jira, SFDC, Slack, and KCS
  • Category filtering (show/hide each source)
  • Result counts in sidebar
  • Clean, unified interface

Press CTRL+C to stop
======================================================================
```

### Performing a Search

1. **Open browser** → http://localhost:5500
2. **Enter search query** in the search box
   - Example: `HCP allowedRegistries`
   - Example: `network connectivity upgrade`
3. **Press Enter** or click **Send** button
4. **Wait 50-60 seconds** for results
5. **View results** from all systems

### Filtering Results

**Sidebar Categories:**
- **All** - Show results from all systems
- **SFDC** - Show only Salesforce cases
- **Slack** - Show only Slack messages
- **Jira** - Show only Jira issues
- **KCS** - Show only knowledge articles

Click any category to filter results.

### Filtering Slack by Channel

1. Click **🔽 Show Filters (Slack Channels)**
2. **Uncheck "All Channels"**
3. **Select specific channels:**
   - forum-rosa-support
   - openshift-sre
   - team-sre
   - etc.
4. **Search again** - Results filtered to selected channels

### Opening Original Items

Click any result to open it in the original system:
- **Jira**: Opens in redhat.atlassian.net
- **SFDC**: Opens in access.redhat.com
- **Slack**: Opens "Find in Slack" search (channel IDs not available)
- **KCS**: Opens in access.redhat.com

---

## Configuration

### Environment Variables (Recommended)

Create `.env` file:
```bash
# Jira
JIRA_EMAIL=your.email@redhat.com
JIRA_API_TOKEN=your_jira_token_here

# SFDC/KCS
RH_API_OFFLINE_TOKEN=your_redhat_offline_token

# Slack
SLACK_XOXC_TOKEN=xoxc-your-token-here
SLACK_XOXD_TOKEN=xoxd-YOUR-SESSION-TOKEN-HERE-token-here
```

Load in `unified_search.py`:
```python
from dotenv import load_dotenv
load_dotenv()

JIRA_EMAIL = os.getenv("JIRA_EMAIL")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")
```

### Changing Port

Edit `unified_search.py`:
```python
# Change port 5500 to your preferred port
app.run(debug=True, host='0.0.0.0', port=5500)
```

### Adjusting Result Limits

Edit `templates_unified/unified_index.html`:
```javascript
body: JSON.stringify({
    query: query,
    max_results: 100,  // Change this (default: 100)
    slack_channels: selectedChannels
})
```

**Note:** Higher limits = slower searches, especially for Slack.

---

## Troubleshooting

### Common Issues

#### 1. "Module not found" Error
```bash
# Solution: Install dependencies
poetry install
```

#### 2. "Port already in use"
```bash
# Solution: Change port or kill existing process
lsof -i :5500
kill -9 <PID>
```

#### 3. Jira Returns 0 Results
**Causes:**
- Invalid API token
- Wrong email address
- Token expired

**Solution:**
- Regenerate API token at https://redhat.atlassian.net
- Verify email matches Jira account
- Update `JIRA_API_TOKEN` in code

#### 4. SFDC Authentication Failed
**Causes:**
- Offline token expired (valid 1 year)
- Network/VPN issues
- Wrong token format

**Solution:**
- Regenerate token at https://access.redhat.com/management/api
- Verify VPN connection
- Check token has no extra spaces

#### 5. Slack Returns 0 Results
**Causes:**
- MCP container not running
- Invalid Slack tokens
- Tokens expired (logout/login refreshes)

**Solution:**
```bash
# Check Podman is running
podman ps

# Pull latest MCP image
podman pull quay.io/redhat-ai-tools/slack-mcp

# Regenerate Slack tokens from browser DevTools
```

#### 6. Search is Slow (>2 minutes)
**Causes:**
- Slack search with high limit
- Network latency
- Large result sets

**Solution:**
- Reduce `max_results` limit
- Use channel filters for Slack
- Check network connection

### Debug Mode

Enable detailed logging:
```bash
export FLASK_DEBUG=1
poetry run python unified_search.py
```

View logs in terminal for detailed error messages.

### Getting Help

1. Check [SETUP.md](SETUP.md) for setup issues
2. Read [ARCHITECTURE.md](ARCHITECTURE.md) for technical details
3. Review this README for usage help
4. Open GitHub issue with:
   - Error message
   - Steps to reproduce
   - System info (OS, Python version)

---

## Documentation

### 📚 Main Guides

| Document | Description |
|----------|-------------|
| [README.md](README.md) | This file - Usage and installation |
| [INSTALLATION_GUIDE.md](INSTALLATION_GUIDE.md) | Complete setup for all deployment methods |
| [TOKEN_SETUP_GUIDE.md](TOKEN_SETUP_GUIDE.md) | **How to get tokens for Jira, Slack, SFDC, KCS** |
| [QUICK_START.md](QUICK_START.md) | Answers to: tools needed, env vars, binary options |
| [QUICK_INSTALL.md](QUICK_INSTALL.md) | Fastest installation methods (binary/Docker/source) |

### 🐳 Podman/Docker Guides

| Document | Description |
|----------|-------------|
| [PODMAN_GUIDE.md](PODMAN_GUIDE.md) | Complete Podman tutorial with examples |
| [PODMAN_TWO_APPROACHES.md](PODMAN_TWO_APPROACHES.md) | **Detailed comparison: 1 vs 2 containers** |
| [QUICK_PODMAN_SLACK.md](QUICK_PODMAN_SLACK.md) | Quick fix for Slack in Podman |
| [SLACK_SETUP_PODMAN.md](SLACK_SETUP_PODMAN.md) | Why Slack needs special setup in containers |

### 📖 Feature Documentation

| Document | Description |
|----------|-------------|
| [PERSISTENT_CREDENTIALS.md](PERSISTENT_CREDENTIALS.md) | Auto-save credentials feature |
| [SLACK_FIX_SUMMARY.md](SLACK_FIX_SUMMARY.md) | Direct Slack links implementation |
| [SELF_CONTAINED_STRUCTURE.md](SELF_CONTAINED_STRUCTURE.md) | Self-contained folder structure |
| [FILES_STRUCTURE.md](FILES_STRUCTURE.md) | File organization guide |
| [CREDENTIALS_CLEANED.md](CREDENTIALS_CLEANED.md) | How credentials were cleaned for GitHub |

---

## Building & Distribution

### Build Standalone Binary

```bash
./build_binary.sh
# Output: dist/unified-search (~50-100MB)
```

### Build Docker Image

```bash
./build_docker.sh
# Image: unified-search:latest
```

### Run Docker Container

```bash
# Basic run
docker run -p 5500:5500 unified-search:latest

# With credentials
docker run -p 5500:5500 \
  -e JIRA_EMAIL="..." \
  -e JIRA_API_TOKEN="..." \
  unified-search:latest

# With persistent storage
docker run -p 5500:5500 \
  -v $(pwd)/.saved_credentials.json:/app/.saved_credentials.json \
  unified-search:latest
```

### Distribution Methods

| Method | Best For | Size | Slack Support |
|--------|----------|------|---------------|
| **PyInstaller Binary** | Desktop users | ~50-100MB | ❌ Requires Podman |
| **Docker Image** | Servers, cloud | ~500MB | ⚠️ Complex |
| **Source + Poetry** | Developers | ~50MB | ✅ Full |

### Publish to GitHub Releases

```bash
# 1. Build binary
./build_binary.sh

# 2. Build Docker
./build_docker.sh
docker push sodoityu/unified-search:latest

# 3. Create GitHub release
# - Go to: https://github.com/sodoityu/SeekrAI1/releases
# - Upload: dist/unified-search
# - Tag: v1.0.0
```

---

## Project Structure

```
finaltool/
├── unified_search.py              # Flask backend (main server)
├── slack_search_standalone.py     # Slack MCP integration
├── templates_unified/
│   └── unified_index.html         # Frontend UI
├── README.md                      # This file
├── SETUP.md                       # Setup guide
├── ARCHITECTURE.md                # Architecture docs
├── QUICKSTART.md                  # Quick reference
└── KCS_FEATURE.md                 # KCS docs

Parent directory:
../
├── .mcp.json                      # MCP server config
├── pyproject.toml                 # Python dependencies
└── poetry.lock                    # Locked dependencies
```

---

## API Reference

### Search Endpoint

```http
POST /search
Content-Type: application/json

{
  "query": "search terms",
  "max_results": 100,
  "slack_channels": ["forum-rosa-support", "openshift-sre"] or null
}
```

**Response:**
```json
{
  "jira": {
    "issues": [{...}],
    "total": 9
  },
  "sfdc": {
    "cases": [{...}],
    "total": 20
  },
  "slack": {
    "messages": [{...}],
    "total": 42,
    "channels": ["forum-rosa-support", ...]
  },
  "kcs": {
    "articles": [{...}],
    "total": 1
  },
  "query": "search terms"
}
```

---

## Performance

### Search Times

| System | Typical Time | Notes |
|--------|--------------|-------|
| Jira | 1-3s | Fast REST API |
| SFDC | 2-5s | Includes token refresh |
| KCS | 1-3s | Shares SFDC token |
| Slack | 45-60s | Slowest (MCP overhead) |
| **Total** | **~50-60s** | **Parallel execution** |

### Optimization Tips

1. **Use specific keywords** - Narrow searches are faster
2. **Filter by channel** - Reduces Slack search time
3. **Lower result limits** - Faster for exploratory searches
4. **Bookmark queries** - Save frequent searches

---

## Contributing

We welcome contributions! Here's how:

### Development Setup

```bash
# Fork repository
git clone https://github.com/YOUR_USERNAME/SeekrAI1.git
cd SeekrAI1/finaltool

# Create branch
git checkout -b feature/your-feature

# Install dependencies
poetry install

# Make changes
# Test locally

# Commit and push
git add .
git commit -m "Add feature: description"
git push origin feature/your-feature

# Create pull request on GitHub
```

### Coding Standards

- Follow PEP 8 for Python code
- Use meaningful variable names
- Add comments for complex logic
- Update documentation for changes
- Test before submitting PR

### Adding New Search Sources

See [ARCHITECTURE.md](ARCHITECTURE.md) "Extension Points" section.

Example template:
```python
def search_newsource(query, max_results=100):
    """Search a new data source."""
    # 1. Make API call
    # 2. Parse response
    # 3. Return standardized format
    return {
        "items": [...],
        "total": N
    }
```

---

## Roadmap

### Current Version: 1.0.0

- [x] Parallel search across 4 systems
- [x] Category filtering
- [x] Slack channel filtering
- [x] Full text display
- [x] Direct links to sources

### Planned Features

- [ ] Result caching (Redis)
- [ ] Search history
- [ ] AI result summarization
- [ ] Export (CSV, JSON, PDF)
- [ ] Saved queries
- [ ] Email alerts
- [ ] GitHub/GitLab integration
- [ ] Advanced filters (date, status, priority)
- [ ] User authentication (SSO)
- [ ] Multi-user support

---

## License

MIT License - See [LICENSE](LICENSE) file for details.

---

## Support

### For Issues
- Open GitHub issue: https://github.com/sodoityu/SeekrAI1/issues
- Include error messages and steps to reproduce

### For Questions
- Check documentation first
- Search existing GitHub issues
- Open discussion on GitHub

### For Security Issues
- **Do NOT open public issue**
- Email: security@example.com
- Include detailed description

---

## Acknowledgments

- **Red Hat** - For internal systems and APIs
- **Flask** - Web framework
- **MCP SDK** - Slack integration
- **Poetry** - Dependency management
- **Contributors** - Community contributions

---

## Screenshots & Examples

### Search Results View

When you search for "HCP allowedRegistries", you get:

**Jira Results (9):**
- OHSS-1234: Allow custom registries in HCP
- OHSS-5678: Registry configuration issues
- ...

**SFDC Cases (20):**
- 03796358: Network connectivity issue
- 04414763: HCP upgrade stuck
- ...

**Slack Messages (42):**
- @creed in #openshift-sre: "I've been investigating..."
- @jayu in #forum-rosa-support: "FYI for this one..."
- ...

**KCS Articles (1):**
- 7139427: ROSA HCP setting pending when clearing registry...

### Typical Use Cases

#### 1. Bug Investigation
```
Query: "network connectivity OVN"
Results: Bugs + cases + discussions + official solutions
Time: ~50s
Value: Complete picture of the issue
```

#### 2. Customer Support
```
Query: "cluster upgrade failed 4.15"
Results: Similar cases + known issues + workarounds
Time: ~50s
Value: Faster resolution with precedents
```

#### 3. Knowledge Discovery
```
Query: "HCP allowedRegistries"
Results: Implementation details + customer examples + documentation
Time: ~50s
Value: Comprehensive understanding
```

---

**Happy Searching! 🔍✨**

One search to find them all across Jira, SFDC, Slack, and KCS!

---

*Last updated: 2026-04-05*  
*Version: 1.0.0*  
*Maintainer: SeekrAI Team*
