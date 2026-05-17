# 🚀 Quick Start Guide

## Your 3 Questions Answered

### ✅ 1. What tools do users need to install?

**Option A: Full Features (Jira + SFDC + KCS + Slack)**
```bash
Required:
- Python 3.10+ 
- Poetry
- Podman or Docker (for Slack MCP)

Install:
sudo dnf install python3 python3-pip podman
curl -sSL https://install.python-poetry.org | python3 -
```

**Option B: Without Slack (Jira + SFDC + KCS only)**
```bash
Required:
- Python 3.10+
- Poetry

Install:
sudo dnf install python3 python3-pip
curl -sSL https://install.python-poetry.org | python3 -
```

**Option C: Binary - No Tools Needed!** ⭐
```bash
# Just download and run - no installation!
wget https://github.com/sodoityu/SeekrAI1/releases/download/v1.0/unified-search
chmod +x unified-search
./unified-search
```

---

### ✅ 2. What environment variables need to be set up?

**Option A: Use UI (Easiest - Recommended)** ⭐

No environment variables needed! Just:

1. Start the app
2. Open http://localhost:5500
3. Click ⚙️ Settings
4. Enter credentials
5. Click 💾 Save & Remember

Done! Credentials auto-load next time.

**Option B: Use Environment Variables**

```bash
# Copy template
cp .env.example .env

# Edit .env with your credentials
nano .env

# Load and run
source .env
poetry run python finaltoolMay17/unified_search.py
```

**Required Variables:**
- `JIRA_EMAIL` - Your email
- `JIRA_API_TOKEN` - From https://issues.redhat.com
- `RH_API_OFFLINE_TOKEN` - From https://access.redhat.com/management/api
- `SLACK_XOXC_TOKEN` - From browser cookies
- `SLACK_XOXD_TOKEN` - From browser cookies

---

### ✅ 3. Can they use a binary without installing tools?

**YES! Three ways:**

#### Method 1: PyInstaller Binary (Single Executable)

**Build the binary:**
```bash
cd finaltoolMay17
chmod +x build_binary.sh
./build_binary.sh
```

**Distribute:**
```bash
# Binary location: dist/unified-search
# Size: ~50-100MB
# Upload to GitHub Releases

# Users just run:
chmod +x unified-search
./unified-search
# Open: http://localhost:5500
```

**Pros:**
- ✅ No Python/Poetry needed
- ✅ Single file
- ✅ Works offline

**Cons:**
- ❌ No Slack search (needs Podman/Docker)
- ❌ Large file size (~50-100MB)

---

#### Method 2: Docker Container (Cross-Platform)

**Build image:**
```bash
cd finaltoolMay17
chmod +x build_docker.sh
./build_docker.sh
```

**Users run:**
```bash
docker run -p 5500:5500 sodoityu/unified-search:latest
# Open: http://localhost:5500
```

**Pros:**
- ✅ Cross-platform (Linux, Mac, Windows)
- ✅ All dependencies included
- ✅ Easy updates

**Cons:**
- ❌ Requires Docker
- ❌ Larger size (~500MB)

---

#### Method 3: Flatpak (Linux Desktop)

**For Linux users:**
```bash
# Build Flatpak
flatpak-builder --force-clean build-dir com.github.sodoityu.UnifiedSearch.yml
flatpak-builder --user --install build-dir com.github.sodoityu.UnifiedSearch.yml

# Users run:
flatpak run com.github.sodoityu.UnifiedSearch
```

**Pros:**
- ✅ Sandboxed and secure
- ✅ Native Linux integration
- ✅ Auto-updates

**Cons:**
- ❌ Linux only
- ❌ Complex setup

---

## Recommended Deployment for End Users

### For Developers / Power Users:
```bash
git clone https://github.com/sodoityu/SeekrAI1.git
cd SeekrAI1
poetry install
poetry run python finaltoolMay17/unified_search.py
```

### For Regular Users:
**Download binary from GitHub Releases:**
```bash
# Linux
wget https://github.com/sodoityu/SeekrAI1/releases/download/v1.0/unified-search-linux
chmod +x unified-search-linux
./unified-search-linux

# Mac
curl -LO https://github.com/sodoityu/SeekrAI1/releases/download/v1.0/unified-search-mac
chmod +x unified-search-mac
./unified-search-mac

# Windows
# Download: unified-search.exe
# Double-click to run
```

### For Server Deployment:
```bash
docker run -d -p 5500:5500 \
  -v /path/to/credentials:/app/.saved_credentials.json \
  sodoityu/unified-search:latest
```

---

## Summary

| Method | Tools Needed | Env Vars Needed | Setup Time |
|--------|-------------|-----------------|------------|
| **Full Install** | Python, Poetry, Podman | ❌ Use UI | 5 min |
| **Binary** | None | ❌ Use UI | 0 min |
| **Docker** | Docker only | Optional | 1 min |
| **Flatpak** | Flatpak only | ❌ Use UI | 0 min |

**Best Choice for End Users:** 
- ⭐ **Binary** (easiest - one file, no tools)
- ⭐ **UI Credentials** (no environment variables needed)

---

## Next Steps

1. **Choose distribution method:**
   - Build binary: `./build_binary.sh`
   - Build Docker: `./build_docker.sh`
   - Both: Build and upload to GitHub Releases

2. **Test locally:**
   ```bash
   # Binary
   cd dist
   ./unified-search
   
   # Docker
   docker run -p 5500:5500 unified-search:latest
   ```

3. **Upload to GitHub:**
   - Go to: https://github.com/sodoityu/SeekrAI1/releases
   - Create new release
   - Upload binaries
   - Users download and run!

---

## Need Help?

- 📖 Full guide: [INSTALLATION_GUIDE.md](INSTALLATION_GUIDE.md)
- 🐛 Issues: https://github.com/sodoityu/SeekrAI1/issues
- 💬 Questions: Open an issue on GitHub
