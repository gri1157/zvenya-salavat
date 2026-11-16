"""Проверка источников трансляции на живых страницах. Запуск: python3 probe.py ГГГГ-ММ-ДД Соперник"""
import os, re, sys, tempfile
os.environ.setdefault("ZV_DATA", tempfile.mkdtemp())
os.environ.setdefault("ZV_PAGE", "index.html")
sys.path.insert(0, os.path.dirname(__file__))
import api

d, opp = sys.argv[1], sys.argv[2]
try:
    mid = api.se_match_id(d, opp)
    print("SE id:", mid)
    if mid:
        page = api.fetch(f"{api.SE}/hockey/L/matchcenter/{mid}/")
        r = api.parse_se(page)
        print("SE период:", r["period"], "наш:", r["ours"], "голов:", len(r["goals"]))
        for g in r["goals"]:
            print("  ", g)
        L = api.text_lines(page)
        print("SE строк текста:", len(L))
        for i, x in enumerate(L):
            if re.search(r"оконч|заверш|буллит|овертайм|период|Счет|Счёт|итог|Лучш", x, re.I) and len(x) < 160:
                print(f"  [{i}] {x}")
        for i, x in enumerate(L):
            if x == "Матч окончен":
                print("--- контекст", i)
                for y in L[max(0, i - 14):i + 6]:
                    print("   |", y[:120])
        for m in re.finditer("Матч окончен", page):
            print("--- html", m.start())
            print(re.sub(r"\s+", " ", page[max(0, m.start() - 700):m.start() + 120]))
        print("--- строки 130-160")
        for y in L[130:160]:
            print("   |", y[:120])
except Exception as e:
    print("SE ошибка:", repr(e))
try:
    sid = api.sr_match_id(d, opp)
    print("SR id:", sid)
    if sid:
        page = api.fetch(f"{api.SR}/hockey/match/{sid}/")
        gl = api.parse_goals(page)
        print("SR голов:", len(gl))
        for g in gl:
            print("  ", g)
        L = api.text_lines(page)
        for i, x in enumerate(L):
            if re.search(r"оконч|заверш|буллит|овертайм|Лучш", x, re.I) and len(x) < 160:
                print(f"  [{i}] {x}")
except Exception as e:
    print("SR ошибка:", repr(e))
