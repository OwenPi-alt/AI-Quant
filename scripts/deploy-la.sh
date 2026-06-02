#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  echo ".env not found. Run: cp .env.example .env"
  exit 1
fi

bash scripts/tailscale-up.sh la
docker compose -f deploy/la/docker-compose.yml --env-file .env up -d --build
docker compose -f deploy/la/docker-compose.yml --env-file .env ps
