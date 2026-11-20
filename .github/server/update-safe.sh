#!/usr/bin/env bash
# БЕЗОПАСНОЕ обновление страницы мини-приложения (замена update.sh; запускается тем же cron каждые 5 минут).
# Отличия от update.sh: не выкладывает версию, пока автопроверка на GitHub не стала зелёной;
# проверяет файл на целостность; хранит копии прежних страниц для отката.
set -euo pipefail
REPO=${ZV_REPO:-/opt/zvenya/repo}
OUT=${ZV_OUT:-/var/www/zvenya}
BK=${ZV_BACKUP:-/opt/zvenya/backup/pages}
SLUG=${ZV_SLUG:-gri1157/zvenya-salavat}
mkdir -p "$BK"
cd "$REPO"
git fetch -q origin main
NEW=$(git rev-parse origin/main)
OLD=$(git rev-parse HEAD)
if [ "$NEW" = "$OLD" ] && [ -s "$OUT/index.html" ]; then exit 0; fi

# 1. Если менялся index.html — ждём зелёную автопроверку именно для этого коммита
if ! git diff --quiet "$OLD" "$NEW" -- index.html; then
  URL=${ZV_CI_URL:-https://api.github.com/repos/$SLUG/commits/$NEW/check-runs?per_page=50}
  JSON=$(curl -fsS -m 20 -H 'Accept: application/vnd.github+json' "$URL" 2>/dev/null || echo '')
  STATE=$(printf '%s' "$JSON" | python3 -c '
import sys, json
try:
    runs = json.load(sys.stdin).get("check_runs", [])
except Exception:
    print("unknown"); sys.exit()
r = [x for x in runs if x.get("name") == "Автопроверка"]
if not r: print("wait")
elif any(x.get("status") != "completed" for x in r): print("wait")
elif all(x.get("conclusion") == "success" for x in r): print("ok")
else: print("fail")')
  case "$STATE" in
    ok) ;;
    wait) echo "ждём автопроверку для ${NEW:0:7}"; exit 0 ;;
    fail) echo "ОТКАЗ: автопроверка ${NEW:0:7} красная, остаёмся на ${OLD:0:7}"; exit 0 ;;
    *) echo "не удалось узнать результат автопроверки ${NEW:0:7}, остаёмся на ${OLD:0:7}"; exit 0 ;;
  esac
fi

# 2. Целостность файла
TMPF=$(mktemp)
trap 'rm -f "$TMPF"' EXIT
git show "$NEW:index.html" > "$TMPF"
SIZE=$(wc -c < "$TMPF")
if [ "$SIZE" -lt 300000 ] || ! grep -q '<title>Звенья Салавата' "$TMPF" || ! grep -q 'const GAMES=' "$TMPF" || ! tail -c 200 "$TMPF" | grep -q '</script>'; then
  echo "ОТКАЗ: файл ${NEW:0:7} не прошёл проверку целостности (размер $SIZE)"; exit 0
fi

# 3. Копия прежней страницы, потом выкладка
[ -s "$OUT/index.html" ] && cp -f "$OUT/index.html" "$BK/index.$(date -u +%Y%m%dT%H%M%SZ).${OLD:0:7}.html"
{ ls -1t "$BK"/index.*.html 2>/dev/null || true; } | tail -n +31 | xargs -r rm -f
git reset -q --hard "$NEW"
TMP=$(mktemp "$OUT/.index.XXXXXX")
{
  printf '%s' '<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="theme-color" content="#00843d"><script src="https://telegram.org/js/telegram-web-app.js"></script></head><body>'
  cat index.html
  printf '%s\n' '</body></html>'
} > "$TMP"
chmod 644 "$TMP"
mv -f "$TMP" "$OUT/index.html"
echo "обновлено $(date -u +%FT%TZ) ${NEW:0:7}"
