#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/bootstrap-common.sh"

need_root
install_base_packages
install_docker
install_tailscale
install_fail2ban
configure_firewall_base

# Public entrypoint: Caddy serves 80/443 to the internet.
# 80 must be reachable for Let's Encrypt HTTP-01 challenge.
ufw allow 80/tcp || true
ufw allow 443/tcp || true

print_ssh_hardening_reminder

echo "LA bootstrap done. Next: copy repo, create .env, run scripts/deploy-la.sh"
