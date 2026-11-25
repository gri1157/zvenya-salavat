#!/usr/bin/env python3
"""Сервер «Звеньев Салавата» для Telegram Mini App.

Хранит голоса народного состава, коды составов и прогнозы «Моей игры».
Кто пишет — узнаёт по подписи Телеграма (initData), подделать её без токена бота нельзя.
Прогноз принимается только в день матча и до закрытия приёма (за 10 минут до начала),
изменить отправленный прогноз нельзя — это проверяет сервер, а не телефон.

Ещё он ведёт бота: отвечает на /start кнопкой приложения и в день матча
напоминает подписчикам, до скольких принимается прогноз.

Лиги с друзьями, итоги матча (очки считает GitHub по тем же правилам, что и приложение,
и кладёт их в .github/data/results.json) — тоже здесь.

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
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qsl, unquote
import urllib.request

TOKEN = os.environ.get("BOT_TOKEN", "").strip()
DATA = os.environ.get("ZV_DATA", "/opt/zvenya/data")
PAGE = os.environ.get("ZV_PAGE", "/opt/zvenya/repo/index.html")
# разбор последнего матча: готовит GitHub (.github/data/razbor_export.js) из самого приложения
RAZBOR = os.environ.get("ZV_RAZBOR", os.path.join(os.path.dirname(PAGE), ".github", "data", "razbor.json"))
ALERTS = os.environ.get("ZV_ALERTS", os.path.join(os.path.dirname(PAGE), ".github", "data", "alerts.json"))
RESULTS = os.environ.get("ZV_RESULTS", os.path.join(os.path.dirname(PAGE), ".github/data/results.json"))
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
WELCOME = ("<b>🏒 Звенья Салавата</b>\n\n"
           "<b>Заходи в игру, выставляй свой состав и своего топового игрока!</b>\n"
           "🎯 Угадывай счёт матча\n"
           "🏆 Получай очки и соревнуйся с другими болельщиками\n\n"
           "🔔 В день матча напомню о прогнозе — /remind\n"
           "⚡ Во время матча пришлю голы, периоды и итог (выключить — /goals)\n"
           "👥 Добавь меня в чат болельщиков — буду вести матч и там")
DESCRIPTION = ("🏒 Звенья Салавата — игра для болельщиков «Салавата Юлаева»\n\n"
               "▶️ Заходи в игру\n"
               "🧩 Выставляй свой состав на матч\n"
               "⭐ Выбирай своего топового игрока\n"
               "🎯 Угадывай счёт\n"
               "🏆 Получай очки и соревнуйся с другими болельщиками\n\n"
               "Жми «Запустить» 👇")
SHORT_DESCRIPTION = "🏒 Собирай состав, выбирай топового игрока, получай очки и соревнуйся с болельщиками «Салавата»!"


def kb(text="Открыть Звенья", frag="", style="success"):
    """Кнопка приложения; style: success — зелёная, primary — синяя, danger — красная."""
    b = {"text": text, "web_app": {"url": APP + "/" + frag}}
    if style:
        b["style"] = style
    return {"inline_keyboard": [[b]]}


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
            sb = subs.setdefault(uid, {})
            sb.update(on=on, ts=int(time.time()))
            save("subs")


def bot_setup():
    if not (TOKEN and APP):
        print("бот не настроен: нет токена или адреса сайта", file=sys.stderr)
        return
    r = tg("setWebhook", url=APP + "/api/tg/hook", secret_token=HOOK_SECRET,
           allowed_updates=["message", "my_chat_member", "callback_query"])
    print("webhook:", (r or {}).get("ok"), (r or {}).get("description", ""), flush=True)
    tg("setMyCommands", commands=[{"command": "start", "description": "Открыть приложение"},
                                  {"command": "remind", "description": "Напоминания о прогнозах: включить или выключить"},
                                  {"command": "goals", "description": "Матч онлайн: периоды и голы — включить или выключить"},
                                  {"command": "table", "description": "Рейтинг прогнозистов"}])
    tg("setChatMenuButton", menu_button={"type": "web_app", "text": "Играть", "web_app": {"url": APP + "/"}})
    tg("setMyShortDescription", short_description=SHORT_DESCRIPTION)
    tg("setMyDescription", description=DESCRIPTION)


# ---------- чаты болельщиков: бот, добавленный в группу, ведёт матч и там
def kb_url(text="🏒 Играть", param="game"):
    """В группах кнопка-приложение запрещена Телеграмом, поэтому обычная ссылка на бота."""
    n = bot_name()
    if not n:
        return None
    return {"inline_keyboard": [[{"text": text, "url": f"https://t.me/{n}?startapp={param}", "style": "success"}]]}


def group_push(text, silent=False, **extra):
    """Сообщение во все чаты болельщиков; возвращает [(чат, номер сообщения)] — по ним потом дописываем передачи."""
    out = []
    for cid, gr in list(load("groups").items()):
        if not gr.get("on"):
            continue
        r = tg("sendMessage", chat_id=int(cid), text=text, disable_notification=silent, **extra)
        if r and r.get("error_code") == 403:
            with LOCK:
                load("groups")[cid]["on"] = False
                save("groups")
        mid = ((r or {}).get("result") or {}).get("message_id")
        if mid:
            out.append([int(cid), mid])
        time.sleep(0.05)
    return out


def season_table(limit=10):
    """Рейтинг сезона по подсчитанным матчам: [(имя, очки, матчей)]."""
    by = uid_by_pid()
    names = load("names")
    tot = {}
    for d, m in results().items():
        for p, x in m.get("s", {}).items():
            t = tot.setdefault(p, [0, 0])
            t[0] += x["tot"]
            t[1] += 1
    rows = sorted(tot.items(), key=lambda kv: -kv[1][0])[:limit]
    return [(names.get(by.get(p, ""), "") or "Болельщик", v[0], v[1]) for p, v in rows]


def table_text():
    rows = season_table()
    if not rows:
        return "🏆 Рейтинг прогнозистов пока пуст: очки появятся после первого подсчитанного матча.\nСделай прогноз на ближайший матч 👇"
    medals = {0: "🥇", 1: "🥈", 2: "🥉"}
    return "🏆 Рейтинг прогнозистов сезона\n" + "\n".join(
        f"{medals.get(i, str(i + 1) + '.')} {n} — {pts} {ru_pts(pts)} ({gp} м.)" for i, (n, pts, gp) in enumerate(rows))


def owner_id():
    o = load("owner").get("id")
    if o:
        return o
    names = load("names")
    return next(iter(names), None)  # первый, кто написал боту, — владелец


def admin_text():
    names, subs, game = load("names"), load("subs"), load("game")
    on = sum(1 for v in subs.values() if v.get("on"))
    live = sum(1 for v in subs.values() if v.get("on") and v.get("goals", True))
    groups = load("groups")
    per = {}
    for uid, v in game.items():
        for d in v.get("picks", {}):
            per[d] = per.get(d, 0) + 1
    last = sorted(per.items())[-6:]
    cal = calendar()
    now = time.time()
    nxt = min((g for g in cal.items() if g[1]["kickoff"] > now), key=lambda g: g[1]["kickoff"], default=None)
    lines = ["📊 Панель владельца",
             f"Открыли бота: {len(names)}",
             f"Получают напоминания: {on}",
             f"Матч онлайн включён: {live}",
             f"Чаты болельщиков: {sum(1 for g in groups.values() if g.get('on'))}",
             f"Лиги: {len(load('leagues'))}",
             f"Голосов в народном составе: {len(load('votes'))}",
             f"Сделали хотя бы один прогноз: {sum(1 for v in game.values() if v.get('picks'))}",
             "", "Прогнозов по матчам:"]
    lines += [f"• {d[8:10]}.{d[5:7]} {cal.get(d, {}).get('o', '')}: {n}" for d, n in last] or ["• пока нет"]
    mv = load("mvp")
    if mv:
        d = max(mv)
        lines += ["", f"Голосов за лучшего игрока {d[8:10]}.{d[5:7]}: {len(mv[d].get('v', {}))}"]
    if nxt:
        k = datetime.fromtimestamp(nxt[1]["kickoff"], UFA).strftime("%d.%m в %H:%M")
        lines += ["", f"Следующий матч: {nxt[1]['o']}, {k} по Уфе; прогнозов уже {per.get(nxt[0], 0)}"]
    try:
        age = int((now - os.path.getmtime(PAGE)) / 3600)
        lines.append(f"Данные приложения обновлены {age} ч назад")
    except OSError:
        pass
    return "\n".join(lines)


# ---------- лучший игрок матча: голосование кнопками после финальной сирены
def mvp_markup(d, cands):
    return {"inline_keyboard": [[{"text": c, "callback_data": f"mvp|{d}|{i}"}] for i, c in enumerate(cands)]}


def mvp_tally(d):
    mv = load("mvp").get(d)
    if not mv:
        return None
    cnt = [0] * len(mv["c"])
    for i in mv.get("v", {}).values():
        if 0 <= i < len(cnt):
            cnt[i] += 1
    order = sorted(range(len(cnt)), key=lambda i: -cnt[i])
    return {"d": d, "o": mv.get("o", ""), "total": sum(cnt), "open": time.time() - mv.get("ts", 0) < 20 * 3600,
            "c": [{"name": mv["c"][i], "n": cnt[i]} for i in order]}


def mvp_vote(q):
    """Нажатие кнопки голосования → ответ-всплывашка."""
    ans = {"method": "answerCallbackQuery", "callback_query_id": q.get("id")}
    try:
        _, d, i = (q.get("data") or "").split("|")
        i = int(i)
    except ValueError:
        return ans
    uid = str((q.get("from") or {}).get("id") or "")
    with LOCK:
        mv = load("mvp").get(d)
        if not mv or not uid or not 0 <= i < len(mv["c"]):
            return dict(ans, text="Голосование не найдено")
        if time.time() - mv.get("ts", 0) > 20 * 3600:
            return dict(ans, text="Голосование уже закрыто")
        mv.setdefault("v", {})[uid] = i
        save("mvp")
    t = mvp_tally(d)
    lead = t["c"][0]
    return dict(ans, text=f"Голос принят: {mv['c'][i]}.\nЛидирует {lead['name']} — {lead['n']} из {t['total']}")


def mgr_points(pk, us, them):
    """Очки генменеджера по счёту — те же правила, что в приложении: победитель 100, точный счёт 50, иначе разница 20."""
    win = "S" if us > them else "O"
    pts, why = 0, []
    try:
        gf, ga = int(pk.get("gf")), int(pk.get("ga"))
    except (TypeError, ValueError):
        return 0, []
    if pk.get("w") == win:
        pts += 100
        why.append("победитель +100")
    if gf == us and ga == them:
        pts += 50
        why.append("точный счёт +50")
    elif pk.get("w") == win and gf - ga == us - them:
        pts += 20
        why.append("разница +20")
    return pts, why


def final_whistle(d, g, us, them, suffix, scorers):
    """Матч окончен: итог всем, предварительные очки участникам, голосование за лучшего игрока."""
    line = score_line(g, us, them) + (f" ({suffix})" if suffix else "")
    mood = "Победа «Салавата»! 🎉" if us > them else "Поражение. Играем дальше."
    names = load("names")
    scored = []
    for uid, v in load("game").items():
        pk = v.get("picks", {}).get(d)
        if pk:
            pts, why = mgr_points(pk, us, them)
            scored.append((uid, pk, pts, why))
    scored.sort(key=lambda r: -r[2])
    top = "\n".join(f"{'🥇🥈🥉'[i]} {names.get(u, '') or 'Болельщик'} — {p} {ru_pts(p)}" for i, (u, _, p, _) in enumerate(scored[:3]) if p > 0)
    text = f"🏁 Матч окончен!\n{line}\n{mood}"
    push(text, groups=False)
    group_push(text + (f"\n\nЛучшие прогнозы на счёт:\n{top}" if top else ""), reply_markup=kb_url("🏆 Рейтинг и прогнозы"))
    for rank, (uid, pk, pts, why) in enumerate(scored, 1):
        mine = f"{pk.get('gf')}:{pk.get('ga')}" if g.get("home") else f"{pk.get('ga')}:{pk.get('gf')}"
        msg = (f"🎯 Твой прогноз {mine}: генменеджер — {pts} {ru_pts(pts)}"
               + (f" ({', '.join(why)})" if why else "") + f".\nПо счёту ты {rank}-й из {len(scored)}.\n"
               "Очки тренера и агента придут утром, когда появится протокол матча.")
        r = tg("sendMessage", chat_id=int(uid), text=msg, reply_markup=kb("Моя игра", "#game"))
        if r and r.get("error_code") == 403:
            set_sub(uid, False)
        time.sleep(0.05)
    cands = list(dict.fromkeys(scorers))[:6] + ["🧤 Вратарь «Салавата»"]
    with LOCK:
        load("mvp")[d] = {"c": cands, "v": {}, "ts": int(time.time()), "o": g["o"]}
        save("mvp")
    push("⭐ Кто лучший игрок «Салавата» в этом матче? Голосуй — итог покажу в приложении.",
         silent=True, reply_markup=mvp_markup(d, cands))


def bot_update(u):
    """Ответ на сообщение боту — сразу в ответе вебхука, без лишних запросов."""
    if u.get("callback_query"):
        return mvp_vote(u["callback_query"])
    cm = u.get("my_chat_member")
    if cm and cm.get("chat", {}).get("type") == "private":
        st = cm.get("new_chat_member", {}).get("status")
        set_sub(str(cm["chat"]["id"]), st == "member")
        return None
    if cm and cm.get("chat", {}).get("type") in ("group", "supergroup"):
        st = cm.get("new_chat_member", {}).get("status")
        cid = str(cm["chat"]["id"])
        on = st in ("member", "administrator")
        with LOCK:
            gr = load("groups")
            was = gr.get(cid, {}).get("on")
            gr[cid] = {"on": on, "title": (cm["chat"].get("title") or "")[:80], "ts": int(time.time())}
            save("groups")
        if on and not was:
            return {"method": "sendMessage", "chat_id": cm["chat"]["id"],
                    "text": ("🏒 Привет, болельщики! Я «Звенья Салавата».\n"
                             "Буду вести здесь матчи «Салавата»: начало, голы, периоды, итог и лучшие прогнозы.\n"
                             "Рейтинг прогнозистов — /table. Свой прогноз делай в приложении 👇"),
                    "reply_markup": kb_url()}
        return None
    m = u.get("message") or {}
    chat = m.get("chat") or {}
    if chat.get("type") in ("group", "supergroup"):
        text = (m.get("text") or "").strip()
        cmd = text.split()[0].split("@")[0].lower() if text else ""
        cid = str(chat["id"])
        if cmd and cid not in load("groups"):
            with LOCK:
                load("groups")[cid] = {"on": True, "title": (chat.get("title") or "")[:80], "ts": int(time.time())}
                save("groups")
        if cmd in ("/table", "/top"):
            return {"method": "sendMessage", "chat_id": chat["id"], "text": table_text(), "reply_markup": kb_url()}
        if cmd == "/start":
            return {"method": "sendMessage", "chat_id": chat["id"],
                    "text": "🏒 Я веду здесь матчи «Салавата» и считаю прогнозы. Рейтинг — /table.", "reply_markup": kb_url()}
        return None
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
        return {"method": "sendMessage", "chat_id": chat["id"], "text": WELCOME, "parse_mode": "HTML", "reply_markup": kb("🏒 ИГРАТЬ")}
    if cmd == "/admin" and uid == owner_id():
        with LOCK:
            if not load("owner").get("id"):
                load("owner")["id"] = uid
                save("owner")
        return {"method": "sendMessage", "chat_id": chat["id"], "text": admin_text()}
    if cmd in ("/table", "/top"):
        return {"method": "sendMessage", "chat_id": chat["id"], "text": table_text(), "reply_markup": kb("Моя игра", "#game")}
    if cmd == "/goals":
        on = not load("subs").get(uid, {}).get("goals", True)
        set_goals(uid, on)
        msg = "⚡ Матч онлайн включён: напишу о начале матча, каждого периода и овертайма и о каждом изменении счёта." if on else \
            "Матч онлайн выключен: во время матчей писать не буду. Включить снова — /goals."
        return {"method": "sendMessage", "chat_id": chat["id"], "text": msg}
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
                    if kind == "day":
                        group_push(text, reply_markup=kb_url("🎯 Сделать прогноз"))
        except Exception as e:
            print("напоминания:", e, file=sys.stderr)
        try:
            announce()
        except Exception as e:
            print("итоги:", e, file=sys.stderr)
        try:
            razbor_tick(time.time())
        except Exception as e:
            print("разбор:", e, file=sys.stderr)
        try:
            alerts_tick(time.time())
        except Exception as e:
            print("тревоги:", e, file=sys.stderr)
        time.sleep(60)


def alerts_tick(now):
    """Новые тревоги (alerts.json готовит GitHub из приложения) — одним сообщением владельцу, с 9:00 до 22:00 по Уфе.
    Ключ тревоги содержит дату начала серии, поэтому об одной и той же серии бот пишет один раз."""
    if not TOKEN:
        return False
    try:
        with open(ALERTS, encoding="utf8") as f:
            a = json.load(f)
    except (FileNotFoundError, ValueError):
        return False
    t = datetime.fromtimestamp(now, UFA)
    try:
        age = (t.date() - datetime.strptime(a.get("d") or "", "%Y-%m-%d").date()).days
    except ValueError:
        return False
    if age < 0 or age > 3 or t.hour < 9 or t.hour >= 22:
        return False
    owner = owner_id()
    sent = load("sent")
    new = [x for x in a.get("items", []) if x.get("k") and x.get("text") and not sent.get("al:" + x["k"])]
    if not owner or not new:
        return False
    with LOCK:
        for x in new:
            sent["al:" + x["k"]] = int(now)
        save("sent")
    tg("sendMessage", chat_id=int(owner), text="⚠ Тревоги «Звеньев Салавата»\n" + "\n".join("• " + x["text"] for x in new),
       reply_markup=kb("Открыть «Форму»", "#form"))
    return True


def razbor_tick(now):
    """Утром после матча — разбор в Telegram (тем, у кого включён «Матч онлайн», и в чаты болельщиков).
    Только вчерашний или сегодняшний матч, с 9:00 до 22:00 по Уфе. Ждёт полный протокол игроков до 13:00,
    потом шлёт то, что есть. Один раз на матч."""
    if not TOKEN:
        return False
    try:
        with open(RAZBOR, encoding="utf8") as f:
            r = json.load(f)
    except (FileNotFoundError, ValueError):
        return False
    d, text = r.get("d"), r.get("text")
    if not d or not text:
        return False
    t = datetime.fromtimestamp(now, UFA)
    try:
        age = (t.date() - datetime.strptime(d, "%Y-%m-%d").date()).days
    except ValueError:
        return False
    if age < 0 or age > 1 or t.hour < 9 or t.hour >= 22 or (not r.get("full") and t.hour < 13):
        return False
    sent = load("sent")
    key = d + "razbor"
    if sent.get(key):
        return False
    with LOCK:
        sent[key] = int(now)
        save("sent")
    push(text, groups=False, reply_markup=kb("📊 Открыть разбор", "#razbor"))
    group_push(text, reply_markup=kb_url("📊 Открыть разбор", "razbor"))
    return True


# ---------- псевдонимы: в открытой выдаче для GitHub нет ни id, ни имён
import secrets


def pid_of(uid):
    with LOCK:
        pids = load("pids")
        if uid not in pids:
            taken = set(pids.values())
            while True:
                x = secrets.token_hex(5)
                if x not in taken:
                    break
            pids[uid] = x
            save("pids")
        return pids[uid]


def uid_by_pid():
    return {v: k for k, v in load("pids").items()}


def public_seal():
    """Закрытые прогнозы последних 60 дней для подсчёта очков на GitHub."""
    out = {}
    cut = time.time() - 60 * 86400
    cal = calendar()
    for uid, v in load("game").items():
        for d, x in v.get("picks", {}).items():
            g = cal.get(d)
            if g and deadline_passed(d) and g["kickoff"] >= cut:
                out.setdefault(d, {})[pid_of(uid)] = {k: x.get(k) for k in ("w", "gf", "ga", "f", "d", "g", "a")}
    return out


# ---------- итоги матча: results.json с GitHub -> сообщения участникам
_res = {"mtime": 0, "data": {}}


def results():
    try:
        m = os.path.getmtime(RESULTS)
    except OSError:
        return _res["data"]
    if m != _res["mtime"]:
        try:
            with open(RESULTS, encoding="utf8") as f:
                _res.update(mtime=m, data=json.load(f))
        except ValueError:
            pass
    return _res["data"]


def ru_pts(n):
    n = abs(int(n))
    return "очко" if n % 10 == 1 and n % 100 != 11 else "очка" if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14 else "очков"


def announce():
    res = results()
    if not res or not (TOKEN and APP):
        return
    by = uid_by_pid()
    names = load("names")
    sent = load("sent")
    today = datetime.now(UFA).date()
    for d, m in sorted(res.items()):
        try:
            age = (today - datetime.strptime(d, "%Y-%m-%d").date()).days
        except ValueError:
            continue
        if age > 3 or sent.get(d + "res") or not m.get("s"):
            continue
        with LOCK:
            sent[d + "res"] = int(time.time())
            save("sent")
        sc = m["s"]
        order = sorted(sc, key=lambda p: -sc[p]["tot"])
        season = {}
        for dd, mm in res.items():
            if dd <= d:
                for p, x in mm.get("s", {}).items():
                    season[p] = season.get(p, 0) + x["tot"]
        sorder = sorted(season, key=lambda p: -season[p])
        line = f"Салават Юлаев {m['gf']}:{m['ga']} {m['o']}" if m.get("h") else f"{m['o']} {m['ga']}:{m['gf']} Салават Юлаев"
        if m.get("x"):
            line += f" ({m['x']})"
        top = order[0]
        top_name = names.get(by.get(top, ""), "") or "Болельщик"
        for p in order:
            uid = by.get(p)
            if not uid:
                continue
            x = sc[p]
            mine = f"{x['gf']}:{x['ga']}" if m.get("h") else f"{x['ga']}:{x['gf']}"
            text = (f"🏁 {line}\n"
                    f"Твой прогноз {mine} — {x['tot']} {ru_pts(x['tot'])} "
                    f"(генменеджер {x['mgr']}, тренер {x['coach']}, агент {x['agent']}).\n"
                    f"За матч: {order.index(p) + 1}-е место из {len(order)}. "
                    f"В сезоне: {sorder.index(p) + 1}-е место, {season[p]} {ru_pts(season[p])}.")
            if p != top:
                text += f"\nЛучший за матч — {top_name}: {sc[top]['tot']} {ru_pts(sc[top]['tot'])}."
            else:
                text += "\n🥇 Ты лучший за матч!"
            r = tg("sendMessage", chat_id=int(uid), text=text, reply_markup=kb("Рейтинг и разбор очков", "#game"))
            if r and r.get("error_code") == 403:
                set_sub(uid, False)
            time.sleep(0.05)
        best = "\n".join(f"{'🥇🥈🥉'[i]} {names.get(by.get(p, ''), '') or 'Болельщик'} — {sc[p]['tot']} {ru_pts(sc[p]['tot'])}"
                         for i, p in enumerate(order[:3]))
        mv = mvp_tally(d)
        star = f"\n\n⭐ Лучший игрок по версии болельщиков: {mv['c'][0]['name']} ({mv['c'][0]['n']} из {mv['total']})" if mv and mv["total"] else ""
        group_push(f"📊 Очки за матч подсчитаны\n{line}\n\n{best}{star}\n\n{table_text()}", reply_markup=kb_url("🏆 Рейтинг и прогнозы"))


# ---------- лиги с друзьями
def my_leagues(uid):
    return [{"id": k, "name": v["name"], "members": v["members"], "owner": v["owner"] == uid}
            for k, v in load("leagues").items() if uid in v["members"]]


BOT_NAME = {"v": ""}


def bot_name():
    if not BOT_NAME["v"] and TOKEN:
        r = tg("getMe") or {}
        BOT_NAME["v"] = (r.get("result") or {}).get("username", "")
    return BOT_NAME["v"]


# ---------- голы онлайн: текстовая трансляция Sports.ru (страница матча отдаётся обычным HTML)
import html as _html

SR = "https://www.sports.ru"
UA = {"User-Agent": "Mozilla/5.0 (compatible; zvenya-salavata/1.0)", "Accept-Language": "ru"}
MONTHS = {"января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6, "июля": 7,
          "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12}
SURNAME = r"[А-ЯЁA-Z][а-яёa-zA-Z'\-]+(?: [А-ЯЁA-Z][а-яёa-zA-Z'\-]+)?"


def fetch(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf8", "replace")


def text_lines(page):
    page = re.sub(r"(?is)<(script|style|noscript)\b.*?</\1>", " ", page)
    page = re.sub(r"(?s)<[^>]+>", "\n", page)
    return [x for x in (re.sub(r"\s+", " ", _html.unescape(l)).strip() for l in page.split("\n")) if x]


def our_surnames():
    try:
        with open(PAGE, encoding="utf8") as f:
            row = re.search(r"^const RAW=(\[.*?\n\]);", f.read(), re.M | re.S)
        return {r[1].split()[-1] for r in json.loads(row.group(1))}
    except Exception:
        return set()


def parse_goals(page):
    """Голы из текста страницы: [(секунда матча, автор, [ассистенты])], по времени, без повторов."""
    L = text_lines(page)
    out = []
    for i, x in enumerate(L):
        if not re.fullmatch(r"Гол!?", x):
            continue
        t = None
        for j in range(max(0, i - 4), i):
            m = re.fullmatch(r"(\d{1,3}):(\d{2})", L[j])
            if m:
                t = int(m.group(1)) * 60 + int(m.group(2))
        if t is None or i + 1 >= len(L) or not re.fullmatch(SURNAME, L[i + 1]):
            continue
        who = L[i + 1]
        ast = []
        if i + 2 < len(L) and re.fullmatch(SURNAME + r"(?:, " + SURNAME + r")?", L[i + 2]):
            ast = [a.strip() for a in L[i + 2].split(",")]
        if any(o[1] == who and abs(o[0] - t) <= 30 for o in out):
            continue
        out.append((t, who, ast))
    return sorted(out)


def page_match(page):
    """Дата и есть ли «Салават» на странице матча."""
    txt = " ".join(text_lines(page)[:400])
    m = re.search(r"(\d{1,2}) (" + "|".join(MONTHS) + r") (\d{4})", txt)
    d = f"{m.group(3)}-{MONTHS[m.group(2)]:02d}-{int(m.group(1)):02d}" if m else ""
    return d, "Салават" in txt, txt


def sr_match_id(d, opp):
    """Номер матча на Sports.ru: ищем в календаре клуба, проверяем дату и соперника, запоминаем."""
    ids = load("srids")
    if d in ids:
        return ids[d]
    cal = fetch(SR + "/hockey/club/salavat/calendar/")
    seen = load("srseen")
    for mid in dict.fromkeys(re.findall(r"/hockey/match/(\d+)/", cal)):
        if mid in seen:
            continue
        try:
            pd, sal, txt = page_match(fetch(f"{SR}/hockey/match/{mid}/"))
        except Exception:
            continue
        with LOCK:
            seen[mid] = pd
            save("srseen")
            if sal and pd:
                ids.setdefault(pd, mid)
                save("srids")
        if pd == d and sal and opp.split()[0] in txt:
            return mid
        time.sleep(1)
    return ids.get(d)


def sr_goals_tick(d, g, now):
    """Запасной путь: голы по трансляции Sports.ru (если Спорт-Экспресс недоступен)."""
    mid = sr_match_id(d, g["o"])
    if not mid:
        return
    goals = parse_goals(fetch(f"{SR}/hockey/match/{mid}/"))
    ours = our_surnames()
    sent = load("sent")
    key = d + "goals"
    done = sent.get(key)
    if done is None:  # первый раз видим матч: если он давно идёт, старые голы не шлём
        done = [f"{t}|{w}" for t, w, _ in goals] if now - g["kickoff"] > 900 else []
    us = them = 0
    feed = []
    for t, who, ast in goals:
        mine = who.split()[-1] in ours
        us, them = (us + 1, them) if mine else (us, them + 1)
        feed.append({"t": t, "who": who, "mine": mine, "us": us, "them": them})
        k = f"{t}|{who}"
        if k in done:
            continue
        done.append(k)
        head = "🚨 ГОЛ «САЛАВАТА»!" if mine else f"Гол {g['o']}"
        push(f"{head}\n{score_line(g, us, them)}\n🏒 {who}{' (' + ', '.join(ast) + ')' if ast else ''}, {t // 60}:{t % 60:02d}", silent=not mine)
    with LOCK:
        sent[key] = done
        save("sent")
    live_set(d, g, now, us, them, LIVE.get("period", 0) if LIVE.get("d") == d else 0, feed)


# ---------- матч онлайн: счёт и периоды со страницы матча «Спорт-Экспресса» (обычный HTML)
SE = "https://www.sport-express.net"
SE_SCHEDULE = SE + "/tag/salavat-yulaev-11/schedule/"
SE_WORD = r"[А-ЯЁA-Z][А-Яа-яЁёA-Za-z'\.\-]*"
SE_WHO = SE_WORD + r"(?: " + SE_WORD + r"){0,3}"
SE_KIND = r"(?i:гол!?|штраф)"
# время, игрок, «ГОЛ!» или «штраф»; после гола — счёт (но не время следующего события)
SE_EV = re.compile(r"(?<![\d:])(\d{1,3}):(\d{2})\s+(" + SE_WHO + r")\s+(" + SE_KIND + r")"
                   r"(?:\s+(\d{1,2})\s*:\s*(\d{1,2})(?![\d:])(?!\s+" + SE_WHO + r"\s+" + SE_KIND + r"))?"
                   r"(?:\s*[-–—]\s*([а-яё][а-яё ,\.\-]*?)(?=\s*(?:\d|$|[А-ЯЁ])))?")
SE_PER = re.compile(r"(?<![\d:])([1-3])(?:-й)?\s+период\s+\d{1,2}\s*:\s*\d{1,2}(?![\d:])", re.I)
SE_OT = re.compile(r"(?<![а-яё])(?:овертайм|ОТ)\s+\d{1,2}\s*:\s*\d{1,2}(?![\d:])", re.I)
SE_SO = re.compile(r"(?<![а-яё])(?:буллиты|серия буллитов|послематчевые буллиты)\s+\d{1,2}\s*:\s*\d{1,2}(?![\d:])", re.I)
PERIOD_NAME = {1: "1-й период", 2: "2-й период", 3: "3-й период", 4: "Овертайм", 5: "Буллиты"}
LIVE = {"on": False}
_se_try = {}


def parse_se(page):
    """Страница матча «Спорт-Экспресса» → период (0 — не начался, 1–3, 4 — овертайм, 5 — буллиты)
    и голы по времени: [(секунда матча, автор, счёт хозяев, счёт гостей)]."""
    txt = " ".join(text_lines(page))
    period = 0
    for m in SE_PER.finditer(txt):
        period = max(period, int(m.group(1)))
    goals, pens = [], []
    for m in SE_EV.finditer(txt):
        t = int(m.group(1)) * 60 + int(m.group(2))
        period = max(period, 1 if t <= 1200 else 2 if t <= 2400 else 3 if t <= 3600 else 4)
        if m.group(4).lower().startswith("гол") and m.group(5) is not None:
            row = (t, m.group(3), int(m.group(5)), int(m.group(6)))
            if row not in goals:
                goals.append(row)
        elif m.group(4).lower() == "штраф":
            row = (t, m.group(3), (m.group(7) or "").strip(" .,-"))
            if row[:2] not in [x[:2] for x in pens]:
                pens.append(row)
    goals.sort(key=lambda r: (r[0], r[2] + r[3]))
    pens.sort()
    if SE_OT.search(txt):
        period = max(period, 4)
    if SE_SO.search(txt):
        period = 5
    return {"period": period, "goals": goals, "pens": pens, "ours": "Салават" in txt}


def se_state(page, mid):
    """Статус и счёт нашего матча из данных страницы: code — not-started / finished / идёт, счёт, овертаймы."""
    for m in re.finditer(r'"id":%s,"date":"' % mid, page):
        seg = page[m.start():m.start() + 4000]
        nxt = re.search(r'"id":\d+,"date":"', seg[20:])
        if nxt:
            seg = seg[:nxt.start() + 20]
        st = re.search(r'"status":\{"code":"([a-z\-]+)"', seg)
        sc = re.search(r'"homeScore":(\d+),"guestScore":(\d+),"scoreType":"([^"]*)","overtime":(\d+)', seg)
        if st:
            return {"code": st.group(1), "home": int(sc.group(1)) if sc else None, "guest": int(sc.group(2)) if sc else None,
                    "type": sc.group(3) if sc else "", "ot": int(sc.group(4)) if sc else 0}
    return None


def se_match_id(d, opp):
    """Номер матча в матч-центре «Спорт-Экспресса»: строка расписания клуба с нужной датой и соперником."""
    ids = load("seids")
    if d in ids:
        return ids[d]
    if time.time() - _se_try.get(d, 0) < 300:  # расписание не дёргаем чаще раза в 5 минут
        return None
    _se_try[d] = time.time()
    page = fetch(SE_SCHEDULE)
    stamp = f"{d[8:10]}.{d[5:7]}.{d[:4]}"
    for part in page.split(stamp)[1:]:
        nxt = re.search(r"\d{2}\.\d{2}\.\d{4}", part)
        row = part[:nxt.start()] if nxt else part[:6000]
        m = re.search(r"matchcenter/(\d+)", row)
        if not m or opp.split()[0] not in " ".join(text_lines(row)):
            continue
        pd, sal, _ = page_match(fetch(f"{SE}/hockey/L/matchcenter/{m.group(1)}/"))
        if pd == d and sal:
            with LOCK:
                ids[d] = m.group(1)
                save("seids")
            return m.group(1)
    return None


def score_line(g, us, them):
    return f"Салават Юлаев {us}:{them} {g['o']}" if g.get("home") else f"{g['o']} {them}:{us} Салават Юлаев"


def push(text, silent=False, groups=True, **extra):
    """Сообщение всем, у кого включён «Матч онлайн» (включён по умолчанию, выключается /goals), и в чаты болельщиков.
    Шлёт в 4 потока (до ~25 сообщений в секунду, лимит Telegram — 30), чтобы последний подписчик не ждал минуту.
    Возвращает [(чат, номер сообщения)]."""
    uids = [uid for uid, sb in list(load("subs").items()) if sb.get("on") and sb.get("goals", True)]

    def one(uid):
        r = tg("sendMessage", chat_id=int(uid), text=text, disable_notification=silent, **extra)
        if r and r.get("error_code") == 403:
            set_sub(uid, False)
        time.sleep(0.05)
        mid = ((r or {}).get("result") or {}).get("message_id")
        return [int(uid), mid] if mid else None

    with ThreadPoolExecutor(max_workers=4) as ex:
        out = [x for x in ex.map(one, uids) if x]
    if groups:
        out += group_push(text, silent=silent, **extra)
    return out


def goal_text(g, head, us, them, who, t, ast):
    return f"{head}\n{score_line(g, us, them)}\n🏒 {who}{' (' + ', '.join(ast) + ')' if ast else ''}, {t // 60}:{t % 60:02d}"


def assists_tick(d, g, st, now):
    """Голы, у которых ещё нет передач: раз в 20 секунд спрашиваем Sports.ru и дописываем передачи в уже
    отправленные сообщения (сам гол уходит сразу, не дожидаясь их). Через 10 минут перестаём искать."""
    keep = []
    for p in st.get("pend", []):
        if now - p["t0"] > 600:
            continue
        if now - p.get("nt", 0) < 20:
            keep.append(p)
            continue
        p["nt"] = now
        ast = sr_assists(d, g, p["t"], p["who"])
        if not ast:
            keep.append(p)
            continue
        text = goal_text(g, p["head"], p["us"], p["them"], p["who"], p["t"], ast)
        for cid, mid in p["msgs"]:
            tg("editMessageText", chat_id=cid, message_id=mid, text=text)
            time.sleep(0.03)
    st["pend"] = keep


def live_set(d, g, now, us, them, period, feed):
    LIVE.clear()
    LIVE.update(on=True, d=d, o=g["o"], home=bool(g.get("home")), us=us, them=them, period=period,
                goals=feed[-12:], kickoff=int(g["kickoff"]),
                fin=bool(load("sent").get(d + "live", {}).get("fin")) or now > g["kickoff"] + 3 * 3600, ts=int(now))


def sr_assists(d, g, t, who):
    """Передачи к голу из трансляции Sports.ru, если она уже успела написать о нём."""
    try:
        mid = sr_match_id(d, g["o"])
        if mid:
            for st, sw, ast in parse_goals(fetch(f"{SR}/hockey/match/{mid}/")):
                if abs(st - t) <= 90 and sw.split()[-1] == who.split()[-1]:
                    return ast
    except Exception as e:
        print("передачи:", e, file=sys.stderr)
    return []


def live_tick(now):
    d = datetime.fromtimestamp(now, UFA).strftime("%Y-%m-%d")
    g = calendar().get(d)
    if not (g and g["kickoff"] - 300 <= now <= g["kickoff"] + 4 * 3600):
        LIVE.clear()
        LIVE["on"] = False
        return False
    sent = load("sent")
    st = sent.get(d + "live")
    late = st is None and now - g["kickoff"] > 900  # сервер запустили посреди матча: старое не рассылаем
    if st is None:
        st = {"kick": False, "p": 0, "goals": [], "src": "", "down": 0}
    st.setdefault("pens", [])
    st.setdefault("pend", [])
    teams = f"Салават Юлаев — {g['o']}" if g.get("home") else f"{g['o']} — Салават Юлаев"
    if not st["kick"] and now >= g["kickoff"]:
        st["kick"] = True
        if not late:
            push(f"🏒 Матч начинается!\n{teams}")
    se = None
    try:
        mid = se_match_id(d, g["o"])
        if mid:
            page = fetch(f"{SE}/hockey/L/matchcenter/{mid}/")
            se = parse_se(page)
            if not se["ours"]:
                se = None
            else:
                se["state"] = se_state(page, mid)
    except Exception as e:
        print("матч онлайн:", e, file=sys.stderr)
    if se and now >= g["kickoff"] - 60:
        home = bool(g.get("home"))
        rows = []  # (ключ, секунда, автор, наш ли гол, наши, их)
        ph = pa = 0
        for t, who, h, a in se["goals"]:
            mine = (h > ph) == home if (h > ph) != (a > pa) else None
            ph, pa = h, a
            us, them = (h, a) if home else (a, h)
            rows.append((f"{h}:{a}", t, who, mine, us, them))
        if st["src"] != "sr":
            st["src"] = "se"
        if se["period"] > st["p"]:
            p = se["period"]
            st["p"] = p
            if not late:
                before = [r for r in rows if r[1] <= (p - 1) * 1200] if p < 5 else rows
                us, them = (before[-1][4], before[-1][5]) if before else (0, 0)
                head = {4: "⏱ Начался овертайм!", 5: "🎯 Серия буллитов!"}.get(p, f"▶️ Начался {p}-й период")
                push(f"{head}\n{score_line(g, us, them)}")
        if st["src"] == "se":
            keys = [r[0] for r in rows]
            gone = [k for k in st["goals"] if k not in keys]
            if gone and se["period"]:
                st["down"] = st.get("down", 0) + 1
                if st["down"] >= 2:  # гол пропал со страницы два опроса подряд — его отменили
                    st["goals"] = [k for k in st["goals"] if k in keys]
                    st["down"] = 0
                    us, them = (rows[-1][4], rows[-1][5]) if rows else (0, 0)
                    push(f"❌ Гол отменён\n{score_line(g, us, them)}")
            else:
                st["down"] = 0
            for k, t, who, mine, us, them in rows:
                if k in st["goals"]:
                    continue
                st["goals"].append(k)
                if late:
                    continue
                ot = " В ОВЕРТАЙМЕ" if t > 3600 else ""
                head = (f"🚨 ГОЛ «САЛАВАТА»{ot}!" if mine else f"Гол {g['o']}{ot.lower()}" if mine is False else f"Гол{ot.lower()}!")
                # гол уходит сразу; передачи допишем в это же сообщение, когда их опубликуют
                msgs = push(goal_text(g, head, us, them, who, t, []), silent=mine is False)
                st["pend"].append({"t": t, "who": who, "head": head, "us": us, "them": them, "msgs": msgs, "t0": now})
        # удаления обеих команд
        ours = our_surnames()
        for t, who, why in se.get("pens", []):
            k = f"{t}|{who}"
            if k in st["pens"]:
                continue
            st["pens"].append(k)
            if late:
                continue
            mine = who.split()[-1] in ours if ours else None
            team = " («Салават Юлаев»)" if mine else f" ({g['o']})" if mine is False else ""
            push(f"⛔ Удаление{team}\n{who}{' — ' + why if why else ''}, {t // 60}:{t % 60:02d}", silent=mine is False)
        if st["pend"]:
            assists_tick(d, g, st, now)
        us, them = (rows[-1][4], rows[-1][5]) if rows else (0, 0)
        stt = se.get("state") or {}
        if stt.get("code") == "finished" and not st.get("fin") and st["src"] == "se":
            st["fin"] = True
            if stt.get("home") is not None:
                us, them = (stt["home"], stt["guest"]) if home else (stt["guest"], stt["home"])
            with LOCK:
                sent[d + "live"] = st
                save("sent")
            if not late and us != them:
                suffix = "Б" if se["period"] == 5 or "bul" in stt.get("type", "").lower() else "ОТ" if se["period"] == 4 or stt.get("ot") else ""
                final_whistle(d, g, us, them, suffix, [r[2] for r in rows if r[3]])
        live_set(d, g, now, us, them, se["period"],
                 [{"t": r[1], "who": r[2], "mine": r[3], "us": r[4], "them": r[5]} for r in rows])
    elif not se and st["src"] != "se" and now > g["kickoff"] + 600:
        st["src"] = "sr"  # «Спорт-Экспресс» не отвечает с начала матча — голы берём со Sports.ru
    with LOCK:
        sent[d + "live"] = st
        save("sent")
    if st["src"] == "sr":
        sr_goals_tick(d, g, now)
    elif not se and not LIVE.get("on") and now >= g["kickoff"]:
        live_set(d, g, now, 0, 0, 0, [])
    return True


def live_loop():
    """Во время матча раз в 10 секунд читает страницу матча и рассылает начало периодов и голы."""
    while True:
        on = False
        try:
            on = bool(TOKEN) and live_tick(time.time())
        except Exception as e:
            print("матч онлайн:", e, file=sys.stderr)
        time.sleep(10 if on else 60)  # во время матча — раз в 10 секунд


def set_goals(uid, on):
    with LOCK:
        subs = load("subs")
        sb = subs.setdefault(uid, {"on": True, "ts": int(time.time())})
        sb["goals"] = on
        if on:
            sb["on"] = True
        save("subs")


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
        if p[:3] == ["api", "public", "seal"]:
            return self.send(200, public_seal())
        if p[:3] == ["api", "public", "mvp"]:
            mv = load("mvp")
            return self.send(200, (mvp_tally(max(mv)) if mv else None) or {})
        if p[:3] == ["api", "public", "live"]:
            return self.send(200, dict(LIVE))
        u = self.user()
        if not u:
            return self.send(401, {"error": "нет подписи Телеграма"})
        if p[:2] == ["api", "me"]:
            return self.send(200, {"id": u["id"], "name": u["name"], "sub": bool(load("subs").get(u["id"], {}).get("on")), "goals": bool(load("subs").get(u["id"], {}).get("goals", True))})
        if p[:2] == ["api", "leagues"]:
            return self.send(200, {"leagues": my_leagues(u["id"]), "bot": bot_name()})
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
                    pid_of(i)
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
        if p[:2] == ["api", "league"] and len(p) == 3:
            try:
                b = self.body()
            except ValueError as e:
                return self.send(400, {"error": str(e)})
            with LOCK:
                lg = load("leagues")
                if p[2] == "create":
                    name = re.sub(r"\s+", " ", str(b.get("name") or "")).strip()[:40]
                    if len(name) < 2:
                        return self.send(400, {"error": "Придумай название"})
                    if sum(1 for v in lg.values() if v["owner"] == u["id"]) >= 10:
                        return self.send(409, {"error": "Можно создать не больше 10 лиг"})
                    lid = secrets.token_hex(3)
                    while lid in lg:
                        lid = secrets.token_hex(3)
                    lg[lid] = {"name": name, "owner": u["id"], "members": [u["id"]], "ts": int(time.time())}
                    save("leagues")
                    return self.send(200, {"id": lid, "leagues": my_leagues(u["id"])})
                lid = str(b.get("id") or "")
                if lid not in lg:
                    return self.send(404, {"error": "Лига не найдена"})
                mem = lg[lid]["members"]
                if p[2] == "join":
                    if u["id"] not in mem:
                        if len(mem) >= 300:
                            return self.send(409, {"error": "В лиге уже 300 участников"})
                        mem.append(u["id"])
                        save("leagues")
                    return self.send(200, {"ok": True, "leagues": my_leagues(u["id"])})
                if p[2] == "leave":
                    if u["id"] in mem:
                        mem.remove(u["id"])
                        if not mem:
                            del lg[lid]
                        elif lg[lid]["owner"] == u["id"]:
                            lg[lid]["owner"] = mem[0]
                        save("leagues")
                    return self.send(200, {"ok": True, "leagues": my_leagues(u["id"])})
            return self.send(404, {"error": "нет такого адреса"})
        if p[:2] == ["api", "subscribe"]:
            try:
                b = self.body()
            except ValueError as e:
                return self.send(400, {"error": str(e)})
            if "goals" in b:
                set_goals(u["id"], bool(b.get("goals")))
            if "on" in b:
                set_sub(u["id"], bool(b.get("on")))
            sb = load("subs").get(u["id"], {})
            return self.send(200, {"ok": True, "sub": bool(sb.get("on")), "goals": bool(sb.get("goals", True))})
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


if __name__ == "__main__" and len(sys.argv) == 3 and sys.argv[1] == "--probe-se":
    # проверка разбора «Спорт-Экспресса»: python3 api.py --probe-se 129367
    pg = fetch(f"{SE}/hockey/L/matchcenter/{sys.argv[2]}/")
    r = parse_se(pg)
    print("страница:", page_match(pg)[:2], "| период:", PERIOD_NAME.get(r["period"], "не начался"))
    for t, w, h, a in r["goals"]:
        print(f"{t // 60}:{t % 60:02d}", w, f"{h}:{a}")
    sys.exit(0)

if __name__ == "__main__" and len(sys.argv) == 3 and sys.argv[1] == "--probe":
    # проверка разбора трансляции: python3 api.py --probe 1874359
    pg = fetch(f"{SR}/hockey/match/{sys.argv[2]}/")
    print("страница:", page_match(pg)[:2])
    for t, w, a in parse_goals(pg):
        print(f"{t // 60}:{t % 60:02d}", w, a)
    sys.exit(0)

if __name__ == "__main__":
    if not TOKEN:
        print("нет BOT_TOKEN — запись и чтение работать не будут", file=sys.stderr)
    threading.Thread(target=watch_self, daemon=True).start()
    threading.Thread(target=bot_setup, daemon=True).start()
    threading.Thread(target=reminders, daemon=True).start()
    threading.Thread(target=live_loop, daemon=True).start()
    print(f"api на 127.0.0.1:{PORT}, матчей в календаре: {len(calendar())}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
