# Seekr Installation Guide

Seekr is a unified search tool for Red Hat SREs that searches across **Jira**, **Salesforce (SFDC)**, **KCS**, **Slack**, **GitHub**, **GitLab**, and **SOP documents** from a single interface.

---

## Architecture

Seekr runs 3 services managed by tmux:

| Service | Port | Description |
|---------|------|-------------|
| **Search API** (`unified_search.py`) | 5500 | Backend API — connects to Jira, SFDC, KCS, Slack, GitHub, GitLab |
| **Web UI** (`seekrWebUI_server.py`) | 5501 | Frontend server — serves the UI, handles Kerberos login, proxies to Search API |
| **ask-sre** | 8000 | AI-powered semantic SOP document search for GitHub/GitLab results |

**Seekr URL:** `http://localhost:5501/seekr/login`

---

## Prerequisites

| Tool | What it is | Why Seekr needs it | Verify |
|------|-----------|-------------------|--------|
| Python 3.12+ | Programming language runtime | Runs both Flask servers | `python3 --version` |
| pip | Python package installer | Installs Flask, requests, and other dependencies | `pip3 --version` |
| tmux | Terminal multiplexer | Runs Seekr's 3 services as background sessions | `tmux -V` |
| Git | Version control | Clone the Seekr repository | `git --version` |

---

## Step 1: Install System Packages

### Fedora

```bash
sudo dnf install python3 python3-pip tmux git
```

<details>
<summary>What each package does</summary>

- **python3, python3-pip** — Python runtime and package installer
- **tmux** — Terminal multiplexer that keeps Seekr's services running in the background. You can attach to any service's session to view logs
- **git** — Clone the Seekr repository

</details>

### macOS

First install [Homebrew](https://brew.sh) if you don't have it:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Then install the packages:

```bash
brew install python@3.13 tmux git
```

---

## Step 2: Clone the Repository

```bash
git clone <repository-url>
cd SeekrAI1
```

---

## Step 3: Install Python Dependencies

```bash
pip3 install -r requirements.txt
```

This installs:

| Package | Version | Purpose |
|---------|---------|---------|
| `flask` | >= 2.3.0 | Web framework powering both servers |
| `flask-cors` | >= 4.0.0 | Enables cross-origin requests between the UI and Search API |
| `requests` | >= 2.31.0 | HTTP client for calling Jira, SFDC, KCS, Slack, GitHub, and GitLab APIs |
| `mcp` | >= 1.0.0 | Model Context Protocol SDK for ask-sre integration |

---

## Step 4: Configure Server Environment

```bash
cp .env.example .env
```

The `.env` file configures the **server settings** only. API tokens for Jira, Slack, etc. are configured separately in the Settings page after login (see Step 6).

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | Auto-generated | Flask session encryption key. If left blank, `start_seekrai.sh` generates one automatically |
| `KERBEROS_REALM` | `IPA.REDHAT.COM` | Red Hat Kerberos realm |
| `LDAP_SERVER` | `ldap://ipa.redhat.com` | Red Hat LDAP server |
| `LDAP_BASE_DN` | `dc=redhat,dc=com` | LDAP base distinguished name |
| `LDAP_USER_BASE` | `cn=users,cn=accounts` | LDAP user search base |

Most users can use the defaults as-is — no changes needed.

**To generate a persistent SECRET_KEY** (optional):

If you want user sessions to persist across service restarts, generate a key and save it in `.env`:

```bash
python3 -c 'import secrets; print(secrets.token_hex(32))'
```

Copy the output and paste it as the `SECRET_KEY` value in `.env`. Without a persistent key, a new one is auto-generated each time services start, meaning users will need to log in again after every restart.

---

## Step 5: ask-sre Setup

ask-sre provides AI-powered semantic search across SOP documents and is required for GitHub and GitLab search results.

For full setup instructions, see [SETUP_ASK_SRE.md](SETUP_ASK_SRE.md).

---

## Step 6: Start Seekr

```bash
./start_seekrai.sh
```

This starts 3 services in tmux background sessions:

| tmux Session | Service | Port |
|-------------|---------|------|
| `seekrai-search` | Search API | 5500 |
| `seekrai-ui` | Web UI + Authentication | 5501 |
| `seekrai-asksre` | ask-sre SOP search | 8000 |

### Viewing Service Logs

To view logs for any service, attach to its tmux session:

```bash
tmux attach -t seekrai-search    # Search API logs
tmux attach -t seekrai-ui        # Web UI logs
tmux attach -t seekrai-asksre    # ask-sre logs
```

### Check Running Services

```bash
tmux ls
```

---

## Step 7: Access Seekr and Configure API Tokens

### Login

1. Open your browser and go to: **http://localhost:5501/seekr/login**
2. Enter your **Kerberos username** (e.g., `jdoe`)
3. Enter your **Kerberos password** in the password field
4. Click **Sign In**

### Configure API Tokens

After your first login, click the **Settings** icon in the left side panel to configure your API tokens. The Settings page has instructions for generating each token (Jira, Salesforce/KCS, Slack, GitHub, GitLab). Each user configures their own tokens — they are stored per-user and persist across sessions.

---

## Refining Search Results

### Sources Filter

The **Sources** filter on the left side panel controls which data sources are displayed in the search results. All sources are checked by default.

| Source | What it searches |
|--------|-----------------|
| **SFDC** | Salesforce support cases |
| **OHSS (Jira)** | OHSS/Jira tickets |
| **Slack** | Slack workspace messages |
| **KCS** | Red Hat Knowledgebase articles |
| **GitHub** | GitHub repository files and SOP documents |
| **GitLab** | GitLab repository files and SOP documents |
| **SOP, Repo** | GitHub, GitLab, and SOP documents |

**Auto-select:** If your search query contains a source name, Seekr automatically selects only that source and filters the results to show only matches from it. The search still runs across all backends, but only the detected source's results are displayed.

### Products Filter

The **Products** filter narrows results to a specific Red Hat product. If your search query contains a product name, Seekr auto-selects the matching product filter.

| Product | Keywords that trigger auto-select |
|---------|----------------------------------|
| **ROSA** | `rosa` |
| **ROSA HCP** | `rosa hcp` |
| **ARO** | `aro` |
| **OSD** | `osd` |

When a product filter is active, only results tagged with that product are shown. Uncheck the filter or click **Select All** to see results across all products.

---

## Troubleshooting

### Port already in use

```
Address already in use
```

**Fix:** Find what's using the port and stop it:

```bash
sudo lsof -i :5500   # Check port 5500
sudo lsof -i :5501   # Check port 5501
```

### "Invalid username or password" at login

**Fix:**
- Make sure you're using your Kerberos password
- Verify your Kerberos credentials work: `kinit your-username@IPA.REDHAT.COM`

---

*Internal Red Hat tool — not for public distribution.*
