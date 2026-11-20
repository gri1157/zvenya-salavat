#!/usr/bin/env bash
# Откат страницы на предыдущую копию (запускать вручную на сервере, от пользователя zvenya).
#   bash rollback.sh          — вернуть самую свежую копию
#   bash rollback.sh список   — показать копии
# Внимание: cron через 5 минут снова подтянет main. Чтобы откат держался, нужно откатить и main
# (revert на GitHub) или временно остановить cron.
set -euo pipefail
BK=${ZV_BACKUP:-/opt/zvenya/backup/pages}
OUT=${ZV_OUT:-/var/www/zvenya}
if [ "${1:-}" = "список" ]; then ls -1t "$BK"/index.*.html; exit 0; fi
F=$({ ls -1t "$BK"/index.*.html 2>/dev/null || true; } | head -1)
[ -n "$F" ] || { echo "копий нет"; exit 1; }
cp -f "$F" "$OUT/index.html"
echo "страница возвращена из $F"
