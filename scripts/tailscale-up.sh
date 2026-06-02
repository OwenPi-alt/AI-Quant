#!/usr/bin/env bash
set -euo pipefail

ROLE="${1:?usage: scripts/tailscale-up.sh la|tokyo}"
if [ ! -f .env ]; then
  echo ".env not found"
  exit 1
fi

set -a
source .env
set +a

if [ -z "${TAILSCALE_AUTHKEY:-}" ] || [ "${TAILSCALE_AUTHKEY}" = "__SET_ON_SERVER__" ]; then
  echo "TAILSCALE_AUTHKEY is not set. Create an auth key in Tailscale admin console first."
  exit 1
fi

HOSTNAME="${TAILSCALE_HOSTNAME_TOKYO:-ai-quant-tokyo}"
if [ "$ROLE" = "la" ]; then
  HOSTNAME="${TAILSCALE_HOSTNAME_LA:-ai-quant-la}"
fi

# --accept-dns=true lets the host resolve MagicDNS hostnames (e.g.
# `ai-quant-tokyo`). Docker containers in this stack also set
# `dns: 100.100.100.100` explicitly so they don't depend on the host
# resolver, but enabling MagicDNS on the host helps operators run quick
# `nslookup ai-quant-tokyo` checks.
sudo tailscale up \
  --auth-key "${TAILSCALE_AUTHKEY}" \
  --hostname "${HOSTNAME}" \
  --accept-dns=true \
  --ssh
tailscale status
