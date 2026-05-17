# ⚡ Quick Fix: Slack in Podman

**Problem:** Slack returns no results, but Jira/SFDC/KCS work fine

**Answer:** Yes, you need **BOTH**:
1. ✅ Tokens in UI Settings
2. ✅ MCP config file + host network mode

---

## 🚀 Quick Solution (Copy-Paste This)

On your **other PC**, run these commands:

```bash
cd /path/to/SeekrAI1

# Step 1: Update .mcp.json with YOUR tokens
nano .mcp.json
# Replace "your-xoxc-token-here" with your actual xoxc token
# Replace "your-xoxd-token-here" with your actual xoxd token
# Save and exit (Ctrl+O, Ctrl+X)

# Step 2: Start Slack MCP server on host
podman run -d \
  --name slack-mcp \
  -e SLACK_XOXC_TOKEN='xoxc-YOUR-ACTUAL-TOKEN' \
  -e SLACK_XOXD_TOKEN='xoxd-YOUR-ACTUAL-TOKEN' \
  -e MCP_TRANSPORT=stdio \
  quay.io/redhat-ai-tools/slack-mcp

# Step 3: Stop and remove old unified-search container
podman stop unified-search
podman rm unified-search

# Step 4: Run unified-search with host network
podman run -d \
  --network=host \
  --name unified-search \
  -v $(pwd)/.saved_credentials.json:/app/.saved_credentials.json:Z \
  -v $(pwd)/.mcp.json:/app/.mcp.json:Z \
  unified-search:latest

# Step 5: Check logs
podman logs -f unified-search
```

**Then:**
- Open http://localhost:5500
- Search for something
- Slack should work now! ✅

---

## 🔍 What Changed?

### Before (Didn't Work):
```bash
podman run -p 5500:5500 unified-search
```
- ❌ Container isolated from host
- ❌ Can't access Slack MCP server
- ❌ Slack returns 0 results

### After (Works):
```bash
podman run --network=host \
  -v .mcp.json:/app/.mcp.json:Z \
  unified-search
```
- ✅ Container uses host network
- ✅ Can access Slack MCP server
- ✅ Slack returns results!

---

## 📝 Why Both Are Needed?

**UI Settings (xoxc/xoxd tokens):**
- Used by Slack Web API method
- First attempt for search

**MCP Config (.mcp.json):**
- Used by Slack MCP server method
- Fallback if Web API fails
- Provides channel info for direct links

**Host Network Mode:**
- Allows container to talk to MCP server on host
- Required for MCP method to work

---

## ⚠️ Alternative: Use Environment Variables (Even Simpler!)

Don't want to edit config files? Use env vars:

```bash
# Stop old container
podman stop unified-search
podman rm unified-search

# Run with all tokens as environment variables
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
- No need to mount config files
- Credentials in one place
- Works immediately

---

## 🧪 Verify It Works

```bash
# Check both containers are running
podman ps

# Should see:
# - slack-mcp (Slack MCP server)
# - unified-search (Main app)

# Check logs
podman logs unified-search | grep -i slack

# Open app
open http://localhost:5500

# Search for "test"
# Slack results should appear! ✅
```

---

## 📚 Need More Help?

- **SLACK_SETUP_PODMAN.md** - Complete Slack setup guide
- **TOKEN_SETUP_GUIDE.md** - How to get Slack tokens
- **PODMAN_GUIDE.md** - General Podman usage

---

**TL;DR:**
```bash
# On other PC:
podman run -d --name slack-mcp \
  -e SLACK_XOXC_TOKEN='xoxc-...' \
  -e SLACK_XOXD_TOKEN='xoxd-...' \
  quay.io/redhat-ai-tools/slack-mcp

podman run -d --network=host --name unified-search \
  -v $(pwd)/.mcp.json:/app/.mcp.json:Z \
  unified-search:latest
```

**Done! Slack works! 🎉**
