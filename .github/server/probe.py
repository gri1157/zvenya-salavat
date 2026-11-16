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
        print("SE первые строки:")
        for x in L[:120]:
            print("   |", x[:140])
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
