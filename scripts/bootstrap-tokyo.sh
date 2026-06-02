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

# Public posture identical to LA: only 22/80/443 reachable from internet.
# Tokyo does NOT actually publish anything on 80/443 to the public; the
# rules exist so `ufw status` looks the same on both hosts.
ufw allow 80/tcp || true
ufw allow 443/tcp || true

# Tokyo's control-api (8080) and Grafana (3000) are reachable ONLY from
# the Tailscale interface. docker-compose binds them directly to the
# Tailscale IP; these ufw rules are defense-in-depth.
ufw allow in on tailscale0 to any port 8080 proto tcp || true
ufw allow in on tailscale0 to any port 3000 proto tcp || true

# Explicit deny so a future docker iptables rule cannot accidentally
# punch these ports through to the public interface.
ufw deny 8080/tcp || true
ufw deny 3000/tcp || true

print_ssh_hardening_reminder

echo "Tokyo bootstrap done. Next: copy repo, create .env, run scripts/deploy-tokyo.sh"
