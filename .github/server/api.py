#!/usr/bin/env python3
"""Сервер «Звеньев Салавата» для Telegram Mini App.

Хранит голоса народного состава, коды составов и прогнозы «Моей игры».
Кто пишет — узнаёт по подписи Телеграма (initData), подделать её без токена бота нельзя.
Прогноз принимается только в день матча и до закрытия приёма (за 10 минут до начала),
изменить отправленный прогноз нельзя — это проверяет сервер, а не телефон.

Ещё он ведёт бота: отвечает на /start кнопкой приложения и в день матча
напоминает подписчикам, до скольких принимается прогноз.

Запуск: python3 api.py   (переменные окружения: BOT_TOKEN, ZV_DATA, ZV_PAGE, ZV_PORT)
Только стандартная библиотека Python 3.8+.
"""
import hashlib
import hmac
import json
import os
import re
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qsl, unquote
import urllib.request

TOKEN = os.environ.get("BOT_TOKEN", "").strip()
DATA = os.environ.get("ZV_DATA", "/opt/zvenya/data")
PAGE = os.environ.get("ZV_PAGE", "/opt/zvenya/repo/index.html")
PORT = int(os.environ.get("ZV_PORT", "18787"))
GDEAD = 600  # приём прогнозов закрывается за 10 минут до начала, секунд
MSK = timezone(timedelta(hours=3))
UFA = timezone(timedelta(hours=5))
MAX_BODY = 24000
AUTH_MAX_AGE = 7 * 86400

os.makedirs(DATA, exist_ok=True)
LOCK = threading.RLock()
_cache = {}


def load(name):
    with LOCK:
        if name not in _cache:
            try:
                with open(os.path.join(DATA, name + ".json"), encoding="utf8") as f:
                    _cache[name] = json.load(f)
            except (FileNotFoundError, ValueError):
                _cache[name] = {}
        return _cache[name]


def save(name):
    path = os.path.join(DATA, name + ".json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf8") as f:
        json.dump(_cache[name], f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)


# ---------- календарь из самого приложения: const CAL=[["ГГГГ-ММ-ДД","ЧЧ:ММ","Соперник",дома],...]
_cal = {"mtime": 0, "games": {}}


def calendar():
    try:
        m = os.path.getmtime(PAGE)
    except OSError:
        return _cal["games"]
    if m != _cal["mtime"]:
        try:
            with open(PAGE, encoding="utf8") as f:
                txt = f.read()
            row = re.search(r"^const CAL=(\[.*?\]);?\s*$", txt, re.M)
            games = {}
            for g in json.loads(row.group(1)):
                d, t, opp = g[0], g[1] or "23:59", g[2]
                kick = datetime.fromisoformat(f"{d}T{t}:00").replace(tzinfo=MSK).timestamp()
                games[d] = {"o": opp, "home": bool(g[3]) if len(g) > 3 else True, "kickoff": kick, "deadline": kick - GDEAD}
            _cal.update(mtime=m, games=games)
        except Exception as e:  # не ломаем сервер из-за календаря
            print("календарь не прочитан:", e, file=sys.stderr)
    return _cal["games"]


def deadline_passed(d):
    g = calendar().get(d)
    return bool(g) and time.time() >= g["deadline"]


# ---------- подпись Телеграма
def check_init(init):
    if not TOKEN or not init:
        return None
    pairs = dict(parse_qsl(init, keep_blank_values=True))
    got = pairs.pop("hash", "")
    check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest()
    want = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(want, got):
        return None
    try:
        if time.time() - int(pairs.get("auth_date", "0")) > AUTH_MAX_AGE:
            return None
        u = json.loads(pairs.get("user", "{}"))
    except ValueError:
        return None
    if not u.get("id"):
        return None
    name = " ".join(x for x in [u.get("first_name", ""), u.get("last_name", "")] if x).strip() or u.get("username", "")
    return {"id": str(u["id"]), "name": name[:60]}


# ---------- проверка содержимого
S = lambda x, n=60: x[:n] if isinstance(x, str) and x else None


def clean_pick(p, d):
    if not isinstance(p, dict) or p.get("w") not in ("S", "O"):
        return None
    try:
        gf, ga = int(p.get("gf")), int(p.get("ga"))
    except (TypeError, ValueError):
        return None
    if not (0 <= gf <= 20 and 0 <= ga <= 20):
        return None
    return {"w": p["w"], "gf": gf, "ga": ga, "f": pad(p.get("f"), 4, 3), "d": pad(p.get("d"), 4, 2),
            "g": S(p.get("g")), "a": S(p.get("a")), "o": calendar().get(d, {}).get("o") or S(p.get("o")),
            "ts": int(time.time() * 1000)}


def pad(v, k, w):
    r = lineup(v, k, w)
    return r + [[None] * w for _ in range(k - len(r))]


def lineup(v, k, w):
    v = v if isinstance(v, list) else []
    out = []
    for i in range(min(len(v), k)):
        r = v[i] if isinstance(v[i], list) else []
        out.append([S(r[j]) if j < len(r) else None for j in range(w)])
    return out


# ---------- бот: приветствие, команды, напоминания
def site_host():
    try:
        with open("/etc/caddy/zvenya.caddy", encoding="utf8") as f:
            return f.read().split()[0]
    except (OSError, IndexError):
        return os.environ.get("ZV_HOST", "")


HOST = site_host()
APP = "https://" + HOST if HOST else ""
HOOK_SECRET = hmac.new(TOKEN.encode(), b"zvenya-webhook", hashlib.sha256).hexdigest()[:48] if TOKEN else ""
WELCOME = ("Привет! Это «Звенья Салавата» — составы, статистика и прогнозы «Салавата Юлаева».\n\n"
           "🏒 Собирай свой состав и сравнивай с тренером\n"
           "🎯 «Моя игра»: прогноз на каждый матч и рейтинг болельщиков\n"
           "📊 Таблица, лидеры КХЛ, карточки игроков\n\n"
           "В день матча я напомню, до скольких принимается прогноз. Выключить — /remind.")


def kb(text="Открыть Звенья", frag=""):
    return {"inline_keyboard": [[{"text": text, "web_app": {"url": APP + "/" + frag}}]]}


def tg(method, **params):
    if not TOKEN:
        return None
    req = urllib.request.Request(f"https://api.telegram.org/bot{TOKEN}/{method}",
                                 data=json.dumps(params, ensure_ascii=False).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read())
        except ValueError:
            return {"ok": False, "error_code": e.code}
    except Exception as e:
        print("telegram:", method, e, file=sys.stderr)
        return None


def set_sub(uid, on):
    with LOCK:
        subs = load("subs")
        if bool(subs.get(uid, {}).get("on")) != on:
            subs[uid] = {"on": on, "ts": int(time.time())}
            save("subs")


def bot_setup():
    if not (TOKEN and APP):
        print("бот не настроен: нет токена или адреса сайта", file=sys.stderr)
        return
    r = tg("setWebhook", url=APP + "/api/tg/hook", secret_token=HOOK_SECRET,
           allowed_updates=["message", "my_chat_member"])
    print("webhook:", (r or {}).get("ok"), (r or {}).get("description", ""), flush=True)
    tg("setMyCommands", commands=[{"command": "start", "description": "Открыть приложение"},
                                  {"command": "remind", "description": "Напоминания о прогнозах: включить или выключить"}])
    tg("setMyShortDescription", short_description="Составы, статистика и прогнозы «Салавата Юлаева»")
    tg("setMyDescription", description="«Звенья Салавата»: составы и пятёрки, статистика игроков, таблица и лидеры КХЛ. "
                                       "Делай прогноз на каждый матч, собирай состав и соревнуйся с другими болельщиками.")


def bot_update(u):
    """Ответ на сообщение боту — сразу в ответе вебхука, без лишних запросов."""
    cm = u.get("my_chat_member")
    if cm and cm.get("chat", {}).get("type") == "private":
        st = cm.get("new_chat_member", {}).get("status")
        set_sub(str(cm["chat"]["id"]), st == "member")
        return None
    m = u.get("message") or {}
    chat = m.get("chat") or {}
    if chat.get("type") != "private":
        return None
    uid = str(chat["id"])
    fr = m.get("from") or {}
    name = " ".join(x for x in [fr.get("first_name", ""), fr.get("last_name", "")] if x).strip()
    if name:
        with LOCK:
            names = load("names")
            if names.get(uid) != name[:60]:
                names[uid] = name[:60]
                save("names")
    text = (m.get("text") or "").strip()
    cmd = text.split()[0].split("@")[0].lower() if text else ""
    if cmd == "/start":
        set_sub(uid, True)
        return {"method": "sendMessage", "chat_id": chat["id"], "text": WELCOME, "reply_markup": kb()}
    if cmd in ("/remind", "/stop"):
        on = cmd == "/remind" and not load("subs").get(uid, {}).get("on")
        set_sub(uid, on)
        msg = "🔔 Напоминания включены: в день матча напишу, до скольких принимается прогноз." if on else \
            "🔕 Напоминания выключены. Включить снова — /remind."
        return {"method": "sendMessage", "chat_id": chat["id"], "text": msg}
    return {"method": "sendMessage", "chat_id": chat["id"],
            "text": "Я открываю «Звенья Салавата» — жми кнопку 👇\nНапоминания о прогнозах: /remind", "reply_markup": kb()}


def match_line(g):
    return f"Салават Юлаев — {g['o']}" if g.get("home") else f"{g['o']} — Салават Юлаев"


def reminders():
    """Каждую минуту: в день матча два напоминания тем, кто подписан и ещё не сделал прогноз."""
    while True:
        try:
            now = time.time()
            d = datetime.fromtimestamp(now, UFA).strftime("%Y-%m-%d")
            g = calendar().get(d)
            if g and TOKEN and APP and now < g["deadline"]:
                left = g["deadline"] - now
                kind = "last" if left <= 45 * 60 else "day" if left <= 4 * 3600 else None
                sent = load("sent")
                if kind and not sent.get(d + kind) and not (kind == "day" and left < 55 * 60):
                    with LOCK:
                        sent[d + kind] = int(now)
                        save("sent")
                    k = datetime.fromtimestamp(g["kickoff"], UFA).strftime("%H:%M")
                    dl = datetime.fromtimestamp(g["deadline"], UFA).strftime("%H:%M")
                    if kind == "day":
                        text = f"🏒 Сегодня {match_line(g)}, начало в {k} по Уфе.\nПрогноз принимается до {dl}. Собери состав и угадай счёт!"
                    else:
                        text = f"⏰ Через {max(1, round(left / 60))} минут закрывается приём прогнозов на {match_line(g)} (до {dl} по Уфе). Успевай!"
                    picks = load("game")
                    for uid, sb in list(load("subs").items()):
                        if not sb.get("on") or d in picks.get(uid, {}).get("picks", {}):
                            continue
                        r = tg("sendMessage", chat_id=int(uid), text=text, reply_markup=kb("Сделать прогноз", "#game"))
                        if r and r.get("error_code") == 403:
                            set_sub(uid, False)
                        time.sleep(0.05)
        except Exception as e:
            print("напоминания:", e, file=sys.stderr)
        time.sleep(60)


class H(BaseHTTPRequestHandler):
    server_version = "zvenya"

    def log_message(self, *a):
        pass

    def send(self, code, obj):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def user(self):
        u = check_init(self.headers.get("X-Tg-Init", ""))
        if u:
            names = load("names")
            if names.get(u["id"]) != u["name"]:
                with LOCK:
                    names[u["id"]] = u["name"]
                    save("names")
        return u

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            raise ValueError("слишком большой запрос")
        return json.loads(self.rfile.read(n) or b"{}")

    def parts(self):
        return [unquote(x) for x in self.path.split("?")[0].strip("/").split("/")]

    # ----- чтение
    def do_GET(self):
        p = self.parts()
        if p[:2] == ["api", "health"]:
            return self.send(200, {"ok": True, "games": len(calendar())})
        u = self.user()
        if not u:
            return self.send(401, {"error": "нет подписи Телеграма"})
        if p[:2] == ["api", "me"]:
            return self.send(200, {"id": u["id"], "name": u["name"], "sub": bool(load("subs").get(u["id"], {}).get("on"))})
        if len(p) == 3 and p[1] == "c":
            return self.send(200, {"docs": self.collection(p[2], u)})
        if len(p) == 4 and p[1] == "d":
            c, i = p[2], p[3]
            if c == "shared":
                v = load("shared").get(i)
                return self.send(200, {"exists": v is not None, "data": v})
            if c in ("votes", "game") and i == u["id"]:
                v = load(c).get(i)
                return self.send(200, {"exists": v is not None, "data": v})
            return self.send(200, {"exists": False, "data": None})
        self.send(404, {"error": "нет такого адреса"})

    def collection(self, c, u):
        if c == "votes":
            return [{"id": k, "data": v} for k, v in load("votes").items()]
        if c == "game":
            out = []
            for k, v in load("game").items():
                picks = v.get("picks", {})
                if k != u["id"]:  # чужие прогнозы видно только после закрытия приёма
                    picks = {d: x for d, x in picks.items() if deadline_passed(d)}
                out.append({"id": k, "data": {"picks": picks, "ts": v.get("ts")}})
            return out
        if c == "gameseal":  # закрытые прогнозы: по ним считаются очки
            seal = {}
            for k, v in load("game").items():
                for d, x in v.get("picks", {}).items():
                    if deadline_passed(d):
                        seal.setdefault(d, {})[k] = x
            return [{"id": d, "data": {"d": d, "o": calendar().get(d, {}).get("o"), "n": len(ps), "picks": ps}} for d, ps in seal.items()]
        return []

    # ----- запись
    def do_PUT(self):
        p = self.parts()
        u = self.user()
        if not u:
            return self.send(401, {"error": "нет подписи Телеграма"})
        if len(p) != 4 or p[1] != "d":
            return self.send(404, {"error": "нет такого адреса"})
        c, i = p[2], p[3]
        try:
            data = self.body()
        except ValueError as e:
            return self.send(400, {"error": str(e)})
        if not isinstance(data, dict):
            return self.send(400, {"error": "неверные данные"})
        now = int(time.time() * 1000)
        if c == "votes":
            if i != u["id"]:
                return self.send(403, {"error": "голосовать можно только за себя"})
            with LOCK:
                load("votes")[i] = {"f": lineup(data.get("f"), 4, 3), "d": lineup(data.get("d"), 4, 2), "ts": now}
                save("votes")
            return self.send(200, {"ok": True})
        if c == "shared":
            if not re.fullmatch(r"[a-z0-9]{6}", i):
                return self.send(400, {"error": "неверный код"})
            lu = data.get("lineup") or {}
            with LOCK:
                sh = load("shared")
                if i in sh:
                    return self.send(409, {"error": "код занят"})
                if len(sh) > 50000:
                    return self.send(507, {"error": "хранилище заполнено"})
                sh[i] = {"lineup": {"f": lineup(lu.get("f"), 4, 3), "d": lineup(lu.get("d"), 4, 2)}, "label": S(data.get("label"), 80), "ts": now}
                save("shared")
            return self.send(200, {"ok": True})
        if c == "game":
            if i != u["id"]:
                return self.send(403, {"error": "прогноз можно сделать только за себя"})
            picks = data.get("picks") if isinstance(data.get("picks"), dict) else {}
            cal = calendar()
            with LOCK:
                g = load("game")
                mine = g.setdefault(i, {"picks": {}, "ts": now})
                added = 0
                for d, pk in picks.items():
                    if d in mine["picks"]:
                        continue  # отправленный прогноз не меняется
                    m = cal.get(d)
                    if not m:
                        return self.send(400, {"error": "такого матча нет в календаре"})
                    t = time.time()
                    if t >= m["deadline"]:
                        return self.send(409, {"error": "приём прогнозов на этот матч закрыт"})
                    if datetime.fromtimestamp(t, UFA).strftime("%Y-%m-%d") != d:
                        return self.send(409, {"error": "прогноз принимается только в день матча"})
                    cp = clean_pick(pk, d)
                    if not cp:
                        return self.send(400, {"error": "прогноз заполнен неверно"})
                    mine["picks"][d] = cp
                    added += 1
                mine["ts"] = now
                save("game")
            return self.send(200, {"ok": True, "added": added})
        self.send(403, {"error": "запись запрещена"})

    def do_POST(self):
        p = self.parts()
        if p[:3] == ["api", "tg", "hook"]:
            if not HOOK_SECRET or not hmac.compare_digest(self.headers.get("X-Telegram-Bot-Api-Secret-Token", ""), HOOK_SECRET):
                return self.send(403, {"error": "нет"})
            try:
                ans = bot_update(self.body())
            except Exception as e:
                print("бот:", e, file=sys.stderr)
                ans = None
            return self.send(200, ans or {})
        u = self.user()
        if not u:
            return self.send(401, {"error": "нет подписи Телеграма"})
        if p[:2] == ["api", "profiles"]:
            try:
                ids = self.body().get("ids") or []
            except ValueError as e:
                return self.send(400, {"error": str(e)})
            names = load("names")
            return self.send(200, {str(x): {"name": names.get(str(x), "")} for x in ids[:2000]})
        if p[:2] == ["api", "subscribe"]:
            try:
                on = bool(self.body().get("on"))
            except ValueError as e:
                return self.send(400, {"error": str(e)})
            set_sub(u["id"], on)
            return self.send(200, {"ok": True, "sub": on})
        self.send(404, {"error": "нет такого адреса"})


def watch_self():
    """Когда обновление с GitHub меняет этот файл — выходим, systemd перезапускает уже новую версию."""
    me = os.path.abspath(__file__)
    t0 = os.path.getmtime(me)
    while True:
        time.sleep(60)
        try:
            if os.path.getmtime(me) != t0:
                os._exit(0)
        except OSError:
            pass


if __name__ == "__main__":
    if not TOKEN:
        print("нет BOT_TOKEN — запись и чтение работать не будут", file=sys.stderr)
    threading.Thread(target=watch_self, daemon=True).start()
    threading.Thread(target=bot_setup, daemon=True).start()
    threading.Thread(target=reminders, daemon=True).start()
    print(f"api на 127.0.0.1:{PORT}, матчей в календаре: {len(calendar())}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
