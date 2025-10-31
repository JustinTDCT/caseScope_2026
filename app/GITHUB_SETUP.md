# 📦 Push CaseScope 2026 to GitHub

## Current Status
✅ Repository cleaned (16 essential files only)  
✅ Git initialized with 4 commits  
✅ .gitignore configured  
✅ Ready to push to GitHub  

---

## Step 1: Create GitHub Repository

1. Go to https://github.com/new
2. Repository name: `caseScope_2026` (or your preferred name)
3. Description: `CaseScope 2026 v1.0.0 - DFIR Platform (Complete Rebuild)`
4. **Important**: Set to **Public** (so you can `git clone` without credentials)
5. **Do NOT** initialize with README, .gitignore, or license (we already have them)
6. Click "Create repository"

---

## Step 2: Push to GitHub

GitHub will show you commands. Use the **"push an existing repository"** section:

```bash
cd /Users/jdube/caseScope_2026

# Add remote (replace YOUR_USERNAME with your GitHub username)
git remote add origin https://github.com/YOUR_USERNAME/caseScope_2026.git

# Rename branch to main (if needed)
git branch -M main

# Push to GitHub
git push -u origin main

# Push tags
git push origin --tags
```

---

## Step 3: Verify on GitHub

Go to your repository URL:
```
https://github.com/YOUR_USERNAME/caseScope_2026
```

You should see:
- ✅ 16 files
- ✅ README.md displayed on home page
- ✅ v1.0.0 tag
- ✅ 4 commits

---

## Step 4: Clone on Ubuntu Server

Now you can clone it on your server:

```bash
# On Ubuntu server
cd /opt/casescope
sudo git clone https://github.com/YOUR_USERNAME/caseScope_2026.git app

# Verify
cd /opt/casescope/app
ls -la
cat version.json
```

---

## Alternative: Private Repository

If you want to keep it private:

### On GitHub:
1. Set repository to **Private** instead of Public

### On Server:
```bash
# You'll need to authenticate during clone
git clone https://github.com/YOUR_USERNAME/caseScope_2026.git app

# GitHub will prompt for credentials
# Use Personal Access Token (not password)
```

**To create token:**
1. GitHub → Settings → Developer settings → Personal access tokens
2. Generate new token (classic)
3. Select scopes: `repo` (full control)
4. Copy token and use as password during clone

---

## Update on Mac, Pull on Server

After making changes:

### On Mac:
```bash
cd /Users/jdube/caseScope_2026

# Make changes
nano main.py

# Commit
git add -A
git commit -m "feat: Add new feature"

# Push
git push origin main
```

### On Server:
```bash
cd /opt/casescope/app

# Pull updates
sudo git pull origin main

# Restart services
sudo systemctl restart casescope casescope-worker
```

---

## Repository Structure (What's in GitHub)

```
caseScope_2026/
├── Documentation (4 files)
│   ├── README.md              Full features & overview
│   ├── INSTALL.md             Quick start guide
│   ├── DEPLOYMENT_GUIDE.md    Advanced deployment
│   └── SUMMARY.txt            High-level summary
│
├── Core Application (7 files)
│   ├── main.py                Flask web app
│   ├── tasks.py               Celery tasks
│   ├── models.py              Database schema
│   ├── config.py              Configuration
│   ├── celery_app.py          Celery setup
│   ├── utils.py               Helpers
│   └── wsgi.py                WSGI entry point
│
├── Processing Pipeline (3 files)
│   ├── file_processing.py     4 modular functions
│   ├── upload_pipeline.py     Upload system
│   └── upload_integration.py  Route handlers
│
└── Configuration (2 files)
    ├── requirements.txt       Python dependencies
    └── version.json           Version info

Total: 16 files (~137 KB)
```

---

## .gitignore (Already Configured)

The following are automatically excluded from Git:

```
✅ Python cache (__pycache__, *.pyc)
✅ Virtual environment (venv/)
✅ Database files (*.db, *.sqlite)
✅ Logs (*.log)
✅ IDE files (.vscode/, .idea/)
✅ OS files (.DS_Store)
✅ Local config (config_local.py, .env)
✅ Temporary files (tmp/, *.tmp)
```

This means:
- Your database won't be pushed to GitHub
- Logs stay local
- Python cache doesn't clutter the repo

---

## Git Workflow

### Making Changes
```bash
# Edit files
nano main.py

# Check status
git status

# Add changes
git add main.py
# Or add all: git add -A

# Commit
git commit -m "feat: Your change description"

# Push
git push origin main
```

### Best Practices

**Commit messages:**
- `feat: Add new feature` - New functionality
- `fix: Fix bug in upload` - Bug fixes
- `docs: Update README` - Documentation
- `chore: Clean up code` - Maintenance
- `refactor: Improve performance` - Code improvements

**Update version.json:**
```bash
# After significant changes
nano version.json
# Update version: "1.0.0" → "1.1.0"
# Add changelog entry

git add version.json
git commit -m "chore: Bump version to 1.1.0"
git tag -a v1.1.0 -m "Version 1.1.0"
git push origin main --tags
```

---

## Current Git History

```
6f02d2a chore: Clean repository - remove all unneeded folders
50035b6 chore: Add .gitignore and remove old code from repo
632b031 docs: Add deployment guide and summary
e001b07 v1.0.0 - CaseScope 2026 initial release (clean rebuild)
```

**Tags:**
- `v1.0.0` - Initial release

---

## Quick Reference

```bash
# Clone on server
git clone https://github.com/YOUR_USERNAME/caseScope_2026.git

# Update on server
cd /opt/casescope/app
sudo git pull origin main
sudo systemctl restart casescope casescope-worker

# Check version
cat version.json | grep version

# View commits
git log --oneline

# View changes
git diff
```

---

## Ready to Push!

Your repository is clean and ready:
- ✅ 16 essential files only
- ✅ No bloat or legacy code
- ✅ Comprehensive documentation
- ✅ Proper .gitignore
- ✅ Git history with v1.0.0 tag

**Just run:**
```bash
git remote add origin https://github.com/YOUR_USERNAME/caseScope_2026.git
git push -u origin main
git push origin --tags
```

**Then on server:**
```bash
sudo git clone https://github.com/YOUR_USERNAME/caseScope_2026.git /opt/casescope/app
```

🚀 **That's it!**

