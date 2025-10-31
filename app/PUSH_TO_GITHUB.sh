#!/bin/bash
#
# CaseScope 2026 - GitHub Push Helper Script
# 
# This script helps you push your code to GitHub
#

set -e

REPO_URL="https://github.com/JustinTDCT/caseScope_2026.git"
REPO_DIR="/opt/casescope/app"

echo "═══════════════════════════════════════════════════════════════"
echo "  CaseScope 2026 - GitHub Push Helper"
echo "═══════════════════════════════════════════════════════════════"
echo ""

cd "$REPO_DIR"

# Check if git is initialized
if [ ! -d ".git" ]; then
    echo "❌ Error: Not a git repository"
    echo "   Run: cd $REPO_DIR && git init"
    exit 1
fi

# Check if remote is configured
if ! git remote get-url origin &>/dev/null; then
    echo "📝 Adding remote origin..."
    git remote add origin "$REPO_URL"
else
    echo "✓ Remote origin already configured"
fi

# Show current status
echo ""
echo "📊 Current Git Status:"
echo "───────────────────────────────────────────────────────────────"
git status --short | head -20
echo ""

# Check for uncommitted changes
if ! git diff-index --quiet HEAD -- 2>/dev/null; then
    echo "⚠️  You have uncommitted changes"
    echo ""
    read -p "Do you want to commit all changes now? (y/n): " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo ""
        read -p "Enter commit message: " commit_msg
        git add -A
        git commit -m "$commit_msg"
        echo "✓ Changes committed"
    else
        echo "⏭️  Skipping commit"
    fi
fi

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  AUTHENTICATION OPTIONS"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "Choose an authentication method:"
echo ""
echo "  1) HTTPS with Personal Access Token (Recommended)"
echo "  2) SSH with SSH Key"
echo "  3) Manual push (I'll do it myself)"
echo ""
read -p "Enter choice (1-3): " -n 1 -r
echo ""
echo ""

case $REPLY in
    1)
        echo "═══════════════════════════════════════════════════════════════"
        echo "  OPTION 1: Personal Access Token (PAT)"
        echo "═══════════════════════════════════════════════════════════════"
        echo ""
        echo "📝 Steps to create a GitHub Personal Access Token:"
        echo ""
        echo "   1. Go to: https://github.com/settings/tokens"
        echo "   2. Click: 'Generate new token' → 'Generate new token (classic)'"
        echo "   3. Name: 'CaseScope Server'"
        echo "   4. Expiration: Choose duration (90 days recommended)"
        echo "   5. Scopes: Check 'repo' (Full control of private repositories)"
        echo "   6. Click: 'Generate token'"
        echo "   7. Copy the token (starts with ghp_...)"
        echo ""
        echo "⚠️  IMPORTANT: Save this token somewhere safe!"
        echo "   You won't be able to see it again."
        echo ""
        read -p "Enter your Personal Access Token: " -s github_token
        echo ""
        echo ""
        
        if [ -z "$github_token" ]; then
            echo "❌ No token provided. Exiting."
            exit 1
        fi
        
        # Configure credential helper to store token
        git config credential.helper store
        
        # Update remote URL to include token
        git remote set-url origin "https://${github_token}@github.com/JustinTDCT/caseScope_2026.git"
        
        echo "✓ Token configured"
        echo ""
        read -p "Push to GitHub now? This will OVERWRITE the remote repository. (y/n): " -n 1 -r
        echo ""
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            echo ""
            echo "🚀 Pushing to GitHub..."
            git push -u origin main --force
            echo ""
            echo "✅ Successfully pushed to GitHub!"
            echo ""
            echo "   View at: https://github.com/JustinTDCT/caseScope_2026"
        fi
        
        # Clean up URL for security
        git remote set-url origin "$REPO_URL"
        ;;
        
    2)
        echo "═══════════════════════════════════════════════════════════════"
        echo "  OPTION 2: SSH Key Authentication"
        echo "═══════════════════════════════════════════════════════════════"
        echo ""
        echo "📝 Setting up SSH key..."
        echo ""
        
        if [ ! -f ~/.ssh/id_ed25519 ]; then
            read -p "Enter your GitHub email: " github_email
            ssh-keygen -t ed25519 -C "$github_email" -f ~/.ssh/id_ed25519 -N ""
            eval "$(ssh-agent -s)"
            ssh-add ~/.ssh/id_ed25519
            echo ""
            echo "✓ SSH key generated"
        else
            echo "✓ SSH key already exists"
        fi
        
        echo ""
        echo "📋 Your PUBLIC SSH key (copy this):"
        echo "───────────────────────────────────────────────────────────────"
        cat ~/.ssh/id_ed25519.pub
        echo "───────────────────────────────────────────────────────────────"
        echo ""
        echo "📝 Add this key to GitHub:"
        echo ""
        echo "   1. Go to: https://github.com/settings/keys"
        echo "   2. Click: 'New SSH key'"
        echo "   3. Title: 'CaseScope Server'"
        echo "   4. Key: Paste the key above"
        echo "   5. Click: 'Add SSH key'"
        echo ""
        read -p "Press ENTER after adding the key to GitHub..." 
        
        # Update remote to use SSH
        git remote set-url origin "git@github.com:JustinTDCT/caseScope_2026.git"
        
        echo ""
        echo "🔍 Testing SSH connection..."
        ssh -T git@github.com 2>&1 | grep -q "successfully authenticated" && echo "✓ SSH authentication successful" || echo "⚠️  SSH test failed, but trying to push anyway..."
        
        echo ""
        read -p "Push to GitHub now? This will OVERWRITE the remote repository. (y/n): " -n 1 -r
        echo ""
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            echo ""
            echo "🚀 Pushing to GitHub..."
            git push -u origin main --force
            echo ""
            echo "✅ Successfully pushed to GitHub!"
            echo ""
            echo "   View at: https://github.com/JustinTDCT/caseScope_2026"
        fi
        ;;
        
    3)
        echo "═══════════════════════════════════════════════════════════════"
        echo "  OPTION 3: Manual Push"
        echo "═══════════════════════════════════════════════════════════════"
        echo ""
        echo "📝 To push manually, run one of these commands:"
        echo ""
        echo "   # With HTTPS (will prompt for username/password):"
        echo "   cd $REPO_DIR"
        echo "   git push -u origin main --force"
        echo ""
        echo "   # With SSH (after setting up SSH key):"
        echo "   cd $REPO_DIR"
        echo "   git remote set-url origin git@github.com:JustinTDCT/caseScope_2026.git"
        echo "   git push -u origin main --force"
        echo ""
        ;;
        
    *)
        echo "❌ Invalid choice. Exiting."
        exit 1
        ;;
esac

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  ✅ DONE"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "Repository: https://github.com/JustinTDCT/caseScope_2026"
echo ""
echo "To push changes in the future, you can:"
echo ""
echo "  cd $REPO_DIR"
echo "  git add -A"
echo "  git commit -m \"Your commit message\""
echo "  git push"
echo ""
