#!/usr/bin/env bash
# Установка «Звеньев Салавата» как Telegram Mini App на свой сервер (Ubuntu/Debian).
# Запуск на сервере под root:
#   bash <(curl -fsSL https://raw.githubusercontent.com/gri1157/zvenya-salavat/main/.github/server/setup.sh)
# Можно передать свой домен: ... setup.sh) zvenya.мойсайт.ru
set -euo pipefail
say(){ printf '\n\033[1;32m%s\033[0m\n' "$*"; }
die(){ printf '\n\033[1;31mСТОП: %s\033[0m\n' "$*"; exit 1; }

[ "$(id -u)" = 0 ] || die "запусти под root (или через sudo)"
. /etc/os-release 2>/dev/null || true
case "${ID:-}${ID_LIKE:-}" in *ubuntu*|*debian*) ;; *) die "нужна Ubuntu или Debian, а здесь: ${PRETTY_NAME:-неизвестно}";; esac

IP=$(curl -fsS4 --max-time 10 https://api.ipify.org 2>/dev/null || hostname -I | awk '{print $1}')
HOST="${1:-${IP//./-}.sslip.io}"
say "Адрес приложения будет: https://$HOST"

# порты 80 и 443 должны быть свободны (или заняты Caddy)
BUSY=$(ss -ltnpH '( sport = :80 or sport = :443 )' 2>/dev/null | grep -v caddy || true)
[ -z "$BUSY" ] || die "порты 80/443 уже заняты другой программой — ничего не трогаю. Пришли Claude этот текст:
$BUSY"

say "1/6 Ставлю git и веб-сервер Caddy (сам получает https-сертификат)"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq git curl python3 ca-certificates debian-keyring debian-archive-keyring apt-transport-https gnupg >/dev/null
if ! command -v caddy >/dev/null; then
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -qq && apt-get install -y -qq caddy >/dev/null
fi

say "2/6 Отдельный пользователь zvenya без прав root — он только обновляет файлы"
id zvenya >/dev/null 2>&1 || useradd --system --create-home --home-dir /opt/zvenya --shell /usr/sbin/nologin zvenya
mkdir -p /var/www/zvenya && chown zvenya:zvenya /var/www/zvenya && chmod 755 /var/www/zvenya

say "3/6 Забираю приложение с GitHub"
if [ -d /opt/zvenya/repo/.git ]; then runuser -u zvenya -- git -C /opt/zvenya/repo pull -q
else runuser -u zvenya -- git clone -q --depth 20 https://github.com/gri1157/zvenya-salavat.git /opt/zvenya/repo; fi
runuser -u zvenya -- bash /opt/zvenya/repo/.github/server/update.sh

say "4/6 Автообновление каждые 5 минут (сборщик кладёт свежие данные на GitHub — сервер их подхватывает)"
cat > /etc/cron.d/zvenya <<CRON
*/5 * * * * zvenya bash /opt/zvenya/repo/.github/server/update.sh >/opt/zvenya/update.log 2>&1
CRON
chmod 644 /etc/cron.d/zvenya

say "5/6 Сервер прогнозов и голосования"
if [ ! -s /opt/zvenya/bot.env ]; then
  echo "Нужен токен бота из @BotFather (строка вида 123456:ABC...). Он останется только на этом сервере."
  TOKEN=""
  while ! printf '%s' "$TOKEN" | grep -Eq '^[0-9]{5,}:[A-Za-z0-9_-]{30,}$'; do
    read -rsp "Вставь токен и нажми Enter (символы не видны): " TOKEN </dev/tty; echo
    printf '%s' "$TOKEN" | grep -Eq '^[0-9]{5,}:[A-Za-z0-9_-]{30,}$' || echo "Не похоже на токен, попробуй ещё раз."
  done
  umask 077; printf 'BOT_TOKEN=%s\n' "$TOKEN" > /opt/zvenya/bot.env; chown zvenya:zvenya /opt/zvenya/bot.env; chmod 600 /opt/zvenya/bot.env; umask 022
  unset TOKEN
fi
mkdir -p /opt/zvenya/data && chown zvenya:zvenya /opt/zvenya/data && chmod 700 /opt/zvenya/data
cat > /etc/systemd/system/zvenya-api.service <<UNIT
[Unit]
Description=Zvenya Salavata API (Telegram Mini App)
After=network.target
[Service]
User=zvenya
Group=zvenya
EnvironmentFile=/opt/zvenya/bot.env
Environment=ZV_DATA=/opt/zvenya/data ZV_PAGE=/opt/zvenya/repo/index.html ZV_PORT=18787
ExecStart=/usr/bin/python3 /opt/zvenya/repo/.github/server/api.py
Restart=always
RestartSec=3
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/zvenya/data
PrivateTmp=true
MemoryMax=200M
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable -q zvenya-api && systemctl restart zvenya-api
sleep 2
systemctl is-active -q zvenya-api || die "сервер прогнозов не запустился. Пришли Claude вывод команды: journalctl -u zvenya-api -n 30"

say "6/6 Настраиваю https"
cat > /etc/caddy/zvenya.caddy <<CADDY
$HOST {
  encode gzip
  handle /api/* {
    reverse_proxy 127.0.0.1:18787
  }
  handle {
    root * /var/www/zvenya
    header Cache-Control "no-cache"
    file_server
  }
}
CADDY
if ! grep -q 'import zvenya.caddy' /etc/caddy/Caddyfile 2>/dev/null; then
  if grep -q 'root \* /usr/share/caddy' /etc/caddy/Caddyfile 2>/dev/null; then echo 'import zvenya.caddy' > /etc/caddy/Caddyfile
  else echo 'import zvenya.caddy' >> /etc/caddy/Caddyfile; fi
fi
if command -v ufw >/dev/null && ufw status | grep -q active; then ufw allow 80/tcp >/dev/null; ufw allow 443/tcp >/dev/null; fi
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null
systemctl enable -q caddy && systemctl restart caddy

say "Жду сертификат..."
for i in $(seq 1 30); do
  if curl -fsS --max-time 5 -o /dev/null "https://$HOST/" && curl -fsS --max-time 5 "https://$HOST/api/health" | grep -q '"ok"'; then
    say "ГОТОВО. Адрес для BotFather:  https://$HOST"
    exit 0
  fi
  sleep 3
done
die "сертификат не получен за 90 секунд. Проверь в панели Timeweb, что в «Firewall» открыты порты 80 и 443, и запусти команду ещё раз. Адрес: https://$HOST"
