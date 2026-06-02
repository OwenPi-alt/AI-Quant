#!/usr/bin/env bash
set -euo pipefail

need_root() {
  if [ "$(id -u)" -ne 0 ]; then
    echo "Please run bootstrap as root: sudo bash $0"
    exit 1
  fi
}

install_base_packages() {
  apt-get update
  apt-get install -y ca-certificates curl gnupg lsb-release ufw jq git
}

install_docker() {
  if command -v docker >/dev/null 2>&1; then
    echo "Docker already installed"
    return
  fi
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg
  . /etc/os-release
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" >/etc/apt/sources.list.d/docker.list
  apt-get update
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  systemctl enable --now docker
}

install_tailscale() {
  if command -v tailscale >/dev/null 2>&1; then
    echo "Tailscale already installed"
    return
  fi
  curl -fsSL https://tailscale.com/install.sh | sh
  systemctl enable --now tailscaled
}

install_fail2ban() {
  # Why we always install fail2ban: LA's public IP is directly resolvable
  # by anyone with the domain (Cloudflare DNS only, not proxied). SSH
  # brute-force attempts will arrive within hours. Tokyo's eth0 also has
  # port 22 open if SSH is enabled.
  if command -v fail2ban-client >/dev/null 2>&1; then
    echo "fail2ban already installed"
    return
  fi
  apt-get install -y fail2ban
  cat >/etc/fail2ban/jail.d/aiq-sshd.conf <<'EOF'
[sshd]
enabled  = true
mode     = aggressive
maxretry = 5
findtime = 10m
bantime  = 1h
EOF
  systemctl enable --now fail2ban
}

configure_firewall_base() {
  ufw allow OpenSSH || true
  ufw --force enable || true
}

print_ssh_hardening_reminder() {
  cat <<'EOF'

----------------------------------------------------------------------
RECOMMENDED next manual steps (do these from a session that won't lock
you out — keep a second SSH window open):

  1. Ensure your SSH public key is in ~/.ssh/authorized_keys.
     Test it works in a new window BEFORE step 2.
  2. Edit /etc/ssh/sshd_config:
         PasswordAuthentication no
         PermitRootLogin prohibit-password
         PubkeyAuthentication yes
  3. systemctl restart ssh

LA's public IP is reachable from anyone who knows the domain (Cloudflare
DNS only). fail2ban throttles brute-force, but disabling password auth
is the real protection.
----------------------------------------------------------------------
EOF
}
