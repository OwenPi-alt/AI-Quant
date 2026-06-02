#!/usr/bin/env sh
set -eu

TS="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="/backups/ai_quant_${TS}.sql.gz"
pg_dump -h postgres -U "${POSTGRES_USER}" "${POSTGRES_DB}" | gzip >"${OUT}"
find /backups -type f -name 'ai_quant_*.sql.gz' -mtime +14 -delete
echo "backup created: ${OUT}"
