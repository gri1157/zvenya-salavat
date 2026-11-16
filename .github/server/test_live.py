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
api.tg = lambda method, **kw: msgs.append(kw["text"]) or {"ok": True}
api.calendar = lambda: {"2026-11-16": {"o": "Адмирал", "home": True, "kickoff": KICK, "deadline": KICK - 600}}
api._cache["subs"] = {"1": {"on": True, "goals": True}, "2": {"on": True}}
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
expect("первый гол", tick(1300), ["🚨 ГОЛ «САЛАВАТА»!\nСалават Юлаев 1:0 Адмирал\n🏒 Данил Алалыкин, 13:50"])
state["page"] = page(1200)
expect("второй гол", tick(1900), ["🚨 ГОЛ «САЛАВАТА»!\nСалават Юлаев 2:0 Адмирал\n🏒 Александр Жаровский, 19:54"])
expect("перерыв — тишина", tick(2500), [])
state["page"] = page(1276)  # заголовка 2-го периода нет, период виден по времени события
expect("2-й период и гол", tick(3200), ["▶️ Начался 2-й период\nСалават Юлаев 2:0 Адмирал",
                                         "🚨 ГОЛ «САЛАВАТА»!\nСалават Юлаев 3:0 Адмирал\n🏒 Александр Жаровский, 21:16"])
state["page"] = page(1638)
expect("гол соперника", tick(3600), ["Гол Адмирал\nСалават Юлаев 3:1 Адмирал\n🏒 Дмитрий Завгородний, 27:18"])
state["page"] = page(1638, header_only=3)
expect("3-й период по заголовку", tick(5400), ["▶️ Начался 3-й период\nСалават Юлаев 3:1 Адмирал"])
state["page"] = page(3092)
expect("пять голов за один опрос", [m.split("\n")[1] for m in tick(6600)],
       [f"Салават Юлаев {s} Адмирал" for s in ("3:2", "3:3", "4:3", "4:4", "4:5")])
state["page"] = page(3078)  # гол 4:5 пропал
expect("отмена: первый опрос ждём", tick(6630), [])
expect("отмена: второй опрос", tick(6660), ["❌ Гол отменён\nСалават Юлаев 4:4 Адмирал"])
state["page"] = page(3425)
expect("после отмены голы приходят снова", [m.split("\n")[1] for m in tick(7000)],
       [f"Салават Юлаев {s} Адмирал" for s in ("4:5", "5:5", "6:5")])
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
                                                           "Гол Адмирал\nСалават Юлаев 3:2 Адмирал\n🏒 Александр Дарьин, 43:14"])
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
print("ВСЁ В ПОРЯДКЕ" if ok else "ЕСТЬ ОШИБКИ")
sys.exit(0 if ok else 1)
