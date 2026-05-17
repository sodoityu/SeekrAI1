# ⚡ ONE-STEP Podman Setup

**The simplest way to run - just ONE command!**

---

## 🚀 Quick Start

### Step 1: Build the Image (First Time Only)

```bash
cd /path/to/SeekrAI1
podman build -t unified-search:latest .
```

**This takes ~3 minutes and installs:**
- Flask (web framework)
- Requests (HTTP library)
- MCP SDK (for Slack search)

### Step 2: Use the Script

```bash
./RUN_WITH_MY_TOKENS.sh
```

**Done!** Open http://localhost:5500 and start searching! ✅

---

### Method 2: Copy-Paste Command

```bash
podman run -d \
  --network=host \
  --name unified-search \
  -e SLACK_XOXC_TOKEN='YOUR-XOXC-TOKEN' \
  -e SLACK_XOXD_TOKEN='YOUR-XOXD-TOKEN' \
  -e SLACK_WORKSPACE_URL='https://redhat.enterprise.slack.com' \
  -e JIRA_URL='https://redhat.atlassian.net' \
  -e JIRA_EMAIL='your-email@redhat.com' \
  -e JIRA_USERNAME='your-email@redhat.com' \
  -e JIRA_API_TOKEN='YOUR-JIRA-TOKEN' \
  -e RH_API_OFFLINE_TOKEN='YOUR-OFFLINE-TOKEN' \
  unified-search:latest
```

**Replace YOUR-*-TOKEN with your actual tokens!**

---

## 🎯 What This Does

1. ✅ Stops any old `unified-search` container
2. ✅ Starts new container with all credentials
3. ✅ Uses `--network=host` for Slack support
4. ✅ All 4 systems work immediately:
   - Jira ✅
   - Slack ✅
   - SFDC ✅
   - KCS ✅

---

## 📊 Check It's Working

```bash
# View running containers
podman ps

# Should show:
# CONTAINER ID  IMAGE                    STATUS
# abc123        unified-search:latest    Up 10 seconds

# View logs
podman logs unified-search

# Should show:
# 🔍 Unified Search - Jira + SFDC + Slack + KCS
# * Running on http://localhost:5500
```

---

## 🌐 Access the App

Open in browser:
```
http://localhost:5500
```

Search for anything, like: `test`

You should see results from **all 4 systems**! ✅

---

## 🔧 Managing the Container

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
```

---

## 🔄 Update Tokens

If your tokens expire:

1. Edit `RUN_WITH_MY_TOKENS.sh` with new tokens
2. Run: `./RUN_WITH_MY_TOKENS.sh`
3. Done!

Or just run the full `podman run` command again with new values.

---

## ⚠️ Important Notes

1. **Script Location:** `RUN_WITH_MY_TOKENS.sh` is in `.gitignore`
   - Won't be pushed to GitHub
   - Your tokens stay private ✅

2. **Network Mode:** `--network=host` is required for Slack
   - Without it, Slack returns 0 results
   - All other systems work either way

3. **Environment Variables:** Takes priority over everything
   - UI Settings not needed
   - Config files not needed
   - Just works! ✅

---

## 🆘 Troubleshooting

### "Container exits immediately"

```bash
# Check logs for errors
podman logs unified-search

# Common issues:
# - Port 5500 already in use
# - Image not built yet
```

### "Port 5500 already in use"

```bash
# Find what's using it
lsof -ti:5500 | xargs kill -9

# Or use different port
podman run -p 5501:5500 ... unified-search:latest
# Access at: http://localhost:5501
```

### "Image not found"

```bash
# Build the image first
cd /path/to/SeekrAI1
podman build -t unified-search:latest .

# Then run again
./RUN_WITH_MY_TOKENS.sh
```

### "No results from Slack"

Make sure you have:
- ✅ `--network=host` in the command
- ✅ Correct xoxc and xoxd tokens
- ✅ Tokens are not expired

---

## 📚 Need More Info?

- **UI_SETTINGS_VS_ENV_VARS.md** - Environment variables vs UI Settings
- **PODMAN_TWO_APPROACHES.md** - Detailed comparison of approaches
- **TOKEN_SETUP_GUIDE.md** - How to get all tokens

---

## ✅ Summary

**Just run:**
```bash
./RUN_WITH_MY_TOKENS.sh
```

**Then open:**
```
http://localhost:5500
```

**That's it! One step, everything works!** 🎉
