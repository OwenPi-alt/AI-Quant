#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  echo ".env not found. Run: cp .env.example .env"
  exit 1
fi

bash scripts/tailscale-up.sh tokyo

TOKYO_TAILSCALE_IP="${TOKYO_TAILSCALE_IP:-$(tailscale ip -4 2>/dev/null | head -1 || true)}"
if [ -z "${TOKYO_TAILSCALE_IP}" ]; then
  echo "Could not determine Tailscale IPv4 for Tokyo." >&2
  echo "Make sure 'tailscale up' succeeded and 'tailscale ip -4' returns a 100.x address." >&2
  exit 1
fi
export TOKYO_TAILSCALE_IP

echo "Binding container ports to Tailscale IP=${TOKYO_TAILSCALE_IP} (no public exposure)"
docker compose -f deploy/tokyo/docker-compose.yml --env-file .env up -d --build
docker compose -f deploy/tokyo/docker-compose.yml --env-file .env ps
