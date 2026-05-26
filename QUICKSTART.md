# 🚀 Unified Search - Quick Start Guide

## ⚡ Super Simple (One Command)

From the project directory:

```bash
cd finaltoolMay18
./start.sh
```

Then open: **http://localhost:5500** 🌐

---

## 🛑 Stop Everything

```bash
cd finaltoolMay18
./stop.sh
```

Or manually:

```bash
pkill -f "uvicorn"          # Stop MCP server
pkill -f "unified_search"   # Stop unified search
```

---

## 📋 Manual Start (Two Terminals)

If you prefer to run services in separate terminals:

### Terminal 1 - Start MCP Server
```bash
cd kush/mcp-server/mcp-server
./start_server.sh
```
**Runs on:** http://localhost:8000

### Terminal 2 - Start Unified Search
```bash
cd finaltoolMay18
python unified_search.py
```
**Runs on:** http://localhost:5500

---

## 🔍 Check Status

```bash
# Quick check
netstat -tuln | grep -E "8000|5500"

# If you see:
# :8000  → MCP Server is running ✅
# :5500  → Unified Search is running ✅
```

Or check with curl:

```bash
curl http://localhost:8000/health  # MCP Server health check
curl http://localhost:5500         # Unified Search UI
```

---

## 🧪 Test Everything Works

```bash
cd finaltoolMay18
python test_sop_integration.py
```

**Expected output:** All tests pass ✅

---

## 💡 What Can I Search?

| Source | What | Count |
|--------|------|-------|
| 🔧 Jira | Issues & Tickets | Unlimited |
| 🎫 SFDC | Support Cases | Unlimited |
| 💬 Slack | Messages | Unlimited |
| 📚 KCS | Knowledge Articles | Unlimited |
| 📖 SOP | OpenShift SOPs | **839 docs** |

**All in one search!**

---

## 🎯 Example Searches

Try these in the web UI at http://localhost:5500:

```
etcd cluster down
pod crashloopbackoff
node not ready
cluster autoscaler
HighEtcdFsyncDurations
certificate rotation
ingress controller issues
storage provisioning failed
```

---

## 🔧 Troubleshooting

### Port already in use?
```bash
# Check what's using the ports
lsof -i :8000  # MCP Server
lsof -i :5500  # Unified Search

# Kill existing processes
pkill -f uvicorn
pkill -f unified_search

# Or kill by port
lsof -ti:8000 | xargs kill
lsof -ti:5500 | xargs kill
```

### Can't find Python/Flask?
```bash
# Install dependencies
pip install flask requests --user

# Or use Poetry (recommended)
cd finaltoolMay18
poetry install
poetry run python unified_search.py
```

### MCP Server won't start?
```bash
cd kush/mcp-server/mcp-server
source .venv/bin/activate
pip install -r requirements.txt
./start_server.sh
```

### Services start but can't connect?
```bash
# Check firewall (Fedora/RHEL)
sudo firewall-cmd --list-ports

# Add ports if needed
sudo firewall-cmd --add-port=8000/tcp --permanent
sudo firewall-cmd --add-port=5500/tcp --permanent
sudo firewall-cmd --reload
```

---

## 📁 Project Structure

```
ask-sre/
├── finaltoolMay18/              ← Unified Search UI
│   ├── start.sh                 ← START HERE! ⭐
│   ├── stop.sh                  ← Stop all services
│   ├── test_sop_integration.py  ← Test script
│   ├── unified_search.py        ← Main Flask app
│   └── templates_unified/       ← Web UI templates
│       └── unified_index.html
│
└── kush/mcp-server/mcp-server/  ← MCP Server (SOP search backend)
    ├── start_server.sh          ← MCP server start script
    └── main.py                  ← FastAPI server
```

---

## 📚 Additional Documentation

- **Main README:** [README.md](./README.md) - Full installation & configuration guide
- **SOP Integration:** [SOP_SEARCH_INTEGRATION_GUIDE.md](./SOP_SEARCH_INTEGRATION_GUIDE.md)
- **Integration Summary:** [INTEGRATION_SUMMARY.md](./INTEGRATION_SUMMARY.md)

---

## 🎨 Features

- ✅ **Parallel Search** - Query all 5 sources simultaneously
- ✅ **Category Filtering** - Show/hide individual sources
- ✅ **Result Counts** - See how many results from each source
- ✅ **Clean UI** - Tabbed interface with syntax highlighting
- ✅ **Direct Links** - Click to open Jira/SFDC/Slack/KCS/SOP items
- ✅ **Session Management** - Credentials saved between sessions
- ✅ **Dark Theme** - Easy on the eyes for long troubleshooting sessions

---

**That's it! Happy searching! 🎉**
