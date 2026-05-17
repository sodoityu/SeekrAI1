# ⚙️ UI Settings vs Environment Variables

**Confused about when to use UI Settings vs environment variables?** This guide explains the difference!

---

## 🎯 Quick Answer

| Method | Need UI Settings? | When Tokens Load |
|--------|------------------|------------------|
| **Environment Variables** | ❌ NO | On container start |
| **UI Settings** | ✅ YES | When you click Save |
| **Config Files** (.mcp.json) | ❌ NO | On container start |

---

## 📋 Three Ways to Configure Tokens

### Method 1: Environment Variables (Recommended for Podman)

**How it works:**
```bash
podman run -d --network=host --name unified-search \
  -e SLACK_XOXC_TOKEN='xoxc-YOUR-TOKEN' \
  -e SLACK_XOXD_TOKEN='xoxd-YOUR-TOKEN' \
  -e JIRA_API_TOKEN='ATATT-YOUR-TOKEN' \
  unified-search:latest
```

**What happens:**
- Tokens passed to container at startup
- App reads them from environment
- **UI Settings NOT needed!** ✅
- Works immediately when container starts

**When to use:**
- Running in Podman/Docker
- Quick testing
- Automation/scripts

---

### Method 2: UI Settings

**How it works:**
1. Start container WITHOUT environment variables:
   ```bash
   podman run -d -p 5500:5500 --name unified-search \
     unified-search:latest
   ```

2. Open http://localhost:5500
3. Click ⚙️ Settings (top right)
4. Enter all tokens
5. Click 💾 Save & Remember

**What happens:**
- Tokens saved to `.saved_credentials.json` file
- File has 600 permissions (read/write owner only)
- Auto-loads next time you open the app
- **Good for interactive use!** ✅

**When to use:**
- Running locally (not in container)
- Don't want tokens in command line
- Interactive development

---

### Method 3: Config Files (.mcp.json)

**How it works:**
1. Edit `.mcp.json` file:
   ```json
   {
     "mcpServers": {
       "slack": {
         "env": {
           "SLACK_XOXC_TOKEN": "xoxc-YOUR-TOKEN",
           "SLACK_XOXD_TOKEN": "xoxd-YOUR-TOKEN"
         }
       }
     }
   }
   ```

2. Mount file to container:
   ```bash
   podman run -d --network=host --name unified-search \
     -v $(pwd)/.mcp.json:/app/.mcp.json:Z \
     unified-search:latest
   ```

**What happens:**
- App reads tokens from config file
- **UI Settings NOT needed!** ✅
- More complex to set up

**When to use:**
- Need MCP server approach
- Want version-controlled config
- Production deployments

---

## ⚠️ Common Confusion: "I set tokens in UI but Slack doesn't work!"

### The Problem

You did this:
1. ✅ Started container
2. ✅ Opened http://localhost:5500
3. ✅ Clicked Settings
4. ✅ Entered xoxc and xoxd tokens
5. ✅ Clicked Save
6. ❌ **Slack still returns 0 results!**

### Why?

**UI Settings saves tokens to a file INSIDE the container.**

But when you started the container, you probably used:
```bash
podman run -p 5500:5500 unified-search:latest
```

**Missing:**
- `--network=host` (needed for Slack MCP)
- OR environment variables for Slack Web API

**The tokens are saved, but the app can't use them properly without network access!**

---

## ✅ The Solution

### Option A: Use Environment Variables (Easier)

```bash
# Stop old container
podman stop unified-search
podman rm unified-search

# Restart with environment variables
podman run -d --network=host --name unified-search \
  -e SLACK_XOXC_TOKEN='xoxc-YOUR-ACTUAL-TOKEN' \
  -e SLACK_XOXD_TOKEN='xoxd-YOUR-ACTUAL-TOKEN' \
  -e JIRA_URL='https://issues.redhat.com' \
  -e JIRA_USERNAME='your-email@redhat.com' \
  -e JIRA_API_TOKEN='ATATT-YOUR-TOKEN' \
  -e SFDC_SESSION_ID='00D...' \
  -e SFDC_INSTANCE_URL='https://redhat.my.salesforce.com' \
  unified-search:latest
```

**Now:**
- ✅ No need for UI Settings
- ✅ Slack works via Web API
- ✅ All systems work

---

### Option B: Add Host Network to Existing Container

```bash
# Stop old container
podman stop unified-search
podman rm unified-search

# Restart with host network + mount saved credentials
podman run -d --network=host --name unified-search \
  -v $(pwd)/.saved_credentials.json:/app/.saved_credentials.json:Z \
  unified-search:latest
```

**This preserves your UI Settings tokens and adds network access!**

---

## 🔍 How to Check Which Method Is Active

### Check Environment Variables

```bash
podman exec unified-search env | grep -E "SLACK|JIRA|SFDC"
```

**If you see:**
```
SLACK_XOXC_TOKEN=xoxc-...
SLACK_XOXD_TOKEN=xoxd-...
```

**Then:** Environment variables are being used! ✅

**If you see nothing:**
Then the app is looking for `.saved_credentials.json` or `.mcp.json`

---

### Check Saved Credentials File

```bash
podman exec unified-search cat /app/.saved_credentials.json
```

**If you see:**
```json
{
  "slack_xoxc": "xoxc-...",
  "slack_xoxd": "xoxd-..."
}
```

**Then:** UI Settings tokens are saved! ✅

**If you see:**
```
cat: /app/.saved_credentials.json: No such file or directory
```

**Then:** No UI Settings configured yet.

---

## 📊 Priority Order

If you have **multiple** sources, the app uses this priority:

1. **Environment Variables** (highest priority)
2. **UI Settings** (`.saved_credentials.json`)
3. **Config Files** (`.mcp.json`)

**Example:**
- If you have `SLACK_XOXC_TOKEN` in environment AND in `.saved_credentials.json`
- The app will use the **environment variable**!

---

## 🎯 Which Method Should You Use?

### For Podman/Docker: Use Environment Variables

**Why:**
- ✅ Simpler (one command)
- ✅ No files to mount
- ✅ Works with `--network=host` for Slack
- ✅ Easy to update (just restart container with new values)

**Example:**
```bash
podman run -d --network=host --name unified-search \
  -e SLACK_XOXC_TOKEN='xoxc-...' \
  -e SLACK_XOXD_TOKEN='xoxd-...' \
  -e JIRA_API_TOKEN='ATATT...' \
  unified-search:latest
```

---

### For Local Development: Use UI Settings

**Why:**
- ✅ Easy to change tokens (just click Settings)
- ✅ Tokens saved between runs
- ✅ No command-line exposure

**Example:**
```bash
# Just run normally
./run.sh

# Then configure via UI
open http://localhost:5500
# Click Settings → Enter tokens → Save
```

---

## 🆘 Troubleshooting

### "I configured UI Settings but tokens not working"

**Check 1: Is the credentials file created?**
```bash
ls -la .saved_credentials.json

# If running in container:
podman exec unified-search ls -la /app/.saved_credentials.json
```

**Check 2: Are tokens correct in the file?**
```bash
cat .saved_credentials.json

# In container:
podman exec unified-search cat /app/.saved_credentials.json
```

**Check 3: Are environment variables overriding?**
```bash
podman exec unified-search env | grep SLACK
```

If you see `SLACK_XOXC_TOKEN=...`, environment variables are taking priority!

---

### "Environment variables not working"

**Check 1: Did you pass them correctly?**
```bash
# Verify they're set in the container
podman exec unified-search env | grep -E "SLACK|JIRA"
```

Should show your tokens!

**Check 2: Did you use quotes?**
```bash
# WRONG (no quotes)
-e SLACK_XOXC_TOKEN=xoxc-123

# RIGHT (with quotes)
-e SLACK_XOXC_TOKEN='xoxc-123'
```

---

### "Slack still doesn't work even with tokens"

**The issue is NOT the tokens - it's the network!**

You need:
```bash
--network=host
```

**Full command:**
```bash
podman run -d --network=host --name unified-search \
  -e SLACK_XOXC_TOKEN='xoxc-...' \
  -e SLACK_XOXD_TOKEN='xoxd-...' \
  unified-search:latest
```

Without `--network=host`, Slack MCP server is unreachable!

---

## 📝 Summary

### Environment Variables (for Podman)
```bash
podman run -d --network=host -e SLACK_XOXC_TOKEN='xoxc-...' unified-search:latest
```
- ✅ Tokens passed at startup
- ❌ No UI Settings needed
- ✅ Best for containers

### UI Settings (for local development)
```bash
./run.sh
# Then: http://localhost:5500 → Settings → Enter tokens → Save
```
- ✅ Tokens saved to file
- ✅ Easy to update
- ✅ Best for development

### Both Together?
- Environment variables take **priority**
- UI Settings are **ignored** if env vars exist
- Choose **one method**, not both!

---

**Still confused?** Check **PODMAN_TWO_APPROACHES.md** for complete examples!
