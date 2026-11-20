#!/usr/bin/env bash
# Копия данных сервера прогнозов (прогнозы, голоса, очки): раз в сутки, хранится 14 копий.
set -euo pipefail
DATA=${ZV_DATA:-/opt/zvenya/data}
DST=${ZV_BACKUP_DATA:-/opt/zvenya/backup/data}
mkdir -p "$DST"; chmod 700 "$DST"
tar -czf "$DST/data.$(date -u +%Y%m%dT%H%M%SZ).tgz" -C "$(dirname "$DATA")" "$(basename "$DATA")"
{ ls -1t "$DST"/data.*.tgz 2>/dev/null || true; } | tail -n +15 | xargs -r rm -f
echo "копия данных сделана"
