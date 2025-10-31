# 🔥 Fresh Install Script - Usage Guide

## What Does This Script Do?

The `fresh_install.sh` script will **COMPLETELY DESTROY** your old CaseScope installation and set up everything from scratch. It's the "nuclear option" for starting fresh.

### It Will Delete:
- ❌ All OpenSearch data and indices
- ❌ All Redis data and queues  
- ❌ All case files and uploads in `/opt/casescope/`
- ❌ Python virtual environment
- ❌ All systemd services
- ❌ Forensic tools (will be re-downloaded)
- ❌ SIGMA rules (will be re-cloned)

### Then It Will Install:
- ✅ OpenSearch 2.11.0 (fresh)
- ✅ Redis (cleared)
- ✅ Python virtual environment (new)
- ✅ CaseScope application
- ✅ All forensic tools (evtx_dump, chainsaw)
- ✅ SIGMA rules repository
- ✅ Systemd services (configured)

---

## 🚀 How to Use

### Step 1: Copy Script to Test Server

```bash
# From your Mac
scp fresh_install.sh your-user@test-server:/tmp/

# Or use rsync
rsync -avz fresh_install.sh your-user@test-server:/tmp/
```

### Step 2: SSH to Test Server

```bash
ssh your-user@test-server
```

### Step 3: Run the Script

```bash
cd /tmp
sudo bash fresh_install.sh
```

### Step 4: Follow the Prompts

The script will:
1. Show you a **BIG WARNING** about what it's about to destroy
2. Ask you to type `YES DELETE EVERYTHING` to confirm
3. Ask for your GitHub username (to clone the repo)
4. Do the complete install (takes ~15-20 minutes)

---

## 📋 What to Prepare Before Running

### 1. Have Your GitHub Username Ready

The script will ask for your GitHub username to clone the repository:
```
Enter your GitHub username: YOUR_USERNAME
```

If you haven't pushed to GitHub yet, press Enter to skip, then manually copy files:
```bash
# On your Mac, after script completes
rsync -avz --exclude '.git' \
    /Users/jdube/caseScope_2026/ \
    your-user@test-server:/opt/casescope/app/
```

### 2. Make Sure You Have Sudo Access

```bash
# Test on server
sudo whoami
# Should output: root
```

### 3. Backup Any Important Data (Optional)

If you have any cases or uploads you want to keep:
```bash
# On test server, before running script
sudo tar -czf ~/casescope_backup_$(date +%Y%m%d).tar.gz /opt/casescope/data /opt/casescope/uploads
```

---

## 🎯 Example Session

```bash
# On your Mac
$ ssh testserver

# On test server
testserver$ cd /tmp
testserver$ sudo bash fresh_install.sh

╔════════════════════════════════════════════════════════════════╗
║                    ⚠️  DANGER ZONE ⚠️                          ║
║                                                                ║
║  This script will COMPLETELY DESTROY the old installation:    ║
║  ...                                                           ║
╚════════════════════════════════════════════════════════════════╝

Type 'YES DELETE EVERYTHING' to continue: YES DELETE EVERYTHING

⚠️  Starting complete destruction and reinstall in 5 seconds...

==> Step 1: Stopping all services...
✓ All services stopped

==> Step 2: Removing systemd services...
✓ Systemd services removed

... (continues for ~15 minutes) ...

==> Step 15: Verifying installation...

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SERVICE STATUS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ✓ redis: RUNNING
  ✓ opensearch: RUNNING
  ✓ casescope: RUNNING
  ✓ casescope-worker: RUNNING

... 

✅ Installation complete! 🎉
```

---

## 🔍 After Installation

### 1. Access the Web Interface

```
http://YOUR_SERVER_IP:5000
```

**Default credentials:**
- Username: `admin`
- Password: `admin`

⚠️ **CHANGE THIS IMMEDIATELY!**

### 2. Check Service Status

```bash
sudo systemctl status casescope
sudo systemctl status casescope-worker
sudo systemctl status opensearch
sudo systemctl status redis
```

### 3. Monitor Logs

```bash
# Web application logs
sudo journalctl -u casescope -f

# Worker logs (watch this during file uploads)
sudo journalctl -u casescope-worker -f

# OpenSearch logs
sudo journalctl -u opensearch -f
```

### 4. Test the System

```bash
# Check OpenSearch health
curl localhost:9200/_cluster/health?pretty

# Check Redis
redis-cli ping

# Check queue (should be 0 when idle)
redis-cli LLEN celery

# Check web app
curl -I localhost:5000
```

---

## 🐛 Troubleshooting

### Script Fails During OpenSearch Installation

```bash
# Check OpenSearch logs
sudo journalctl -u opensearch -n 100

# Manual start
sudo systemctl start opensearch

# Check if port 9200 is in use
sudo lsof -i :9200
```

### Script Fails During Git Clone

If you don't have the repo on GitHub yet:
1. Press Enter when asked for GitHub username
2. After script completes, manually copy files:

```bash
# On your Mac
rsync -avz --exclude '.git' \
    /Users/jdube/caseScope_2026/ \
    your-user@test-server:/opt/casescope/app/

# Then on test server
cd /opt/casescope/app
source /opt/casescope/venv/bin/activate
pip install -r requirements.txt
flask init-db
sudo systemctl restart casescope casescope-worker
```

### Services Won't Start

```bash
# Check for errors
sudo journalctl -xe

# Try starting manually
sudo systemctl start casescope
sudo systemctl start casescope-worker

# Check logs
sudo journalctl -u casescope -n 50
sudo journalctl -u casescope-worker -n 50
```

### Database Initialization Fails

```bash
cd /opt/casescope/app
source /opt/casescope/venv/bin/activate
export FLASK_APP=main.py
flask init-db
```

---

## 🔄 Re-running the Script

You can run this script as many times as you need. Each time it will:
1. Completely wipe the old installation
2. Start fresh from scratch

This is useful for:
- Testing the installation process
- Recovering from a broken installation
- Starting over after major changes

---

## ⏱️ Expected Runtime

| Step | Time |
|------|------|
| Stopping services | 10 seconds |
| Removing old installation | 30 seconds |
| System update | 2-5 minutes |
| Installing dependencies | 1-2 minutes |
| Downloading OpenSearch | 2-3 minutes |
| Starting OpenSearch | 45 seconds |
| Cloning repository | 10 seconds |
| Installing Python packages | 2-3 minutes |
| Downloading forensic tools | 1-2 minutes |
| Cloning SIGMA rules | 1-2 minutes |
| Initializing database | 5 seconds |
| Starting services | 10 seconds |

**Total: ~15-20 minutes**

---

## 📞 Need Help?

If something goes wrong:

1. **Check the logs**: `sudo journalctl -u casescope -n 100`
2. **Verify services**: `sudo systemctl status casescope`
3. **Try manual steps**: Follow INSTALL.md step-by-step
4. **Re-run the script**: It's designed to be idempotent

---

## ✅ Success Checklist

After the script completes, verify:

- [ ] All 4 services are running (redis, opensearch, casescope, casescope-worker)
- [ ] Can access web interface at `http://SERVER_IP:5000`
- [ ] Can login with admin/admin
- [ ] OpenSearch responds: `curl localhost:9200`
- [ ] Redis responds: `redis-cli ping`
- [ ] Forensic tools work: `/opt/casescope/bin/evtx_dump --version`
- [ ] SIGMA rules exist: `ls /opt/casescope/sigma_rules`

If all checked, you're good to go! 🎉

---

**Script Version:** 1.0.0  
**Compatible with:** Ubuntu 24.04 LTS  
**CaseScope Version:** 2026 v1.0.0

