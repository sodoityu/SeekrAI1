# 📦 Installation Guide - Unified Search Tool

## Table of Contents
1. [Required Tools](#required-tools)
2. [Environment Variables](#environment-variables)
3. [Installation Methods](#installation-methods)
4. [Binary Distribution](#binary-distribution)

---

## 1. Required Tools

### Minimum Requirements (For Basic Usage)
- **Python 3.10+** (tested with Python 3.13)
- **Poetry** (Python dependency manager)
- **Git** (to clone the repository)

### Full Requirements (For All Features Including Slack)
- **Python 3.10+**
- **Poetry**
- **Podman** or **Docker** (for Slack MCP server)
- **Git**

### Check if You Have Them:
```bash
python3 --version    # Should be 3.10+
poetry --version     # Any recent version
podman --version     # Or: docker --version
git --version
```

---

## 2. Environment Variables

### Option A: Use Environment Variables (Temporary)

```bash
# Jira Credentials
export JIRA_EMAIL="your-email@redhat.com"
export JIRA_API_TOKEN="your-jira-token"
export JIRA_BASE_URL="https://issues.redhat.com"

# SFDC (Salesforce) Credentials
export RH_API_OFFLINE_TOKEN="your-offline-token"

# Slack Credentials
export SLACK_XOXC_TOKEN="xoxc-..."
export SLACK_XOXD_TOKEN="xoxd-..."
export SLACK_WORKSPACE_URL="https://redhat.enterprise.slack.com"
export LOGS_CHANNEL_ID="C0AKQ7SD0RZ"

# Start the app
poetry run python finaltoolMay17/unified_search.py
```

### Option B: Use UI (Recommended - Persistent)

1. Start the app **without** setting environment variables:
   ```bash
   poetry run python finaltoolMay17/unified_search.py
   ```

2. Open http://localhost:5500

3. Click **⚙️ Settings**

4. Enter your credentials

5. Click **💾 Save & Remember**

6. ✅ **Credentials saved!** They'll auto-load next time!

**Credentials File Location:**
```
finaltoolMay17/.saved_credentials.json
```
- Permissions: `600` (only you can read)
- Not committed to git (in `.gitignore`)
- Auto-loads on startup

---

## 3. Installation Methods

### Method 1: Full Installation (All Features)

```bash
# 1. Clone repository
git clone https://github.com/sodoityu/SeekrAI1.git
cd SeekrAI1

# 2. Install Python dependencies
poetry install

# 3. Install Podman (for Slack - RHEL/Fedora)
sudo dnf install podman

# 4. Pull Slack MCP server image
podman pull quay.io/redhat-ai-tools/slack-mcp

# 5. Start the app
poetry run python finaltoolMay17/unified_search.py

# 6. Open browser
open http://localhost:5500
```

### Method 2: Minimal Installation (Without Slack)

If you don't need Slack search:

```bash
# 1. Clone repository
git clone https://github.com/sodoityu/SeekrAI1.git
cd SeekrAI1

# 2. Install Python dependencies
poetry install

# 3. Start the app
poetry run python finaltoolMay17/unified_search.py

# You'll have: Jira + SFDC + KCS search
# Slack will show "not configured"
```

### Method 3: Using run.sh Script

```bash
# Smart startup script (auto-detects poetry)
./run.sh
```

This script:
- ✅ Checks if Poetry is installed
- ✅ Uses `poetry run` if available
- ✅ Falls back to direct `python3` if not
- ✅ Handles virtual environment automatically

---

## 4. Binary Distribution

### Can Users Run Without Installing Anything?

**Yes! Three options:**

#### Option 1: PyInstaller Binary (Recommended for Desktop)

Create a standalone executable:

```bash
# Install PyInstaller
poetry add --group dev pyinstaller

# Build binary
poetry run pyinstaller --onefile \
  --add-data "finaltoolMay17/templates_unified:templates_unified" \
  --name unified-search \
  finaltoolMay17/unified_search.py

# Result:
dist/unified-search  # Single executable!
```

**Usage:**
```bash
# User just runs:
./unified-search

# No Python, Poetry, or dependencies needed!
```

**Limitations:**
- ❌ Slack search won't work (needs Podman/Docker for MCP server)
- ✅ Jira, SFDC, KCS work fine
- Size: ~50-100MB

#### Option 2: Docker Container (Best for Cross-Platform)

Package everything in Docker:

```dockerfile
FROM python:3.13-slim

WORKDIR /app

# Install dependencies
COPY pyproject.toml poetry.lock ./
RUN pip install poetry && poetry install --no-dev

# Copy app
COPY finaltoolMay17/ ./finaltoolMay17/
COPY slack_search_standalone.py ./

# Expose port
EXPOSE 5500

# Run
CMD ["poetry", "run", "python", "finaltoolMay17/unified_search.py"]
```

**Build & Run:**
```bash
# Build
docker build -t unified-search:latest .

# Run
docker run -p 5500:5500 \
  -e JIRA_EMAIL="your-email@redhat.com" \
  -e JIRA_API_TOKEN="your-token" \
  unified-search:latest

# Open: http://localhost:5500
```

**Users need:** Only Docker (no Python, Poetry, etc.)

#### Option 3: Flatpak (For Linux Desktop Users)

Create a Flatpak package:

```bash
# Install flatpak-builder
sudo dnf install flatpak-builder

# Build Flatpak
flatpak-builder --force-clean build-dir com.github.sodoityu.UnifiedSearch.yml

# Install locally
flatpak-builder --user --install --force-clean build-dir com.github.sodoityu.UnifiedSearch.yml

# Run
flatpak run com.github.sodoityu.UnifiedSearch
```

**Users need:** Only Flatpak (comes with Fedora/RHEL)

---

## Comparison: Installation Methods

| Method | Setup Time | Dependencies | Slack Support | Best For |
|--------|-----------|--------------|---------------|----------|
| **Full Install** | 5 min | Python, Poetry, Podman | ✅ Yes | Developers |
| **Minimal Install** | 2 min | Python, Poetry | ❌ No | Quick Testing |
| **PyInstaller Binary** | 0 min (user) | None | ❌ No | End Users (Desktop) |
| **Docker** | 1 min | Docker only | ⚠️ Complex | Servers/Cloud |
| **Flatpak** | 0 min (user) | Flatpak only | ❌ No | Linux Desktop Users |

---

## Quick Start for End Users

### If They Have Python + Poetry:
```bash
git clone https://github.com/sodoityu/SeekrAI1.git
cd SeekrAI1
poetry install
poetry run python finaltoolMay17/unified_search.py
# Open: http://localhost:5500
```

### If They Want a Binary:
```bash
# Download binary (once you build it)
wget https://github.com/sodoityu/SeekrAI1/releases/download/v1.0/unified-search

# Make executable
chmod +x unified-search

# Run
./unified-search
# Open: http://localhost:5500
```

### If They Have Docker:
```bash
docker run -p 5500:5500 sodoityu/unified-search:latest
# Open: http://localhost:5500
```

---

## How to Get Credentials

### Jira API Token
1. Go to: https://issues.redhat.com
2. Click your profile → **Account Settings**
3. Click **Security** → **Create and manage API tokens**
4. Click **Create API token**
5. Copy the token

### SFDC (Red Hat API) Offline Token
1. Go to: https://access.redhat.com/management/api
2. Click **Generate Token**
3. Copy the offline token

### Slack Tokens (xoxc and xoxd)
1. Open Slack in browser
2. Press **F12** (Developer Tools)
3. Go to **Application** tab → **Cookies**
4. Find:
   - `d` cookie → This is your **xoxd** token
   - Look in **Local Storage** for `xoxc-...` → This is your **xoxc** token

**Note:** These tokens are session-based. You may need to refresh them periodically.

---

## Troubleshooting

### "Poetry not found"
```bash
# Install Poetry
curl -sSL https://install.python-poetry.org | python3 -

# Add to PATH
export PATH="$HOME/.local/bin:$PATH"
```

### "Python version too old"
```bash
# Install Python 3.13 (Fedora/RHEL)
sudo dnf install python3.13

# Use with Poetry
poetry env use python3.13
```

### "Podman not found" (for Slack)
```bash
# Install Podman
sudo dnf install podman

# Test
podman --version
```

### "Port 5500 already in use"
```bash
# Kill existing process
lsof -ti:5500 | xargs kill -9

# Or use different port
PORT=5501 poetry run python finaltoolMay17/unified_search.py
```

---

## Next Steps

1. **For Developers:**
   - Full install with all features
   - Set up environment variables
   - Customize search logic

2. **For End Users:**
   - Download binary (once available)
   - Or use Docker image
   - Enter credentials via UI

3. **For Distribution:**
   - Build PyInstaller binary
   - Create Docker image
   - Publish to GitHub Releases

---

## Support

- GitHub Issues: https://github.com/sodoityu/SeekrAI1/issues
- Documentation: This file
- Source Code: https://github.com/sodoityu/SeekrAI1
