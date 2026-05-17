# 🐳 Two Approaches to Run in Podman

Complete comparison and detailed steps for both approaches.

---

## 📊 Comparison Table

| Approach | Containers Needed | Complexity | Slack Support | Setup Time |
|----------|------------------|------------|---------------|------------|
| **Environment Variables** (recommended) | **1 container** | ⭐ Simple | ✅ Via Web API | 2 minutes |
| **Config Files** (.mcp.json) | **2 containers** | ⭐⭐⭐ Complex | ✅ Via MCP Server | 5 minutes |

---

## ⭐ Approach 1: Environment Variables (RECOMMENDED)

**ONE container - All tokens passed as environment variables**

### 📋 What You Need

- Slack tokens (xoxc, xoxd)
- Jira credentials (URL, username, API token)
- SFDC credentials (session ID, instance URL)
- KCS cookies (optional)

### 🚀 Step-by-Step

#### Step 1: Get Your Tokens

Follow **TOKEN_SETUP_GUIDE.md** to get all tokens.

**Quick reference:**
- **Slack:** Browser DevTools → Cookies → `d` (xoxd), Network tab → `xoxc`
- **Jira:** https://id.atlassian.com/manage-profile/security/api-tokens
- **SFDC:** Browser → Cookies → `sid`

#### Step 2: Build the Image (First Time Only)

```bash
# Clone repo
git clone https://github.com/sodoityu/SeekrAI1.git
cd SeekrAI1

# Build image
podman build -t unified-search:latest .
```

**Output should end with:**
```
Successfully tagged localhost/unified-search:latest
```

#### Step 3: Run with Environment Variables

```bash
podman run -d \
  --network=host \
  --name unified-search \
  -e SLACK_XOXC_TOKEN='xoxc-YOUR-WORKSPACE-ID-YOUR-TOKEN...' \
  -e SLACK_XOXD_TOKEN='xoxd-YOUR-SESSION-TOKEN-HERE...' \
  -e JIRA_URL='https://issues.redhat.com' \
  -e JIRA_USERNAME='your-email@redhat.com' \
  -e JIRA_API_TOKEN='ATATT3xFfGF0cH1lxjl38VNvP-...' \
  -e SFDC_SESSION_ID='00D8a0000008gYK!...' \
  -e SFDC_INSTANCE_URL='https://redhat.my.salesforce.com' \
  unified-search:latest
```

**Replace with YOUR actual tokens!**

#### Step 4: Verify It's Running

```bash
# Check container status
podman ps

# Should show:
# CONTAINER ID  IMAGE                         COMMAND               STATUS
# abc123def456  localhost/unified-search:...  python3 unified_s...  Up 10 seconds
```

#### Step 5: Check Logs

```bash
podman logs unified-search
```

**Should show:**
```
======================================================================
 🔍 Unified Search - Jira + SFDC + Slack + KCS
======================================================================

 * Running on http://127.0.0.1:5500
```

#### Step 6: Access in Browser

```bash
# Open in browser
open http://localhost:5500

# Or on Linux
xdg-open http://localhost:5500

# Or manually type in browser:
http://localhost:5500
```

#### Step 7: Test Search

1. Enter search query: `test`
2. Click "Search All"
3. **You should see results from all 4 systems:**
   - ✅ Jira
   - ✅ Slack
   - ✅ SFDC
   - ✅ KCS

**Done! ✅**

---

### 🔧 Managing the Container

```bash
# Stop container
podman stop unified-search

# Start container again
podman start unified-search

# View logs in real-time
podman logs -f unified-search

# Restart container
podman restart unified-search

# Remove container
podman stop unified-search
podman rm unified-search
```

### 🔄 Update Tokens

If tokens expire or change:

```bash
# Stop and remove old container
podman stop unified-search
podman rm unified-search

# Run again with NEW tokens
podman run -d \
  --network=host \
  --name unified-search \
  -e SLACK_XOXC_TOKEN='NEW-xoxc-token' \
  -e SLACK_XOXD_TOKEN='NEW-xoxd-YOUR-SESSION-TOKEN-HERE' \
  -e JIRA_API_TOKEN='NEW-jira-token' \
  -e SFDC_SESSION_ID='NEW-sfdc-session' \
  unified-search:latest
```

---

## ⭐⭐⭐ Approach 2: Config Files (COMPLEX)

**TWO containers - Tokens in config files, uses MCP Server**

### 📋 What You Need

- Everything from Approach 1
- Text editor (nano, vi, or VS Code)
- Understanding of JSON format

### 🚀 Step-by-Step

#### Step 1: Clone and Build (Same as Approach 1)

```bash
# Clone repo
git clone https://github.com/sodoityu/SeekrAI1.git
cd SeekrAI1

# Build image
podman build -t unified-search:latest .
```

#### Step 2: Create .mcp.json Config File

```bash
# Edit .mcp.json
nano .mcp.json
```

**Update with YOUR tokens:**

```json
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
        "MCP_TRANSPORT",
        "quay.io/redhat-ai-tools/slack-mcp"
      ],
      "env": {
        "SLACK_XOXC_TOKEN": "xoxc-YOUR-WORKSPACE-ID-YOUR-TOKEN...",
        "SLACK_XOXD_TOKEN": "xoxd-YOUR-SESSION-TOKEN-HERE...",
        "SLACK_WORKSPACE_URL": "https://redhat-internal.slack.com",
        "MCP_TRANSPORT": "stdio"
      }
    },
    "mcp-atlassian": {
      "command": "uvx",
      "args": ["mcp-atlassian"],
      "env": {
        "JIRA_URL": "https://issues.redhat.com",
        "JIRA_USERNAME": "your-email@redhat.com",
        "JIRA_API_TOKEN": "ATATT3xFfGF0cH1lxjl38VNvP-..."
      }
    }
  }
}
```

**Save and exit:**
- nano: `Ctrl+O`, `Enter`, `Ctrl+X`
- vi: `Esc`, `:wq`, `Enter`

#### Step 3: Create .saved_credentials.json

```bash
# Create credentials file
cat > .saved_credentials.json <<'EOF'
{
  "slack_xoxc": "xoxc-YOUR-WORKSPACE-ID-YOUR-TOKEN...",
  "slack_xoxd": "xoxd-YOUR-SESSION-TOKEN-HERE...",
  "jira_url": "https://issues.redhat.com",
  "jira_username": "your-email@redhat.com",
  "jira_api_token": "ATATT3xFfGF0cH1lxjl38VNvP-...",
  "sfdc_session_id": "00D8a0000008gYK!...",
  "sfdc_instance_url": "https://redhat.my.salesforce.com"
}
EOF

# Set permissions (important for security!)
chmod 600 .saved_credentials.json
```

#### Step 4: Start Slack MCP Server (FIRST CONTAINER)

```bash
podman run -d \
  --name slack-mcp \
  -e SLACK_XOXC_TOKEN='xoxc-YOUR-WORKSPACE-ID-YOUR-TOKEN...' \
  -e SLACK_XOXD_TOKEN='xoxd-YOUR-SESSION-TOKEN-HERE...' \
  -e MCP_TRANSPORT=stdio \
  quay.io/redhat-ai-tools/slack-mcp
```

**Verify it's running:**
```bash
podman ps | grep slack-mcp

# Should show:
# abc123  quay.io/redhat-ai-tools/slack-mcp  Up 5 seconds
```

#### Step 5: Start Unified Search (SECOND CONTAINER)

```bash
podman run -d \
  --network=host \
  --name unified-search \
  -v $(pwd)/.saved_credentials.json:/app/.saved_credentials.json:Z \
  -v $(pwd)/.mcp.json:/app/.mcp.json:Z \
  unified-search:latest
```

**What this does:**
- `--network=host` - Share host network (can access slack-mcp container)
- `-v .saved_credentials.json:...` - Mount credentials file
- `-v .mcp.json:...` - Mount MCP config
- `:Z` - SELinux label (Fedora/RHEL/CentOS)

#### Step 6: Verify Both Containers Running

```bash
podman ps
```

**Should show TWO containers:**
```
CONTAINER ID  IMAGE                         COMMAND               STATUS
abc123        slack-mcp                     ...                   Up 1 minute
def456        unified-search:latest         python3 unified_s...  Up 30 seconds
```

#### Step 7: Check Logs

```bash
# Check Slack MCP logs
podman logs slack-mcp

# Check unified-search logs
podman logs unified-search
```

#### Step 8: Access in Browser

```
http://localhost:5500
```

#### Step 9: Test Search

Search for `test` - should get results from all 4 systems.

---

### 🔧 Managing TWO Containers

```bash
# View both containers
podman ps

# Stop both
podman stop slack-mcp unified-search

# Start both
podman start slack-mcp unified-search

# View logs
podman logs slack-mcp
podman logs unified-search

# Restart both
podman restart slack-mcp unified-search

# Remove both
podman stop slack-mcp unified-search
podman rm slack-mcp unified-search
```

### 🔄 Update Config Files

```bash
# Stop containers
podman stop slack-mcp unified-search
podman rm slack-mcp unified-search

# Edit config files
nano .mcp.json
nano .saved_credentials.json

# Restart both containers (repeat Steps 4 & 5)
```

---

## 📊 Detailed Comparison

### Approach 1: Environment Variables

**Pros:**
- ✅ Only ONE container to manage
- ✅ Simpler commands
- ✅ No config files to edit
- ✅ Easier to update tokens (just restart with new values)
- ✅ Works immediately
- ✅ Better for beginners

**Cons:**
- ⚠️ Tokens visible in `podman ps` output
- ⚠️ Need to copy-paste long command

**Best for:**
- Quick testing
- Simple deployments
- Users who don't want to manage config files

---

### Approach 2: Config Files

**Pros:**
- ✅ Tokens stored in files (not visible in ps output)
- ✅ Can be version controlled (with .gitignore)
- ✅ Easier to manage many credentials
- ✅ Uses full MCP protocol stack

**Cons:**
- ❌ Need to manage TWO containers
- ❌ More complex setup
- ❌ Need to edit JSON files correctly
- ❌ Harder to troubleshoot
- ❌ More things that can go wrong

**Best for:**
- Production deployments
- Security-conscious environments
- Users comfortable with config files

---

## 🎯 Which Should You Choose?

### Choose **Approach 1** (Environment Variables) if:
- ✅ You want the simplest setup
- ✅ You're new to Podman/Docker
- ✅ You're testing the tool
- ✅ You don't mind tokens in environment

### Choose **Approach 2** (Config Files) if:
- ✅ You need better security (tokens in files)
- ✅ You're deploying to production
- ✅ You want to use version control
- ✅ You're comfortable managing multiple containers

---

## 🆘 Troubleshooting

### Approach 1 Issues

**"No Slack results"**
```bash
# Check if tokens are correct
podman exec unified-search env | grep SLACK

# Should show your tokens
# SLACK_XOXC_TOKEN=xoxc-...
# SLACK_XOXD_TOKEN=xoxd-YOUR-SESSION-TOKEN-HERE...
```

**"Container exits immediately"**
```bash
# Check logs
podman logs unified-search

# Look for errors like:
# - "ModuleNotFoundError: No module named 'flask'"
# - Connection refused
```

### Approach 2 Issues

**"Slack MCP not found"**
```bash
# Check if slack-mcp container is running
podman ps | grep slack-mcp

# If not running, start it:
podman start slack-mcp
```

**"Permission denied on .mcp.json"**
```bash
# Fix SELinux labels
chcon -Rt svirt_sandbox_file_t .mcp.json .saved_credentials.json

# Or use :Z in volume mount (already included)
```

**"Can't read config file"**
```bash
# Check file exists
ls -la .mcp.json .saved_credentials.json

# Check permissions
chmod 600 .saved_credentials.json
```

---

## 📝 Quick Command Reference

### Approach 1: One Command
```bash
podman run -d --network=host --name unified-search \
  -e SLACK_XOXC_TOKEN='xoxc-...' \
  -e SLACK_XOXD_TOKEN='xoxd-YOUR-SESSION-TOKEN-HERE...' \
  -e JIRA_URL='https://issues.redhat.com' \
  -e JIRA_USERNAME='user@redhat.com' \
  -e JIRA_API_TOKEN='ATATT...' \
  -e SFDC_SESSION_ID='00D...' \
  -e SFDC_INSTANCE_URL='https://redhat.my.salesforce.com' \
  unified-search:latest
```

### Approach 2: Two Commands
```bash
# Start MCP server
podman run -d --name slack-mcp \
  -e SLACK_XOXC_TOKEN='xoxc-...' \
  -e SLACK_XOXD_TOKEN='xoxd-YOUR-SESSION-TOKEN-HERE...' \
  quay.io/redhat-ai-tools/slack-mcp

# Start unified search
podman run -d --network=host --name unified-search \
  -v $(pwd)/.saved_credentials.json:/app/.saved_credentials.json:Z \
  -v $(pwd)/.mcp.json:/app/.mcp.json:Z \
  unified-search:latest
```

---

## 🎉 Summary

**For most users, we recommend Approach 1** (Environment Variables):
- Simpler
- Faster to set up
- Easier to troubleshoot
- Only ONE container to manage

**Use Approach 2** (Config Files) only if you have specific requirements for file-based configuration.

---

**Need help choosing?** Start with Approach 1. You can always switch to Approach 2 later if needed!
