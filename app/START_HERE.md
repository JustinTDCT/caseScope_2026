# 🚀 START HERE - Fresh Install & Remote Access Guide

## What You Now Have

I've created a complete fresh install system for your CaseScope test server:

### 📄 Files Created:

1. **`fresh_install.sh`** ⭐
   - Complete nuclear option script
   - Removes EVERYTHING from old installation
   - Installs fresh from scratch
   - ~15-20 minute runtime

2. **`FRESH_INSTALL_USAGE.md`**
   - Detailed usage guide for the script
   - Step-by-step instructions
   - Troubleshooting tips

3. **`REMOTE_ACCESS.md`**
   - Answers your question about remote server access
   - 5 different methods to choose from
   - My recommendation: Cursor Remote Tunnel

4. **`QUICK_REFERENCE.md`**
   - Cheat sheet for daily operations
   - All essential commands
   - Common troubleshooting

---

## 🎯 Quick Start (3 Steps)

### Step 1: Copy Script to Server (2 minutes)

```bash
# From your Mac
scp fresh_install.sh your-user@your-test-server:/tmp/
```

### Step 2: Run the Script (15-20 minutes)

```bash
# SSH to your test server
ssh your-user@your-test-server

# Run the script
cd /tmp
sudo bash fresh_install.sh

# When prompted, type:
YES DELETE EVERYTHING

# When asked for GitHub username:
# - Enter your username if you've pushed to GitHub
# - Or press Enter to skip (then manually sync files)
```

### Step 3: Access CaseScope

```
Open: http://YOUR_SERVER_IP:5000
Login: admin / admin
⚠️ CHANGE PASSWORD IMMEDIATELY!
```

---

## 🔌 Remote Access Setup (Your Second Question)

You asked: *"is there an agent or something I can install on the test server which lets you interface with it?"*

### My Answer: YES! Several Options

#### **Best Option: VSCode Remote-SSH Extension** (Recommended)

This lets me (AI) directly execute commands on your test server through Cursor's Remote-SSH extension.

**Setup (5 minutes):**
```bash
# On your Mac, add to ~/.ssh/config
cat >> ~/.ssh/config << 'EOF'
Host casescope-test
    HostName YOUR_SERVER_IP
    User YOUR_USERNAME
    IdentityFile ~/.ssh/id_rsa
EOF

# In Cursor:
# 1. Install "Remote - SSH" extension
# 2. CMD+SHIFT+P → "Remote-SSH: Connect to Host"
# 3. Select "casescope-test"
```

**Benefits:**
- ✅ I can execute commands directly on the server
- ✅ Real-time file editing
- ✅ No manual syncing needed
- ✅ See server environment
- ✅ Native Cursor/VSCode integration

#### **Alternative: Simple Deployment Script** (Fastest)

If you want to keep it simple without installing anything:

```bash
# On your Mac, create ~/deploy_casescope.sh
cat > ~/deploy_casescope.sh << 'EOF'
#!/bin/bash
rsync -avz --exclude '.git' \
    /Users/jdube/caseScope_2026/ \
    YOUR_USER@YOUR_SERVER:/opt/casescope/app/

ssh YOUR_USER@YOUR_SERVER << 'REMOTE'
    sudo systemctl restart casescope casescope-worker
    echo "✅ Deployed!"
REMOTE
EOF

chmod +x ~/deploy_casescope.sh

# Use it after making changes
~/deploy_casescope.sh
```

📖 **See `REMOTE_ACCESS.md` for all 4 options with detailed setup**

---

## 📋 What the Fresh Install Script Does

### Destroys:
- ❌ All OpenSearch data & indices
- ❌ All Redis data & queues
- ❌ All case files & uploads
- ❌ Python virtual environment
- ❌ Systemd services
- ❌ Old forensic tools

### Installs Fresh:
- ✅ OpenSearch 2.11.0
- ✅ Redis (cleared)
- ✅ Python 3 + virtualenv
- ✅ CaseScope application
- ✅ evtx_dump, chainsaw
- ✅ SIGMA rules (latest)
- ✅ Systemd services
- ✅ Database (admin/admin)

---

## 🎬 Example Session

```bash
# On your Mac
$ scp fresh_install.sh user@testserver:/tmp/
fresh_install.sh            100%   15KB   1.2MB/s   00:00

$ ssh user@testserver
Welcome to Ubuntu 24.04 LTS

# On test server
user@testserver:~$ cd /tmp
user@testserver:/tmp$ sudo bash fresh_install.sh

╔════════════════════════════════════════════════════════════════╗
║                    ⚠️  DANGER ZONE ⚠️                          ║
║  This script will COMPLETELY DESTROY the old installation     ║
╚════════════════════════════════════════════════════════════════╝

Type 'YES DELETE EVERYTHING' to continue: YES DELETE EVERYTHING

⚠️  Starting complete destruction and reinstall in 5 seconds...

==> Step 1: Stopping all services...
✓ All services stopped

==> Step 2: Removing systemd services...
✓ Systemd services removed

... (continues for 15-20 minutes) ...

✓ Installation complete! 🎉

🌐 Web Interface: http://192.168.1.100:5000
👤 Login: admin / admin
```

---

## 🔍 After Installation

### Verify Everything Works
```bash
# Check services
sudo systemctl status casescope casescope-worker opensearch redis

# Check health
curl localhost:9200/_cluster/health?pretty
redis-cli ping
curl localhost:5000
```

### Test Upload
1. Login to web interface
2. Create a new case
3. Upload a small EVTX file
4. Watch logs: `sudo journalctl -u casescope-worker -f`
5. Verify it processes: Queued → Indexing → SIGMA → Completed

---

## 📚 Documentation Reference

| File | Purpose | When to Read |
|------|---------|--------------|
| `START_HERE.md` (this file) | Quick overview | Read first |
| `FRESH_INSTALL_USAGE.md` | Detailed script guide | Before running script |
| `REMOTE_ACCESS.md` | Remote server access | For CI/CD setup |
| `QUICK_REFERENCE.md` | Daily operations cheat sheet | Keep handy |
| `INSTALL.md` | Original install guide | Reference |
| `DEPLOYMENT_GUIDE.md` | Production deployment | For prod setup |
| `README.md` | Feature documentation | Understanding features |

---

## ⚡ Next Steps

### 1. Run Fresh Install (Now)
```bash
scp fresh_install.sh user@server:/tmp/
ssh user@server
cd /tmp && sudo bash fresh_install.sh
```

### 2. Choose Remote Access Method (After Install)
- Read `REMOTE_ACCESS.md`
- I recommend: VSCode Remote-SSH extension (5 min setup)
- Or use: Simple rsync deployment script (2 min setup)

### 3. Test the System
- Upload a small EVTX file
- Verify processing works
- Check all services are running

### 4. Set Up Daily Workflow
- Save the quick reference commands
- Set up deployment script
- Configure monitoring

---

## 🆘 If Something Goes Wrong

### During Installation:
1. Check logs: `sudo journalctl -xe`
2. Re-run the script (it's idempotent)
3. See `FRESH_INSTALL_USAGE.md` → Troubleshooting section

### After Installation:
1. Check service status: `sudo systemctl status casescope`
2. Check logs: `sudo journalctl -u casescope -n 100`
3. See `QUICK_REFERENCE.md` → Common Issues section

### Nuclear Option:
```bash
# Just run the script again!
sudo bash /tmp/fresh_install.sh
```

---

## 💡 Pro Tips

1. **Always test on small files first** (~10MB EVTX)
2. **Watch worker logs during uploads**: `sudo journalctl -u casescope-worker -f`
3. **Keep an eye on the queue**: `redis-cli LLEN celery` (should be 0 when idle)
4. **OpenSearch takes time**: Wait 30-60 seconds after restart
5. **Use tmux for persistent sessions**: `tmux new -s casescope`
6. **Change default password**: First thing after login!

---

## 📞 Quick Commands

```bash
# Health check (one-liner)
for s in redis opensearch casescope casescope-worker; do systemctl is-active --quiet $s && echo "✓ $s" || echo "✗ $s"; done

# Restart everything
sudo systemctl restart casescope casescope-worker

# Watch logs
sudo journalctl -u casescope-worker -f

# Check queue
redis-cli LLEN celery

# Deploy from Mac (after setting up rsync)
~/deploy_casescope.sh
```

---

## ✅ Success Checklist

After running fresh_install.sh, verify:

- [ ] Script completed without errors
- [ ] All 4 services running: `systemctl status redis opensearch casescope casescope-worker`
- [ ] Can access web UI: `http://SERVER_IP:5000`
- [ ] Can login with admin/admin
- [ ] OpenSearch healthy: `curl localhost:9200`
- [ ] Redis working: `redis-cli ping`
- [ ] Default password changed
- [ ] Test upload processed successfully

If all checked: **You're ready to go! 🎉**

---

## 🎯 Your Two Questions - Answered

### ✅ Question 1: "make me a bash install script that will rip EVERYTHING out"
**Answer:** `fresh_install.sh` (done! ✓)

### ✅ Question 2: "is there an agent or something I can install on the test server which lets you interface with it"
**Answer:** Yes! See `REMOTE_ACCESS.md` for 4 options. I recommend VSCode Remote-SSH extension.

---

## 🚀 Ready to Start?

```bash
# Step 1: Copy script
scp fresh_install.sh user@server:/tmp/

# Step 2: Run it
ssh user@server "cd /tmp && sudo bash fresh_install.sh"

# Step 3: Access CaseScope
open http://your-server-ip:5000
```

**Estimated time:** 20 minutes
**Difficulty:** Easy (script does everything)
**Risk:** None (test server, fresh install)

---

**Good luck! 🍀**

*If you run into issues, check the troubleshooting sections in the other docs or let me know!*

---

**Created:** 2025-10-27  
**CaseScope Version:** 2026 v1.0.0  
**Compatible with:** Ubuntu 24.04 LTS

