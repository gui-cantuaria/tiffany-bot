#!/bin/bash
# One-time setup so GitHub Actions can SSH into this VPS and run deploy.sh.
# Run on the VPS as root: bash scripts/setup-github-actions.sh
#
# After this script, add the printed secrets to GitHub:
#   Repo → Settings → Secrets and variables → Actions

set -e

KEY="$HOME/.ssh/github_deploy"
AUTH="$HOME/.ssh/authorized_keys"

echo "=== GitHub Actions deploy setup ==="

if [ ! -f "$KEY" ]; then
    echo "Generating deploy key..."
    ssh-keygen -t ed25519 -f "$KEY" -N "" -C "github-actions-deploy"
fi

# Allow GitHub Actions (and you) to SSH in with this key.
grep -qF "$(cat "${KEY}.pub")" "$AUTH" 2>/dev/null || cat "${KEY}.pub" >> "$AUTH"
chmod 600 "$AUTH"

# Git fetch/pull from GitHub via SSH (no token prompts).
if [ ! -f "$HOME/.ssh/config" ] || ! grep -q "Host github.com" "$HOME/.ssh/config" 2>/dev/null; then
    cat >> "$HOME/.ssh/config" <<'EOF'
Host github.com
    HostName github.com
    User git
    IdentityFile ~/.ssh/github_deploy
    IdentitiesOnly yes
EOF
    chmod 600 "$HOME/.ssh/config"
fi

cd /opt/tiffany-bot 2>/dev/null || true
if [ -d /opt/tiffany-bot/.git ]; then
    git remote set-url origin git@github.com:gui-cantuaria/tiffany-bot.git 2>/dev/null || true
fi

IP=$(curl -s --max-time 5 ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')

echo ""
echo "=== Add these GitHub Secrets ==="
echo "Repo: https://github.com/gui-cantuaria/tiffany-bot/settings/secrets/actions"
echo ""
echo "VPS_HOST"
echo "  $IP"
echo ""
echo "VPS_SSH_KEY  (paste the block below — includes BEGIN/END lines)"
echo "----------------------------------------"
cat "$KEY"
echo "----------------------------------------"
echo ""
echo "Also add the PUBLIC key to GitHub → Settings → SSH keys (if not done yet):"
echo "$(cat "${KEY}.pub")"
echo ""
echo "Test from your machine after saving secrets:"
echo "  gh workflow run deploy.yml"
echo ""
