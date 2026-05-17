# 🐳 Podman Guide - Run Unified Search in Container

Complete guide to run the Unified Search tool using Podman (or Docker).

---

## 📋 Prerequisites

**Install Podman:**

```bash
# Fedora/RHEL
sudo dnf install podman

# Ubuntu/Debian
sudo apt install podman

# macOS
brew install podman
podman machine init
podman machine start

# Verify installation
podman --version
```

**Or use Docker:**
```bash
# Everything works the same, just replace 'podman' with 'docker'
docker --version
```

---

## 🚀 Quick Start (3 Steps)

### Step 1: Build the Image

```bash
cd /home/jayu/asksre/ask-sre/finaltoolMay18

# Build with Podman
podman build -t unified-search:latest .

# Or with Docker
docker build -t unified-search:latest .
```

**What this does:**
- Reads `Dockerfile` 
- Installs Python + Flask + dependencies
- Copies your app files into the image
- Creates a ready-to-run container image

### Step 2: Run the Container

```bash
# Run in foreground (you can see logs)
podman run -p 5500:5500 unified-search:latest

# Or run in background (detached)
podman run -d -p 5500:5500 --name unified-search unified-search:latest
```

**What this does:**
- Starts a container from the image
- Maps port 5500 (container) → 5500 (your machine)
- Names the container "unified-search"

### Step 3: Open in Browser

```
http://localhost:5500
```

Click ⚙️ Settings → Enter your tokens → Save!

---

## 🎯 Common Use Cases

### Use Case 1: Run with Environment Variables

```bash
podman run -p 5500:5500 \
  -e JIRA_EMAIL='your-email@redhat.com' \
  -e JIRA_API_TOKEN='your-jira-token' \
  -e SLACK_XOXC_TOKEN='xoxc-...' \
  -e SLACK_XOXD_TOKEN='xoxd-...' \
  -e SFDC_SESSION_ID='00D...' \
  -e SFDC_INSTANCE_URL='https://redhat.my.salesforce.com' \
  unified-search:latest
```

**Benefit:** No need to configure via UI, credentials loaded automatically!

### Use Case 2: Persistent Credentials (Recommended)

```bash
# Create credentials file on your machine
touch .saved_credentials.json
chmod 600 .saved_credentials.json

# Run with volume mount
podman run -p 5500:5500 \
  -v $(pwd)/.saved_credentials.json:/app/.saved_credentials.json \
  unified-search:latest
```

**Benefit:** Credentials persist even if you stop/restart container!

### Use Case 3: Run in Background

```bash
# Start detached
podman run -d -p 5500:5500 --name unified-search unified-search:latest

# Check status
podman ps

# View logs
podman logs unified-search

# Follow logs (like tail -f)
podman logs -f unified-search

# Stop container
podman stop unified-search

# Start again
podman start unified-search

# Remove container
podman rm unified-search
```

### Use Case 4: Custom Port

```bash
# Run on port 8080 instead of 5500
podman run -p 8080:5500 unified-search:latest

# Access at: http://localhost:8080
```

---

## 🔧 Advanced Configuration

### Mount Multiple Files

```bash
podman run -p 5500:5500 \
  -v $(pwd)/.saved_credentials.json:/app/.saved_credentials.json \
  -v $(pwd)/.mcp.json:/app/.mcp.json \
  -v $(pwd)/custom-config:/app/config \
  unified-search:latest
```

### Run with MCP Servers (Slack Support)

For Slack search to work, the container needs access to Podman socket:

```bash
# Run with Podman socket mounted
podman run -p 5500:5500 \
  -v /run/podman/podman.sock:/run/podman/podman.sock:Z \
  -e SLACK_XOXC_TOKEN='xoxc-...' \
  -e SLACK_XOXD_TOKEN='xoxd-...' \
  unified-search:latest
```

**Or use host network mode:**

```bash
podman run --network=host \
  -v /run/podman/podman.sock:/run/podman/podman.sock:Z \
  unified-search:latest
```

### Auto-Restart on Reboot

```bash
# Run with restart policy
podman run -d -p 5500:5500 \
  --name unified-search \
  --restart=always \
  unified-search:latest
```

---

## 📊 Container Management

### List Containers

```bash
# Show running containers
podman ps

# Show all containers (including stopped)
podman ps -a

# Show images
podman images
```

### Check Logs

```bash
# View logs
podman logs unified-search

# Follow logs in real-time
podman logs -f unified-search

# Last 50 lines
podman logs --tail 50 unified-search

# With timestamps
podman logs -t unified-search
```

### Enter Running Container

```bash
# Get a shell inside the container
podman exec -it unified-search /bin/bash

# Run a single command
podman exec unified-search ls -la /app

# Check Python version
podman exec unified-search python3 --version
```

### Stop/Start/Restart

```bash
# Stop container
podman stop unified-search

# Start stopped container
podman start unified-search

# Restart running container
podman restart unified-search

# Remove container
podman stop unified-search
podman rm unified-search

# Remove container (force)
podman rm -f unified-search
```

### Clean Up

```bash
# Remove stopped containers
podman container prune

# Remove unused images
podman image prune

# Remove everything (careful!)
podman system prune -a
```

---

## 🐳 Dockerfile Explained

Let's look at what's in the `Dockerfile`:

```dockerfile
# Start with Python 3.10 base image
FROM python:3.10-slim

# Set working directory inside container
WORKDIR /app

# Copy application files
COPY unified_search.py .
COPY slack_search_standalone.py .
COPY .mcp.json .
COPY templates_unified/ templates_unified/
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose port 5500
EXPOSE 5500

# Run the application
CMD ["python3", "unified_search.py"]
```

**What each line does:**
- `FROM`: Base operating system + Python
- `WORKDIR`: Where files go inside container
- `COPY`: Copy your files into container
- `RUN`: Install dependencies
- `EXPOSE`: Document which port app uses
- `CMD`: Command to run when container starts

---

## 🔍 Troubleshooting

### Problem: "Port already in use"

```bash
# Find what's using port 5500
lsof -i :5500

# Kill it
kill -9 <PID>

# Or use a different port
podman run -p 5501:5500 unified-search:latest
```

### Problem: "Cannot connect to Podman socket"

```bash
# Start Podman service
systemctl --user start podman.socket

# Enable on boot
systemctl --user enable podman.socket

# Check status
systemctl --user status podman.socket
```

### Problem: "Permission denied" when mounting volumes

```bash
# Use :Z flag for SELinux systems (Fedora/RHEL)
podman run -p 5500:5500 \
  -v $(pwd)/.saved_credentials.json:/app/.saved_credentials.json:Z \
  unified-search:latest
```

### Problem: Container exits immediately

```bash
# Check logs to see error
podman logs unified-search

# Run in foreground to see output
podman run -p 5500:5500 unified-search:latest
```

### Problem: "No module named 'flask'"

```bash
# Rebuild image (dependencies might not have installed)
podman build --no-cache -t unified-search:latest .
```

### Problem: Can't access from other machines

```bash
# Bind to all interfaces, not just localhost
podman run -p 0.0.0.0:5500:5500 unified-search:latest

# Or use host network mode
podman run --network=host unified-search:latest
```

---

## 📤 Share Your Image

### Save Image to File

```bash
# Save image as tar file
podman save -o unified-search.tar unified-search:latest

# Compress it
gzip unified-search.tar

# Share unified-search.tar.gz with others
```

### Load Image from File

```bash
# Decompress
gunzip unified-search.tar.gz

# Load into Podman
podman load -i unified-search.tar

# Run it
podman run -p 5500:5500 unified-search:latest
```

### Push to Container Registry

```bash
# Tag for Docker Hub
podman tag unified-search:latest sodoityu/unified-search:latest

# Login to Docker Hub
podman login docker.io

# Push
podman push sodoityu/unified-search:latest
```

Then others can:
```bash
podman pull sodoityu/unified-search:latest
podman run -p 5500:5500 sodoityu/unified-search:latest
```

---

## 🎯 Quick Reference

### Build & Run

```bash
# Build
podman build -t unified-search:latest .

# Run (foreground)
podman run -p 5500:5500 unified-search:latest

# Run (background)
podman run -d -p 5500:5500 --name unified-search unified-search:latest
```

### Manage

```bash
# List
podman ps
podman images

# Logs
podman logs unified-search
podman logs -f unified-search

# Shell
podman exec -it unified-search /bin/bash

# Stop/Start
podman stop unified-search
podman start unified-search
podman restart unified-search

# Remove
podman rm -f unified-search
podman rmi unified-search:latest
```

### With Credentials

```bash
# Environment variables
podman run -p 5500:5500 \
  -e JIRA_API_TOKEN='token' \
  unified-search:latest

# Volume mount
podman run -p 5500:5500 \
  -v $(pwd)/.saved_credentials.json:/app/.saved_credentials.json:Z \
  unified-search:latest
```

---

## ✅ Best Practices

1. **Use volume mounts** for credentials (persistent)
2. **Run in background** with `-d` flag for production
3. **Use `--restart=always`** for auto-restart on reboot
4. **Check logs regularly** with `podman logs`
5. **Clean up old containers** with `podman system prune`
6. **Tag your images** with versions: `unified-search:v1.0`

---

## 🆚 Podman vs Docker

Everything in this guide works with both!

```bash
# Podman
podman build -t unified-search .
podman run -p 5500:5500 unified-search

# Docker (same commands!)
docker build -t unified-search .
docker run -p 5500:5500 unified-search
```

**Differences:**
- Podman: Rootless by default (more secure)
- Docker: Requires daemon
- Both: Use same Dockerfile format

---

## 🎉 Summary

**3 commands to get started:**

```bash
# 1. Build
podman build -t unified-search .

# 2. Run
podman run -d -p 5500:5500 --name unified-search unified-search:latest

# 3. Use
open http://localhost:5500
```

**That's it! Your tool is now running in a container!** 🚀

Need help? Check:
- **TOKEN_SETUP_GUIDE.md** - How to get tokens
- **README.md** - Full documentation
- **Dockerfile** - Container configuration
