# 🔌 Remote Server Access for CaseScope Testing

Since you work on a Mac and SSH into your test server, here are the best options for me (AI) to interface with your remote test server:

## Option 1: VSCode Remote-SSH Extension (RECOMMENDED) ⭐

Use VSCode/Cursor with the Remote-SSH extension to connect directly to your test server. This gives full remote development capabilities.

### Setup:

```bash
# On your Mac, add to ~/.ssh/config:
cat >> ~/.ssh/config << 'EOF'
Host casescope-test
    HostName YOUR_SERVER_IP
    User YOUR_USERNAME
    Port 22
    IdentityFile ~/.ssh/id_rsa
EOF

# Then in Cursor/VSCode:
# 1. Install "Remote - SSH" extension
# 2. CMD+SHIFT+P → "Remote-SSH: Connect to Host"
# 3. Select "casescope-test"
# 4. Opens remote workspace on server
```

This creates a persistent connection where Cursor/VSCode runs on your Mac but all files and commands execute on the server.

### Benefits:
- ✅ Full access to server filesystem
- ✅ Direct command execution on server
- ✅ No manual file syncing needed
- ✅ Real-time file editing
- ✅ Can see server environment variables, services, etc.
- ✅ Native Cursor/VSCode integration

---

## Option 2: Simple SSH + Manual Execution

If you prefer to keep things simple:

1. **On your Mac** - Edit files in Cursor/local editor
2. **Sync to server** - Use rsync or scp
3. **Execute commands** - I provide commands, you run them via SSH

### Quick Sync Script:

```bash
#!/bin/bash
# Save as sync_to_test.sh

rsync -avz --exclude '.git' \
    /Users/jdube/caseScope_2026/ \
    your-user@test-server:/opt/casescope/app/
```

### Usage:
```bash
chmod +x sync_to_test.sh
./sync_to_test.sh  # Run after changes
```

---

## Option 3: Deployment Script with Logging

Create a deployment script that logs all actions for debugging:

```bash
#!/bin/bash
# deploy_and_test.sh

REMOTE_USER="your-user"
REMOTE_HOST="test-server-ip"
REMOTE_PATH="/opt/casescope/app"

echo "📦 Syncing files..."
rsync -avz --exclude '.git' \
    /Users/jdube/caseScope_2026/ \
    ${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_PATH}/

echo "🔄 Restarting services..."
ssh ${REMOTE_USER}@${REMOTE_HOST} << 'EOF'
    sudo systemctl restart casescope
    sudo systemctl restart casescope-worker
    echo "✅ Services restarted"
    
    echo "📊 Service Status:"
    sudo systemctl status casescope --no-pager | head -3
    sudo systemctl status casescope-worker --no-pager | head -3
EOF

echo "✅ Deployment complete!"
```

---

## Option 4: Tmux Session Manager

For persistent SSH sessions during testing:

```bash
# On test server, install tmux
sudo apt install tmux

# Start a named session
tmux new -s casescope

# Detach: Ctrl+B, then D
# Reattach: tmux attach -t casescope
```

This way, if your SSH connection drops, your work continues running.

---

## My Recommendation (Best to Worst):

### 🥇 **Option 1: VSCode Remote-SSH**
- **Best for:** Active development and testing
- **Setup time:** 5 minutes
- **Benefit:** I can directly execute commands and see results, full IDE on remote server

### 🥈 **Option 3: Deployment Script + Logging**
- **Best for:** Quick deployments without remote access setup
- **Setup time:** 2 minutes
- **Benefit:** Simple, no additional tools needed, works immediately

### 🥉 **Option 2: Simple SSH + Manual**
- **Best for:** Manual control, traditional workflow
- **Setup time:** 1 minute
- **Benefit:** Full control, traditional Unix workflow

### 🏅 **Option 4: SSH + Tmux**
- **Best for:** Long-running sessions that survive disconnects
- **Setup time:** 1 minute
- **Benefit:** Persistent sessions, no lost work on disconnect

---

## Quick Start: Get Me Connected to Your Test Server

### Method A: Remote-SSH (5 minutes)

```bash
# On your Mac, add SSH config
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

### Method B: Simple Deployment Script (2 minutes)

```bash
# On your Mac, create this script
cat > ~/deploy_casescope.sh << 'EOF'
#!/bin/bash
rsync -avz --delete --exclude '.git' \
    /Users/jdube/caseScope_2026/ \
    YOUR_USER@YOUR_SERVER:/opt/casescope/app/

ssh YOUR_USER@YOUR_SERVER << 'REMOTE'
    cd /opt/casescope/app
    sudo systemctl restart casescope casescope-worker
    echo "✅ Deployed and restarted"
REMOTE
EOF

chmod +x ~/deploy_casescope.sh

# Run after changes
~/deploy_casescope.sh
```

---

## Security Notes 🔒

1. **SSH Keys:** Use SSH keys instead of passwords
   ```bash
   ssh-keygen -t ed25519
   ssh-copy-id user@test-server
   ```

2. **Firewall:** Ensure port 5000 is accessible (for CaseScope web UI)
   ```bash
   sudo ufw allow 5000/tcp
   ```

3. **Tunnel Security:** If using Cursor tunnel, it uses GitHub authentication

---

## Troubleshooting SSH Issues

```bash
# Test SSH connection
ssh -v your-user@test-server

# Check SSH config
cat ~/.ssh/config

# Fix permissions (if needed)
chmod 700 ~/.ssh
chmod 600 ~/.ssh/id_*
chmod 644 ~/.ssh/id_*.pub
```

---

## What to Do Right Now:

1. **Choose your method** (I recommend Option 1 or 4)
2. **Update `fresh_install.sh`** with your server details
3. **Run the fresh install** on your test server
4. **Set up remote access** using your chosen method

Once you've chosen, let me know and I can provide more specific setup instructions!

