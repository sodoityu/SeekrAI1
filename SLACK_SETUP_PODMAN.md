# 🔧 Slack Setup for Podman/Docker

Why Slack search returns no results in containers and how to fix it.

---

## 🤔 The Problem

Slack search needs **both**:
1. ✅ Tokens in UI Settings (xoxc, xoxd) 
2. ✅ Slack MCP server running on HOST machine
3. ✅ Container can access host's Podman socket

**Why?** Slack search uses two methods:
- **Web API** (direct with tokens) - tries first
- **MCP Server** (via Podman) - fallback if Web API fails

When running the app in a container, it can't access the host's Podman socket to talk to the MCP server.

---

## ✅ Solution 1: Run with Host Network (Recommended)

This gives the container access to everything on your host:

```bash
# Stop existing container
podman stop unified-search
podman rm unified-search

# Run with host network
podman run -d \
  --network=host \
  --name unified-search \
  -v $(pwd)/.saved_credentials.json:/app/.saved_credentials.json:Z \
  -v $(pwd)/.mcp.json:/app/.mcp.json:Z \
  unified-search:latest
```

**What this does:**
- `--network=host` - Container uses host's network (can access MCP server)
- `-v .saved_credentials.json:...` - Mounts your saved tokens
- `-v .mcp.json:...` - Mounts MCP config
- `:Z` - SELinux label (needed on Fedora/RHEL)

**Then:**
1. Start Slack MCP server on host:
   ```bash
   podman run -d \
     --name slack-mcp \
     -e SLACK_XOXC_TOKEN='your-xoxc-token' \
     -e SLACK_XOXD_TOKEN='your-xoxd-token' \
     quay.io/redhat-ai-tools/slack-mcp
   ```

2. Open http://localhost:5500
3. Configure tokens in Settings
4. Search - Slack should work! ✅

---

## ✅ Solution 2: Mount Podman Socket

Give the container access to host's Podman:

```bash
podman run -d \
  -p 5500:5500 \
  --name unified-search \
  -v /run/podman/podman.sock:/run/podman/podman.sock:Z \
  -v $(pwd)/.saved_credentials.json:/app/.saved_credentials.json:Z \
  -v $(pwd)/.mcp.json:/app/.mcp.json:Z \
  unified-search:latest
```

**What this does:**
- Mounts Podman socket so container can start MCP server
- Container can run `podman run` commands to start Slack MCP

---

## ✅ Solution 3: Use Environment Variables (Easiest)

Pass all tokens as environment variables:

```bash
podman run -d \
  --network=host \
  --name unified-search \
  -e SLACK_XOXC_TOKEN='xoxc-3016034988151-...' \
  -e SLACK_XOXD_TOKEN='xoxd-5GTKCd9yBXeiOE...' \
  -e JIRA_URL='https://your-jira.atlassian.net' \
  -e JIRA_USERNAME='your-email@company.com' \
  -e JIRA_API_TOKEN='ATATT3xFfGF0...' \
  -e SFDC_SESSION_ID='00D8...' \
  -e SFDC_INSTANCE_URL='https://redhat.my.salesforce.com' \
  unified-search:latest
```

**Benefits:**
- No need to configure via UI
- Credentials loaded automatically
- Works immediately

---

## 📋 Step-by-Step: Complete Setup

### Step 1: Prepare Configuration Files

On your **host machine** (not in container):

```bash
cd /path/to/SeekrAI1

# Create .saved_credentials.json
cat > .saved_credentials.json <<EOF
{
  "slack_xoxc": "xoxc-3016034988151-...",
  "slack_xoxd": "xoxd-5GTKCd9yBXeiOE...",
  "jira_url": "https://your-jira.atlassian.net",
  "jira_username": "your-email@company.com",
  "jira_api_token": "ATATT3xFfGF0...",
  "sfdc_session_id": "00D8...",
  "sfdc_instance_url": "https://redhat.my.salesforce.com"
}
EOF

chmod 600 .saved_credentials.json

# Update .mcp.json with your tokens
cat > .mcp.json <<EOF
{
  "mcpServers": {
    "slack": {
      "command": "podman",
      "args": [
        "run",
        "-i",
        "--rm",
        "-e",
        "SLACK_XOXC_TOKEN",
        "-e",
        "SLACK_XOXD_TOKEN",
        "-e",
        "LOGS_CHANNEL_ID",
        "-e",
        "MCP_TRANSPORT",
        "quay.io/redhat-ai-tools/slack-mcp"
      ],
      "env": {
        "SLACK_XOXC_TOKEN": "xoxc-3016034988151-...",
        "SLACK_XOXD_TOKEN": "xoxd-5GTKCd9yBXeiOE...",
        "SLACK_WORKSPACE_URL": "https://redhat-internal.slack.com",
        "MCP_TRANSPORT": "stdio"
      }
    },
    "mcp-atlassian": {
      "command": "uvx",
      "args": ["mcp-atlassian"],
      "env": {
        "JIRA_URL": "https://your-jira.atlassian.net",
        "JIRA_USERNAME": "your-email@company.com",
        "JIRA_API_TOKEN": "ATATT3xFfGF0..."
      }
    }
  }
}
EOF
```

### Step 2: Start Slack MCP Server on Host

```bash
# Start Slack MCP server (on host, not in container)
podman run -d \
  --name slack-mcp \
  -e SLACK_XOXC_TOKEN='xoxc-3016034988151-...' \
  -e SLACK_XOXD_TOKEN='xoxd-5GTKCd9yBXeiOE...' \
  -e MCP_TRANSPORT=stdio \
  quay.io/redhat-ai-tools/slack-mcp

# Verify it's running
podman ps | grep slack-mcp
```

### Step 3: Run Unified Search with Host Network

```bash
# Build image
podman build -t unified-search:latest .

# Run with host network and volume mounts
podman run -d \
  --network=host \
  --name unified-search \
  -v $(pwd)/.saved_credentials.json:/app/.saved_credentials.json:Z \
  -v $(pwd)/.mcp.json:/app/.mcp.json:Z \
  unified-search:latest

# Check logs
podman logs -f unified-search
```

### Step 4: Test Slack Search

```bash
# Open browser
open http://localhost:5500

# Search for something
# Enter query: "hello"
# Check results - Slack should have results now! ✅
```

---

## 🔍 Troubleshooting

### "Still no Slack results"

**Check 1: Are tokens correct?**
```bash
# Test Slack Web API directly
curl -H "Authorization: Bearer xoxc-YOUR-TOKEN" \
  --cookie "d=xoxd-YOUR-TOKEN" \
  "https://slack.com/api/search.messages?query=test&count=5"
```

**Check 2: Is MCP server running?**
```bash
podman ps | grep slack-mcp
# Should show slack-mcp container running
```

**Check 3: Can container access host?**
```bash
# Run with host network?
podman inspect unified-search | grep NetworkMode
# Should show: "NetworkMode": "host"
```

**Check 4: View container logs**
```bash
podman logs unified-search | grep -i slack
# Look for errors
```

### "Web API works but MCP doesn't"

The Web API is usually enough! MCP is only a fallback.

To test which one is being used:
```bash
# Check subprocess logs
podman exec unified-search cat /tmp/slack_search.log
```

### "Permission denied on .mcp.json"

```bash
# Fix SELinux labels (Fedora/RHEL)
chcon -Rt svirt_sandbox_file_t .mcp.json .saved_credentials.json

# Or use :Z flag in volume mount (already included above)
```

---

## 📊 Architecture When Running in Podman

```
┌─────────────────────────────────────────┐
│        Your Computer (Host)             │
│                                         │
│  ┌───────────────────────────────────┐ │
│  │  Unified Search Container         │ │
│  │  (port 5500)                      │ │
│  │                                   │ │
│  │  - Flask App                      │ │
│  │  - Searches Jira/SFDC/KCS ✅      │ │
│  │  - Calls slack_search_standalone  │ │
│  │    (tries Web API first)          │ │
│  └───────────┬───────────────────────┘ │
│              │                          │
│              │ (needs access to host)   │
│              ▼                          │
│  ┌───────────────────────────────────┐ │
│  │  Slack MCP Container (on host)    │ │
│  │  - quay.io/redhat-ai-tools/slack  │ │
│  │  - Runs MCP protocol              │ │
│  └───────────────────────────────────┘ │
│                                         │
│  Files mounted from host:               │
│  - .saved_credentials.json              │
│  - .mcp.json                            │
└─────────────────────────────────────────┘
```

**Key Point:** Container needs `--network=host` to access the Slack MCP server running on host!

---

## ✅ Quick Reference

### Full Working Command

```bash
# 1. Start Slack MCP on host
podman run -d --name slack-mcp \
  -e SLACK_XOXC_TOKEN='xoxc-...' \
  -e SLACK_XOXD_TOKEN='xoxd-...' \
  quay.io/redhat-ai-tools/slack-mcp

# 2. Run unified search with host network
podman run -d --network=host --name unified-search \
  -v $(pwd)/.saved_credentials.json:/app/.saved_credentials.json:Z \
  -v $(pwd)/.mcp.json:/app/.mcp.json:Z \
  unified-search:latest

# 3. Access
open http://localhost:5500
```

### Environment Variable Method (No Config Files)

```bash
podman run -d --network=host --name unified-search \
  -e SLACK_XOXC_TOKEN='xoxc-...' \
  -e SLACK_XOXD_TOKEN='xoxd-...' \
  -e JIRA_URL='https://jira.atlassian.net' \
  -e JIRA_USERNAME='user@company.com' \
  -e JIRA_API_TOKEN='ATATT...' \
  -e SFDC_SESSION_ID='00D...' \
  -e SFDC_INSTANCE_URL='https://company.salesforce.com' \
  unified-search:latest
```

---

## 🎯 Summary

**To get Slack working in Podman:**

1. ✅ **UI Settings** - Configure xoxc/xoxd tokens
2. ✅ **MCP Config** - Update `.mcp.json` with tokens  
3. ✅ **MCP Server** - Start Slack MCP on host
4. ✅ **Host Network** - Run container with `--network=host`
5. ✅ **Volume Mounts** - Mount `.saved_credentials.json` and `.mcp.json`

**Or use environment variables** to skip config files entirely!

---

**Need help?** Check:
- TOKEN_SETUP_GUIDE.md - How to get Slack tokens
- PODMAN_GUIDE.md - General Podman usage
