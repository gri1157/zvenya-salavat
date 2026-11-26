#!/usr/bin/env python3
"""Проверка «Матча онлайн» без сети: python3 .github/server/test_live.py

Лента событий — как на странице матч-центра «Спорт-Экспресса» (матч 16.11.2026, «Салават Юлаев» — «Адмирал», 6:5).
Матч проигрывается по минутам, проверяются сообщения бота и ответ /api/public/live.
"""
import os
import sys
import tempfile

os.environ["ZV_DATA"] = tempfile.mkdtemp()
os.environ["BOT_TOKEN"] = "test"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import api  # noqa: E402

EVENTS = [  # (секунда матча, имя, тип, счёт после гола)
    (830, "Данил Алалыкин", "ГОЛ!", "1 : 0"), (950, "Владислав Ефремов", "штраф", ""), (1081, "Артем Пименов", "штраф", ""),
    (1147, "Илья Морозов", "штраф", ""), (1194, "Александр Жаровский", "ГОЛ!", "2 : 0"),
    (1276, "Александр Жаровский", "ГОЛ!", "3 : 0"), (1638, "Дмитрий Завгородний", "ГОЛ!", "3 : 1"), (1778, "Артем Пименов", "штраф", ""),
    (2125, "Ярослав Цулыгин", "штраф", ""),
    (2418, "Александр Волков", "штраф", ""), (2594, "Александр Дарьин", "ГОЛ!", "3 : 2"), (2851, "Семен Ибрагимов", "ГОЛ!", "3 : 3"),
    (3037, "Мэттью Маджо", "ГОЛ!", "4 : 3"), (3078, "Дмитрий Мухтаров", "ГОЛ!", "4 : 4"), (3092, "Владислав Цицюра", "ГОЛ!", "4 : 5"),
    (3136, "Данил Алалыкин", "ГОЛ!", "5 : 5"), (3230, "Ильдан Газимов", "штраф", ""), (3425, "Вадим Шипачев", "ГОЛ!", "6 : 5"),
]


def page(upto, header_only=0, split=False):
    """Страница на секунду матча upto. header_only — период, у которого пока есть только заголовок."""
    ev = [e for e in EVENTS if e[0] <= upto]
    out = ["<html><head><title>Онлайн трансляция Салават Юлаев - Адмирал, 16 ноября 2026, счет 6:5, FONBET КХЛ</title>"
           "<script>var x='99:99 Кто То ГОЛ! 9 : 9'</script></head><body>",
           "<h1>Салават Юлаев - Адмирал. 16 ноября 2026. FONBET КХЛ. Регулярный чемпионат</h1>",
           "<div>Время, дата:17:00, 16.11.2026</div><table><tr><td>Период</td><td>1</td><td>2</td><td>3</td></tr></table>",
           "<a>«Салават Юлаев» обыграл «Адмирал» в овертайме 3:2 в прошлом сезоне</a><ul><li>Все события</li><li>Главные события</li></ul>"]
    score = "0 : 0"
    blocks = []
    for p in (1, 2, 3):
        mine = [e for e in ev if (p - 1) * 1200 < e[0] <= p * 1200]
        if not mine and header_only != p:
            continue
        rows = []
        for t, who, kind, sc in mine:
            score = sc or score
            tm = f"{t // 60}:{t % 60:02d}"
            sc_html = "".join(f"<span>{x}</span>" for x in sc.split()) if split else f"<span>{sc}</span>"
            rows.append(f"<div><span>{tm}</span><a>{who}</a><b>{kind}</b>{sc_html if sc else ''}</div>")
        blocks.append(f"<div><h3>{p} период</h3><span>{score}</span></div>" + "".join(reversed(rows)))
    return "\n".join(out + list(reversed(blocks))) + "</body></html>"


SCHEDULE = ("<table><tr><td>14.11.2026</td><td>Сибирь-Салават Юлаев</td><td><a href='/hockey/L/matchcenter/129350/'>2 : 3</a></td></tr>"
            "<tr><td>16.11.2026</td><td>Регулярный чемпионат</td><td><a>Салават Юлаев</a>-<a>Адмирал</a></td>"
            "<td><a href='https://www.sport-express.net/hockey/L/matchcenter/129367/'>-:-</a></td></tr>"
            "<tr><td>18.11.2026</td><td><a>Салават Юлаев</a>-<a>Барыс</a></td><td><a href='/hockey/L/matchcenter/129376/'>-:-</a></td></tr></table>")

KICK = 1794837600  # 16.11.2026 17:00 по Москве
state = {"page": page(0), "se_down": False}
msgs = []


def fake_fetch(url):
    if "sports.ru" in url:
        raise OSError("sports.ru недоступен")
    if state["se_down"]:
        raise OSError("sport-express недоступен")
    if url == api.SE_SCHEDULE:
        return SCHEDULE
    assert url.endswith("/matchcenter/129367/"), url
    return state["page"]


api.fetch = fake_fetch
_our_surnames = api.our_surnames
api.our_surnames = lambda: {"Алалыкин", "Жаровский", "Маджо", "Шипачев", "Пименов", "Газимов"}
api.tg = lambda method, **kw: msgs.append(kw["text"]) or {"ok": True}
api.calendar = lambda: {"2026-11-16": {"o": "Адмирал", "home": True, "kickoff": KICK, "deadline": KICK - 600}}
api._cache["subs"] = {"1": {"on": True, "goals": True}, "2": {"on": True, "goals": False}, "3": {"on": False}}
ok = True


def expect(name, got, want):
    global ok
    good = got == want
    ok = ok and good
    print("✓" if good else "✗", name, "" if good else f"\n   получено: {got}\n   ожидалось: {want}")


def tick(sec, **kw):
    """Опрос на sec секунд после начала; возвращает сообщения этого опроса."""
    del msgs[:]
    api.live_tick(KICK + sec)
    return list(msgs)


# разбор готовой страницы — в обоих вариантах вёрстки счёта
for split in (False, True):
    r = api.parse_se(page(9999, split=split))
    expect(f"разбор: 11 голов, период 3 (split={split})", (len(r["goals"]), r["period"], r["goals"][-1], r["ours"]),
           (11, 3, (3425, "Вадим Шипачев", 6, 5), True))
expect("до матча период 0", api.parse_se(page(0))["period"], 0)

expect("за 4 минуты до начала — тишина", tick(-240), [])
expect("live до начала выключен", api.LIVE.get("on"), None if not api.LIVE else api.LIVE.get("on"))
expect("начало матча", tick(5), ["🏒 Матч начинается!\nСалават Юлаев — Адмирал"])
state["page"] = page(0, header_only=1)
expect("1-й период по заголовку", tick(120), ["▶️ Начался 1-й период\nСалават Юлаев 0:0 Адмирал"])
expect("повторно не шлём", tick(150), [])
state["page"] = page(830)
expect("первый гол", tick(1300), ["🚨 ГОЛ «САЛАВАТА»!\nСалават Юлаев 1:0 Адмирал\n🏒 Данил Алалыкин\n⏱ 13:50 (1-й период)"])
state["page"] = page(1200)
expect("второй гол и удаления обеих команд", tick(1900), ["🚨 ГОЛ «САЛАВАТА»!\nСалават Юлаев 2:0 Адмирал\n🏒 Александр Жаровский\n⏱ 19:54 (1-й период)",
                                                     "⛔ Удаление (Адмирал)\nВладислав Ефремов, 15:50",
                                                     "⛔ Удаление («Салават Юлаев»)\nАртем Пименов, 18:01",
                                                     "⛔ Удаление (Адмирал)\nИлья Морозов, 19:07"])
expect("перерыв — тишина", tick(2500), [])
state["page"] = page(1276)  # заголовка 2-го периода нет, период виден по времени события
expect("2-й период и гол", tick(3200), ["▶️ Начался 2-й период\nСалават Юлаев 2:0 Адмирал",
                                         "🚨 ГОЛ «САЛАВАТА»!\nСалават Юлаев 3:0 Адмирал\n🏒 Александр Жаровский\n⏱ 21:16 (2-й период, 1:16)"])
state["page"] = page(1638)
expect("гол соперника", tick(3600), ["Гол Адмирал\nСалават Юлаев 3:1 Адмирал\n🏒 Дмитрий Завгородний\n⏱ 27:18 (2-й период, 7:18)"])
state["page"] = page(1638, header_only=3)
expect("3-й период по заголовку", tick(5400), ["▶️ Начался 3-й период\nСалават Юлаев 3:1 Адмирал"])
state["page"] = page(3092)
expect("пять голов за один опрос", [m.split("\n")[1] for m in tick(6600)],
       [f"Салават Юлаев {s} Адмирал" for s in ("3:2", "3:3", "4:3", "4:4", "4:5")]
       + ["Артем Пименов, 29:38", "Ярослав Цулыгин, 35:25", "Александр Волков, 40:18"])
state["page"] = page(3078)  # гол 4:5 пропал
expect("отмена: первый опрос ждём", tick(6630), [])
expect("отмена: второй опрос", tick(6660), ["❌ Гол отменён\nСалават Юлаев 4:4 Адмирал"])
state["page"] = page(3425)
expect("после отмены голы приходят снова", [m.split("\n")[1] for m in tick(7000)],
       [f"Салават Юлаев {s} Адмирал" for s in ("4:5", "5:5", "6:5")] + ["Ильдан Газимов, 53:50"])
expect("/api/public/live", {k: api.LIVE[k] for k in ("on", "o", "home", "us", "them", "period", "fin")},
       {"on": True, "o": "Адмирал", "home": True, "us": 6, "them": 5, "period": 3, "fin": False})
state["page"] = page(3425).replace("<h3>3 период</h3>", "<h3>3 период</h3><span>6 : 5</span><h3>Овертайм</h3>")
expect("овертайм по заголовку", tick(8400), ["⏱ Начался овертайм!\nСалават Юлаев 6:5 Адмирал"])
expect("через 4 часа live выключен", (tick(4 * 3600 + 60), api.LIVE), ([], {"on": False}))

# сервер перезапустили посреди матча: старые события не рассылаются
api._cache["sent"] = {}
state["page"] = page(1638)
expect("поздний старт — тишина", tick(3600), [])
state["page"] = page(2594)
expect("поздний старт — дальше как обычно", tick(5500), ["▶️ Начался 3-й период\nСалават Юлаев 3:1 Адмирал",
                                                           "Гол Адмирал\nСалават Юлаев 3:2 Адмирал\n🏒 Александр Дарьин\n⏱ 43:14 (3-й период, 3:14)",
                                                           "⛔ Удаление («Салават Юлаев»)\nАртем Пименов, 29:38",
                                                           "⛔ Удаление (Адмирал)\nЯрослав Цулыгин, 35:25",
                                                           "⛔ Удаление (Адмирал)\nАлександр Волков, 40:18"])
# «Спорт-Экспресс» недоступен: сервер не падает, начало матча всё равно приходит
api._cache["sent"] = {}
api._cache["seids"] = {}
api._se_try.clear()
state["se_down"] = True
expect("источник недоступен — только начало матча", tick(5), ["🏒 Матч начинается!\nСалават Юлаев — Адмирал"])
try:
    got = tick(700)
except OSError:  # запасной путь (Sports.ru) тоже недоступен — цикл сервера это переживает
    got = []
expect("источник недоступен — без ложных сообщений", got, [])

# финальная сирена: итог, предварительные очки, голосование, чат болельщиков
api._cache["sent"] = {}
api._cache["seids"] = {"2026-11-16": "129367"}
api._cache["groups"] = {"-100500": {"on": True, "title": "Фан-чат"}}
api._cache["names"] = {"1": "Гриша", "5": "Петя"}
api._cache["game"] = {"1": {"picks": {"2026-11-16": {"w": "S", "gf": 6, "ga": 5}}},
                      "5": {"picks": {"2026-11-16": {"w": "S", "gf": 3, "ga": 2}}},
                      "7": {"picks": {"2026-11-16": {"w": "O", "gf": 1, "ga": 2}}}}
api._cache["mvp"] = {}
api.BOT_NAME["v"] = "zvenya_salavat_bot"
state["se_down"] = False
sent_to = []
api.tg = lambda method, **kw: (msgs.append(kw["text"]), sent_to.append((kw.get("chat_id"), kw["text"].split("\n")[0], bool(kw.get("reply_markup"))))) and {"ok": True}
JS = ('<script>{"match":{"id":129367,"date":"2026-11-16T17:00:00","score":{"scoreByPeriod":{"periods":[]},"homeScore":6,"guestScore":5,'
      '"scoreType":"","overtime":0,"techResult":"","relative":false},"status":{"code":"%s","name":"x"}},'
      '"todayMatches":{"matches":[{"id":129365,"date":"2026-11-16T19:30:00","score":{"homeScore":1,"guestScore":2,"scoreType":"","overtime":0},"status":{"code":"finished","name":"Матч окончен"}}]}}</script>')
state["page"] = page(3425) + JS % "live"
tick(7000)
expect("чужой «Матч окончен» в боковой колонке не считается финалом", api._cache["sent"]["2026-11-16live"].get("fin"), None)
expect("состояние матча из данных страницы", api.se_state(state["page"], "129367")["code"], "live")
state["page"] = page(3425) + JS % "finished"
del sent_to[:]
got = tick(7100)
expect("финал: итог всем подписанным", [x for x in sent_to if x[1] == "🏁 Матч окончен!"], [(1, "🏁 Матч окончен!", False), (-100500, "🏁 Матч окончен!", True)])
expect("финал: счёт и настроение", got[0].split("\n\n")[0], "🏁 Матч окончен!\nСалават Юлаев 6:5 Адмирал\nПобеда «Салавата»! 🎉")
expect("финал: список шайб — кто забил, счёт и время", got[0].split("\n\n")[1].split("\n")[:3],
       ["Шайбы:", "🏒 1:0 Данил Алалыкин, 13:50", "🏒 2:0 Александр Жаровский, 19:54"])
expect("финал: в чате — лучшие прогнозы", "🥇 Гриша — 150 очков" in got[1] and "🥈 Петя — 120 очков" in got[1], True)
mine = [m for m in got if m.startswith("🎯")]
expect("финал: очки генменеджера каждому", [m.split("\n")[0] for m in mine],
       ["🎯 Твой прогноз 6:5: генменеджер — 150 очков (победитель +100, точный счёт +50).",
        "🎯 Твой прогноз 3:2: генменеджер — 120 очков (победитель +100, разница +20).",
        "🎯 Твой прогноз 1:2: генменеджер — 0 очков."])
expect("финал: голосование с кандидатами-авторами голов", api._cache["mvp"]["2026-11-16"]["c"],
       ["Данил Алалыкин", "Александр Жаровский", "Мэттью Маджо", "Вадим Шипачев", "🧤 Вратарь «Салавата»"])
expect("финал: один раз", tick(7200), [])
r = api.bot_update({"callback_query": {"id": "q1", "from": {"id": 5}, "data": "mvp|2026-11-16|3"}})
expect("голос за лучшего игрока", (r["method"], r["text"]), ("answerCallbackQuery", "Голос принят: Вадим Шипачев.\nЛидирует Вадим Шипачев — 1 из 1"))
api.bot_update({"callback_query": {"id": "q2", "from": {"id": 5}, "data": "mvp|2026-11-16|0"}})
expect("повторный голос заменяет прежний", api.mvp_tally("2026-11-16")["c"][0], {"name": "Данил Алалыкин", "n": 1})
expect("счёт в плашке приложения: матч окончен", (api.LIVE["us"], api.LIVE["them"], api.LIVE["fin"]), (6, 5, True))
r = api.bot_update({"my_chat_member": {"chat": {"id": -200, "type": "supergroup", "title": "Уфа хоккей"}, "new_chat_member": {"status": "member"}}})
expect("бот добавлен в чат — приветствие и запись", (r["chat_id"], api._cache["groups"]["-200"]["on"]), (-200, True))
r = api.bot_update({"message": {"chat": {"id": -200, "type": "supergroup"}, "text": "/table@zvenya_salavat_bot"}})
expect("рейтинг в чате", r["text"].startswith("🏆"), True)
expect("обычные сообщения в чате бот не трогает", api.bot_update({"message": {"chat": {"id": -200, "type": "supergroup"}, "text": "привет"}}), None)
r = api.bot_update({"message": {"chat": {"id": 1, "type": "private"}, "from": {"first_name": "Гриша"}, "text": "/admin"}})
expect("панель владельца — первому пользователю", r["text"].startswith("📊 Панель владельца") and "Открыли бота: 2" in r["text"], True)
r = api.bot_update({"message": {"chat": {"id": 5, "type": "private"}, "from": {"first_name": "Петя"}, "text": "/admin"}})
expect("панель владельца закрыта для остальных", r["text"].startswith("📊"), False)

# вёрстка как на настоящей странице: причина удаления, гол в овертайме
REAL = ("<div>Овертайм 3 : 4</div><div>60:48</div><a>Митчелл Миллер</a><b>ГОЛ!</b><div>3 период 3 : 3</div>"
        "<div>55:43</div><a>Вадим Шипачев</a><b>штраф - удар клюшкой</b><div>25:48</div><a>Дин Стюарт</a>"
        "<b>штраф - опасная игра высоко поднятой клюшкой</b><div>Салават Юлаев</div>")
r = api.parse_se(REAL)
expect("разбор: причины удалений", r["pens"], [(1548, "Дин Стюарт", "опасная игра высоко поднятой клюшкой"),
                                               (3343, "Вадим Шипачев", "удар клюшкой")])
expect("разбор: овертайм", r["period"], 4)

# гол уходит сразу, передачи дописываются в то же сообщение, когда появятся
api._cache["sent"] = {}
api._cache["groups"] = {}
api._cache["subs"] = {"1": {"on": True, "goals": True}}
edits = []
nid = [100]


def fake_tg(method, **kw):
    if method == "editMessageText":
        edits.append((kw["chat_id"], kw["message_id"], kw["text"]))
        return {"ok": True}
    msgs.append(kw["text"])
    nid[0] += 1
    return {"ok": True, "result": {"message_id": nid[0]}}


api.tg = fake_tg
ast = {"v": []}
_sr_assists = api.sr_assists
api.sr_assists = lambda d, g, t, who: ast["v"]
state["page"] = page(830) + JS % "live"
tick(1000)
state["page"] = page(830) + JS % "live"
api._cache["sent"]["2026-11-16live"]["goals"] = []  # гол «новый» для этого опроса
got = tick(1010)
expect("гол без передач — сразу", got, ["🚨 ГОЛ «САЛАВАТА»!\nСалават Юлаев 1:0 Адмирал\n🏒 Данил Алалыкин\n⏱ 13:50 (1-й период)"])
tick(1020)
expect("передач пока нет — не правим", edits, [])
ast["v"] = ["Александр Жаровский", "Мэттью Маджо"]
tick(1040)
expect("передачи дописаны в отправленное сообщение", edits,
       [(1, nid[0], "🚨 ГОЛ «САЛАВАТА»!\nСалават Юлаев 1:0 Адмирал\n🏒 Данил Алалыкин (Александр Жаровский, Мэттью Маджо)\n⏱ 13:50 (1-й период)")])
tick(1070)
expect("второй раз не правим", len(edits), 1)

# гол в овертайме
api._cache["sent"]["2026-11-16live"]["goals"] = ["1:0"]
state["page"] = page(830).replace("</body>", "<div>Овертайм 2 : 0</div><div>61:10</div><a>Мэттью Маджо</a><b>ГОЛ!</b><span>2 : 0</span></body>")
got = [m for m in tick(9000) if "ГОЛ" in m]
expect("гол в овертайме", got, ["🚨 ГОЛ «САЛАВАТА» В ОВЕРТАЙМЕ!\nСалават Юлаев 2:0 Адмирал\n🏒 Мэттью Маджо\n⏱ 61:10 (овертайм, 1:10)"])

# разбор утром после матча: один раз, с 9:00 по Уфе, ждёт полный протокол до 13:00
import tempfile, json as _json
from datetime import datetime as _dt
tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf8")
_json.dump({"d": "2026-11-24", "full": False, "text": "📊 Разбор: Салават Юлаев 5:4 Нефтехимик ОТ\nБросков больше у нас: 37:25."}, tmp)
tmp.close()
api.RAZBOR = tmp.name
api._cache["sent"] = {}
api._cache["groups"] = {}
api._cache["subs"] = {"1": {"on": True, "goals": True}, "2": {"on": True, "goals": False}}
api.TOKEN = api.TOKEN or "test"
msgs.clear()
at = lambda s: _dt.strptime(s, "%Y-%m-%d %H:%M").replace(tzinfo=api.UFA).timestamp()
expect("разбор: ночью не шлём", api.razbor_tick(at("2026-11-25 07:00")), False)
expect("разбор: без протокола игроков ждём до 13:00", api.razbor_tick(at("2026-11-25 10:00")), False)
expect("разбор: в 13:00 шлём то, что есть", api.razbor_tick(at("2026-11-25 13:01")), True)
expect("разбор: текст ушёл подписчику «Матча онлайн»", msgs, ["📊 Разбор: Салават Юлаев 5:4 Нефтехимик ОТ\nБросков больше у нас: 37:25."])
expect("разбор: второй раз не шлём", api.razbor_tick(at("2026-11-25 14:00")), False)
api._cache["sent"] = {}
expect("разбор: позавчерашний матч не шлём", api.razbor_tick(at("2026-11-26 13:30")), False)
_json.dump({"d": "2026-11-24", "full": True, "text": "x"}, open(tmp.name, "w"))
expect("разбор: полный — шлём с 9 утра", api.razbor_tick(at("2026-11-25 09:05")), True)

# тревоги: владельцу, один раз на серию
tmp2 = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf8")
_json.dump({"d": "2026-11-24", "items": [{"k": "gksv:Семен Вязовой:2026-11-24", "text": "Вязовой: .883 отражённых за 5 матчей (порог .900)."}]}, tmp2)
tmp2.close()
api.ALERTS = tmp2.name
api._cache["sent"] = {}
api._cache["owner"] = {"id": "1"}
to = []
api.tg = lambda method, **kw: (to.append((kw.get("chat_id"), kw.get("text"))), {"ok": True})[1]
expect("тревоги: ночью не пишем", api.alerts_tick(at("2026-11-25 06:00")), False)
expect("тревоги: днём — владельцу", api.alerts_tick(at("2026-11-25 10:00")), True)
expect("тревоги: текст", to, [(1, "⚠ Тревоги «Звеньев Салавата»\n• Вязовой: .883 отражённых за 5 матчей (порог .900).")])
expect("тревоги: та же серия — второй раз не пишем", api.alerts_tick(at("2026-11-25 11:00")), False)
# Sports.ru: матч по ссылке-слагу из календаря (формат с ноября 2026) и передачи к голу соперника
SRCAL = ("<tr><td><a href='https://www.sports.ru/hockey/match/2026-11-24/'>24.11.2026|17:00</a></td>"
         "<td><a href='https://www.sports.ru/hockey/match/neftekhimik-vs-salavat/'>5:4</a></td></tr>"
         "<tr><td><a href='https://www.sports.ru/hockey/match/2026-11-26/'>26.11.2026|17:00</a></td>"
         "<td><a href='https://www.sports.ru/hockey/match/dynamo-minsk-vs-salavat/'>0:1</a></td></tr>")
SRMATCH = ("<html><body><div>26 ноября 2026</div><div>Салават Юлаев</div><div>Динамо Минск</div>"
           "<div>7:55</div><div>Гол!</div><div>Галиев</div><div>Обе-Кюбель, Улле</div></body></html>")


def sr_fetch(url):
    if url.endswith("/hockey/club/salavat/calendar/"):
        return SRCAL
    if url.endswith("/hockey/match/dynamo-minsk-vs-salavat/"):
        return SRMATCH
    raise OSError("нет страницы " + url)


api.fetch = sr_fetch
api._cache["srids"] = {}
api._cache["srseen"] = {}
api.save = lambda *a, **k: None
expect("Sports.ru: матч по слагу из календаря", api.sr_match_id("2026-11-26", "Динамо Мн"), "dynamo-minsk-vs-salavat")
expect("передачи к голу соперника", _sr_assists("2026-11-26", {"o": "Динамо Мн"}, 475, "Данияр Галиев"), ["Обе-Кюбель", "Улле"])

# фамилии наших игроков из настоящей страницы (26.11 список был пустым — все голы считались голами соперника)
api.PAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "index.html")
_ours = _our_surnames()
expect("наши фамилии из страницы приложения", (len(_ours) >= 25, "Броссо" in _ours, "Галиев" in _ours), (True, True, False))

print("ВСЁ В ПОРЯДКЕ" if ok else "ЕСТЬ ОШИБКИ")
sys.exit(0 if ok else 1)
