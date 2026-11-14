#!/usr/bin/env bash
# Обновление страницы мини-приложения. Запускает cron от пользователя zvenya каждые 5 минут.
set -euo pipefail
REPO=/opt/zvenya/repo
OUT=/var/www/zvenya
cd "$REPO"
git fetch -q origin main
git reset -q --hard origin/main
TMP=$(mktemp "$OUT/.index.XXXXXX")
{
  printf '%s' '<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="theme-color" content="#00843d"><script src="https://telegram.org/js/telegram-web-app.js"></script></head><body>'
  cat index.html
  printf '%s\n' '</body></html>'
} > "$TMP"
chmod 644 "$TMP"
mv -f "$TMP" "$OUT/index.html"
echo "обновлено $(date -u +%FT%TZ) $(git rev-parse --short HEAD)"
