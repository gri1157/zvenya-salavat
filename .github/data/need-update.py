"""Нужен ли дорогой запуск ИИ-сборщика? Работает без ИИ и без сети.
Запуск: python3 .github/data/need-update.py index.html
Печатает одну строку JSON и завершается кодом 0 всегда.
  full   — после последнего матча в GAMES уже сыгран новый матч (прошло >3 ч после начала): нужен полный сбор
  light  — новых матчей нет, но данные старше 3 суток: достаточно таблицы, травм и составов
  skip   — новых матчей нет и данные свежие: ничего не делать
  proto  — не хватает протоколов КХЛ (даты из GAMES, которых нет в KP): нужен браузер владельца
Время начала в CAL — московское (UTC+3).
"""
import json, sys, re, datetime as dt

h = open(sys.argv[1] if len(sys.argv) > 1 else 'index.html', encoding='utf-8').read()
dec = json.JSONDecoder()


def const(k):
    i = h.find('const ' + k + '=')
    assert i >= 0, k
    return dec.raw_decode(h, i + len(k) + 7)[0]


GAMES, CAL, KP = const('GAMES'), const('CAL'), const('KP')
now = dt.datetime.now(dt.timezone.utc)
have = {g['d'] for g in GAMES}
played = []
for d, t, opp, home in CAL:
    hh, mm = map(int, t.split(':'))
    start = dt.datetime.fromisoformat(d).replace(hour=hh, minute=mm, tzinfo=dt.timezone.utc) - dt.timedelta(hours=3)
    if now >= start + dt.timedelta(hours=3) and d not in have and d > '2026-09-01':
        played.append(d)
m = re.search(r'const UPDATED=\{[^}]*?date:"([^"]+)"', h)
months = {'января':1,'февраля':2,'марта':3,'апреля':4,'мая':5,'июня':6,'июля':7,'августа':8,'сентября':9,'октября':10,'ноября':11,'декабря':12}
age = None
if m:
    dd, mn, yy = m.group(1).split()
    age = (now.date() - dt.date(int(yy), months[mn], int(dd))).days
kp_dates = set(KP) if isinstance(KP, dict) else {r[0] for r in KP}
no_proto = sorted(d for d in have if d not in kp_dates and d != '2026-09-20')
site_missing = []
try:
    need = json.load(open('.github/data/need.json', encoding='utf-8'))
    site_missing = [d for d in need.get('нет_в_приложении', []) if d not in have]
except Exception:
    pass
played = sorted(set(played) | set(site_missing))
mode = 'full' if played else ('light' if (age is None or age >= 3) else 'skip')
print(json.dumps({'mode': mode, 'новые_матчи': played, 'данным_дней': age, 'нет_протокола_КХЛ': no_proto}, ensure_ascii=False))
