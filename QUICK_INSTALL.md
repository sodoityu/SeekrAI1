# ⚡ Quick Install - No Dependencies Needed!

Choose the **fastest** method for you:

---

## 🚀 Option 1: Pre-built Binary (FASTEST - 2 minutes)

**No Python, No pip, No Docker needed!**

### For Linux:

```bash
# Download binary
wget https://github.com/sodoityu/SeekrAI1/releases/download/v1.0/unified-search-linux

# Make executable
chmod +x unified-search-linux

# Run it
./unified-search-linux
```

### For macOS:

```bash
# Download binary
curl -L https://github.com/sodoityu/SeekrAI1/releases/download/v1.0/unified-search-macos -o unified-search

# Make executable
chmod +x unified-search

# Run it
./unified-search
```

### For Windows:

```powershell
# Download unified-search.exe from releases
# Double-click to run, or:
.\unified-search.exe
```

**Then:**
1. Open browser: http://localhost:5500
2. Click ⚙️ Settings
3. Enter your tokens (see TOKEN_SETUP_GUIDE.md)
4. Start searching!

**⚠️ Note:** Binary does NOT include Slack MCP support. For Slack search, you'll need Podman/Docker.

---

## 🐳 Option 2: Docker (3 minutes)

**Only need Docker installed!**

```bash
# Pull and run
docker run -d -p 5500:5500 --name unified-search sodoityu/unified-search:latest

# Or build yourself
git clone https://github.com/sodoityu/SeekrAI1.git
cd SeekrAI1
./build_docker.sh
docker run -p 5500:5500 unified-search:latest
```

**Then:**
- Open: http://localhost:5500
- Configure tokens in Settings

---

## 📦 Option 3: Source Code (5 minutes)

**Need Python 3.10+ only!**

```bash
# Clone repo
git clone https://github.com/sodoityu/SeekrAI1.git
cd SeekrAI1

# Install dependencies
pip3 install -r requirements.txt

# Run
./run.sh
```

**Then:**
- Open: http://localhost:5500
- Configure tokens in Settings

---

## 🎯 Which Option to Choose?

| Your Situation | Best Option | Install Time |
|----------------|-------------|--------------|
| **No Python, no Docker** | Binary (Option 1) | 2 minutes |
| **Have Docker** | Docker (Option 2) | 3 minutes |
| **Have Python 3.10+** | Source (Option 3) | 5 minutes |
| **Want full features (Slack)** | Source (Option 3) | 5 minutes + setup MCP |

---

## 🔑 After Installation: Get Your Tokens

You'll need tokens for the systems you want to search:

1. **Slack** - See TOKEN_SETUP_GUIDE.md → Section 1
2. **Jira** - See TOKEN_SETUP_GUIDE.md → Section 2
3. **SFDC** - See TOKEN_SETUP_GUIDE.md → Section 3
4. **KCS** - See TOKEN_SETUP_GUIDE.md → Section 4

---

## ⚙️ Quick Token Setup

```bash
# Open the app
./unified-search   # or ./run.sh

# In browser: http://localhost:5500
# Click: ⚙️ Settings (top right)
# Paste your tokens
# Click: 💾 Save & Remember

# Done! Start searching!
```

---

## 🧪 Test It Works

Search for: `test`

You should see results from:
- ✅ Jira (if Jira token configured)
- ✅ Slack (if Slack tokens configured)
- ✅ SFDC (if SFDC token configured)
- ✅ KCS (if KCS cookies configured)

---

## 🆘 Troubleshooting

### Binary doesn't run
```bash
# Check if executable
chmod +x unified-search

# Run directly
./unified-search

# Check for errors
./unified-search 2>&1 | less
```

### "Address already in use"
```bash
# Port 5500 is taken, kill the process
lsof -ti:5500 | xargs kill -9

# Or use a different port
PORT=5501 ./unified-search
```

### No results from Slack
**Cause:** Binary doesn't support Slack MCP
**Solution:** Use Option 3 (Source) + install Podman

---

## 📊 Comparison

| Feature | Binary | Docker | Source |
|---------|--------|--------|--------|
| **Install Time** | 2 min | 3 min | 5 min |
| **Dependencies** | None | Docker only | Python + pip |
| **Jira Search** | ✅ | ✅ | ✅ |
| **SFDC Search** | ✅ | ✅ | ✅ |
| **KCS Search** | ✅ | ✅ | ✅ |
| **Slack Search** | ❌ (needs MCP) | ✅ | ✅ |
| **File Size** | 17 MB | 200 MB | 100 KB |
| **Portability** | ✅✅✅ | ✅✅ | ✅ |
| **Updates** | Manual | Pull image | Git pull |

---

## 🎉 That's It!

**Fastest path for most users:**
1. Download binary (2 minutes)
2. Run it
3. Configure tokens in Settings UI
4. Start searching!

Need help? Check:
- 📘 TOKEN_SETUP_GUIDE.md - How to get tokens
- 📗 README.md - Full documentation
- 📕 INSTALLATION_GUIDE.md - Detailed installation

**Happy searching! 🔍**
