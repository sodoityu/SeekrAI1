# 🔑 Token Setup Guide

Complete guide to obtain and configure tokens for Jira, Slack, SFDC, and KCS.

---

## 📋 Quick Overview

| System | Token Type | Where to Get | Required For |
|--------|-----------|--------------|--------------|
| **Slack** | xoxc + xoxd tokens | Browser cookies | Direct message links |
| **Jira** | API Token | Atlassian Account Settings | Issue search |
| **SFDC** | Session ID | Salesforce cookies | Case search |
| **KCS** | Session cookies | Red Hat Customer Portal | Article search |

---

## 1️⃣ Slack Tokens (xoxc + xoxd)

### What You Need
- `SLACK_XOXC_TOKEN` - Authentication token
- `SLACK_XOXD_TOKEN` - Session token

### How to Get Them

**Method 1: Browser Developer Tools (Chrome/Firefox)**

1. **Open Slack in Browser**
   - Go to https://redhat-internal.slack.com (or your workspace)
   - Make sure you're logged in

2. **Open Developer Tools**
   - Press `F12` or `Ctrl+Shift+I` (Windows/Linux)
   - Press `Cmd+Option+I` (Mac)

3. **Go to Application/Storage Tab**
   - Chrome: Click "Application" tab
   - Firefox: Click "Storage" tab

4. **Find Cookies**
   - Expand "Cookies" in left sidebar
   - Click on your Slack workspace URL

5. **Copy Token Values**
   - Find cookie named `d` → Copy the **Value** → This is your `SLACK_XOXD_TOKEN`
   - Find cookie named `d-s` → Copy the **Value** → This is your session value (usually not needed)
   
6. **Get xoxc Token**
   - Go to "Network" tab in Developer Tools
   - Refresh the page or send a message
   - Click on any API request (looks like `api.slack.com/api/...`)
   - Look in "Request Headers" section
   - Find `Authorization: Bearer xoxc-...` → Copy the `xoxc-...` part → This is your `SLACK_XOXC_TOKEN`

**Method 2: Quick Cookie Inspector**
```javascript
// Run this in browser console while on Slack
document.cookie.split(';').forEach(c => console.log(c.trim()))
// Look for: d=xoxd-YOUR-SESSION-TOKEN-HERE... and copy the value
```

### Configuration

**Option A: Settings UI (Recommended)**
1. Start the app: `./run.sh`
2. Open http://localhost:5500
3. Click ⚙️ Settings
4. Paste tokens:
   - Slack xoxc Token: `xoxc-YOUR-WORKSPACE-ID-YOUR-TOKEN...`
   - Slack xoxd Token: `xoxd-YOUR-SESSION-TOKEN-HERE...`
5. Click 💾 Save & Remember

**Option B: Environment Variables**
```bash
export SLACK_XOXC_TOKEN="xoxc-YOUR-WORKSPACE-ID-YOUR-TOKEN..."
export SLACK_XOXD_TOKEN="xoxd-YOUR-SESSION-TOKEN-HERE..."
```

**Option C: Edit .mcp.json**
```json
{
  "mcpServers": {
    "slack": {
      "env": {
        "SLACK_XOXC_TOKEN": "xoxc-YOUR-WORKSPACE-ID-YOUR-TOKEN...",
        "SLACK_XOXD_TOKEN": "xoxd-YOUR-SESSION-TOKEN-HERE..."
      }
    }
  }
}
```

---

## 2️⃣ Jira API Token

### What You Need
- `JIRA_URL` - Your Jira instance URL
- `JIRA_USERNAME` - Your email address
- `JIRA_API_TOKEN` - API authentication token

### How to Get Them

1. **Go to Atlassian Account Settings**
   - Visit: https://id.atlassian.com/manage-profile/security/api-tokens
   - Or: Jira → Click your profile icon → "Account settings" → "Security" → "API tokens"

2. **Create API Token**
   - Click "Create API token"
   - Label: `unified-search-tool` (or any name)
   - Click "Create"
   - **Copy the token immediately** (you won't see it again!)

3. **Get Your Jira URL**
   - If Cloud: `https://your-company.atlassian.net`
   - If Server: `https://jira.your-company.com`

### Configuration

**Option A: Settings UI (Recommended)**
1. Open http://localhost:5500
2. Click ⚙️ Settings
3. Fill in:
   - Jira URL: `https://your-company.atlassian.net`
   - Jira Username: `your-email@company.com`
   - Jira API Token: `ATATT3xFfGF0cH1lxjl38VNvP-...`
4. Click 💾 Save & Remember

**Option B: Environment Variables**
```bash
export JIRA_URL="https://your-company.atlassian.net"
export JIRA_USERNAME="your-email@company.com"
export JIRA_API_TOKEN="ATATT3xFfGF0cH1lxjl38VNvP-..."
```

**Option C: Edit .mcp.json**
```json
{
  "mcpServers": {
    "mcp-atlassian": {
      "env": {
        "JIRA_URL": "https://your-company.atlassian.net",
        "JIRA_USERNAME": "your-email@company.com",
        "JIRA_API_TOKEN": "ATATT3xFfGF0cH1lxjl38VNvP-..."
      }
    }
  }
}
```

---

## 3️⃣ Salesforce (SFDC) Token

### What You Need
- `SFDC_SESSION_ID` - Salesforce session ID
- `SFDC_INSTANCE_URL` - Your Salesforce instance URL

### How to Get Them

**Method 1: Browser Developer Tools**

1. **Login to Salesforce**
   - Go to your Salesforce instance (e.g., https://redhat.my.salesforce.com)
   - Login with your credentials

2. **Open Developer Tools**
   - Press `F12` or right-click → "Inspect"

3. **Get Session ID from Cookies**
   - Go to "Application" (Chrome) or "Storage" (Firefox) tab
   - Click "Cookies" → Your Salesforce URL
   - Find cookie named `sid` → Copy the **Value** → This is your `SFDC_SESSION_ID`

4. **Get Instance URL**
   - The instance URL is in your browser address bar
   - Example: `https://redhat.my.salesforce.com`
   - Copy everything up to `.com`

**Method 2: Salesforce Developer Console**
```javascript
// Run in browser console
console.log('Session ID:', document.cookie.match(/sid=([^;]+)/)?.[1]);
console.log('Instance:', window.location.origin);
```

### Configuration

**Settings UI:**
1. Open http://localhost:5500
2. Click ⚙️ Settings
3. Fill in:
   - SFDC Session ID: `00D8...AAEA`
   - SFDC Instance URL: `https://redhat.my.salesforce.com`
4. Click 💾 Save & Remember

**Environment Variables:**
```bash
export SFDC_SESSION_ID="00D8...AAEA"
export SFDC_INSTANCE_URL="https://redhat.my.salesforce.com"
```

**⚠️ Note:** SFDC session IDs expire (usually after 2 hours of inactivity). You'll need to refresh them periodically.

---

## 4️⃣ KCS (Red Hat Customer Portal)

### What You Need
- `KCS_COOKIES` - Authentication cookies from Red Hat Customer Portal

### How to Get Them

1. **Login to Red Hat Customer Portal**
   - Go to https://access.redhat.com
   - Login with your Red Hat account

2. **Open Developer Tools**
   - Press `F12`
   - Go to "Application" (Chrome) or "Storage" (Firefox) tab

3. **Copy All Cookies**
   - Click "Cookies" → `https://access.redhat.com`
   - Copy all cookie values in this format:
   ```
   cookie1=value1; cookie2=value2; cookie3=value3
   ```

4. **Common Required Cookies:**
   - `rh_sso`
   - `_redhat_customer_portal_session`
   - `_csrf_token`

### Configuration

**Settings UI:**
1. Open http://localhost:5500
2. Click ⚙️ Settings
3. Paste all cookies in "KCS Cookies" field
4. Click 💾 Save & Remember

**Environment Variables:**
```bash
export KCS_COOKIES="rh_sso=value1; _redhat_customer_portal_session=value2"
```

---

## 🏗️ Architecture Overview

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
│  - redhat-internal.slack.com           │
│  - redhat.my.salesforce.com            │
│  - access.redhat.com (KCS)             │
└─────────────────────────────────────────┘
```

### Component Details

**1. Flask Application (`unified_search.py`)**
- Web server on port 5500
- Routes:
  - `GET /` - Main search interface
  - `POST /search` - Execute parallel search
  - `GET /settings` - Settings UI
  - `POST /save-credentials` - Save credentials
  - `GET /load-credentials` - Load saved credentials

**2. Slack Integration (`slack_search_standalone.py`)**
- **Dual approach:**
  - Slack Web API (`search.messages`) - Gets channel_id for direct links
  - Slack MCP Server - Fallback if Web API fails
- **Direct link construction:**
  - Format: `https://workspace.slack.com/archives/{channel_id}/p{timestamp}`
  - Timestamp conversion: `1734620891.519839` → `1734620891519839` (remove dot, pad with zeros)

**3. Jira Integration**
- Uses MCP Atlassian server (`mcp-atlassian`)
- JQL search for issues
- Returns: issue key, summary, status, assignee, priority

**4. SFDC Integration**
- Direct API calls to Salesforce REST API
- Endpoint: `/services/data/v57.0/search/`
- SOSL queries for cases

**5. KCS Integration**
- Web scraping Red Hat Customer Portal
- Search endpoint: `/search/browse/search/`
- Returns solution articles

**6. Credential Storage**
- File: `.saved_credentials.json`
- Permissions: `600` (owner read/write only)
- Format: JSON with encrypted values (base64 encoded)
- Auto-loads on app startup

---

## 🔒 Security Best Practices

### 1. Keep Tokens Secure
```bash
# Set proper permissions
chmod 600 .saved_credentials.json
chmod 600 .env

# Never commit tokens to git
echo ".saved_credentials.json" >> .gitignore
echo ".env" >> .gitignore
```

### 2. Rotate Tokens Regularly
- **Slack tokens:** Extract fresh tokens monthly
- **Jira API tokens:** Regenerate every 90 days
- **SFDC sessions:** Expire automatically, refresh as needed
- **KCS cookies:** Refresh when they expire

### 3. Token Expiration
| Token Type | Typical Lifespan | What Happens When Expired |
|------------|------------------|---------------------------|
| Slack xoxc | 6-12 months | Search fails, need new tokens |
| Slack xoxd | Tied to session | Search fails, need new tokens |
| Jira API | Never (until revoked) | Still works |
| SFDC Session | 2 hours inactive | 401 error, need new session |
| KCS Cookies | Session-based | Search fails, need new cookies |

### 4. Monitoring
Watch for these error messages:
- `invalid_auth` - Slack token expired
- `401 Unauthorized` - Jira/SFDC token invalid
- `403 Forbidden` - Insufficient permissions
- `SESSION_EXPIRED` - SFDC session timed out

---

## 🐛 Troubleshooting

### Slack: "No results found"
**Cause:** Invalid xoxc/xoxd tokens
**Fix:**
1. Get fresh tokens from browser
2. Update in Settings UI
3. Test with a simple query like "hello"

### Jira: "Authentication failed"
**Cause:** Wrong API token or username
**Fix:**
1. Verify username is your email address
2. Regenerate API token at https://id.atlassian.com/manage-profile/security/api-tokens
3. Update in Settings UI

### SFDC: "Session expired"
**Cause:** Session ID timeout (2 hours)
**Fix:**
1. Login to Salesforce again
2. Get fresh session ID from cookies
3. Update in Settings UI

### KCS: "Failed to fetch"
**Cause:** Cookies expired
**Fix:**
1. Login to https://access.redhat.com again
2. Copy fresh cookies
3. Update in Settings UI

---

## 📚 Additional Resources

- **Slack API Documentation:** https://api.slack.com/methods
- **Jira API Documentation:** https://developer.atlassian.com/cloud/jira/platform/rest/v3/
- **Salesforce REST API:** https://developer.salesforce.com/docs/atlas.en-us.api_rest.meta/api_rest/
- **MCP Protocol:** https://github.com/modelcontextprotocol

---

## ✅ Quick Setup Checklist

- [ ] Install required tools (Poetry, Podman/Docker, uvx)
- [ ] Get Slack tokens (xoxc + xoxd)
- [ ] Create Jira API token
- [ ] Get SFDC session ID
- [ ] Copy KCS cookies
- [ ] Start app: `./run.sh`
- [ ] Open Settings UI: http://localhost:5500
- [ ] Paste all tokens
- [ ] Click Save & Remember
- [ ] Test search with query: "test"
- [ ] Verify all 4 systems return results

**All tokens configured? Ready to search!** 🚀
