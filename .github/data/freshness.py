"""Свежесть данных приложения. Без ИИ, только чтение index.html.
Запуск: python3 .github/data/freshness.py index.html [сегодня YYYY-MM-DD]
Проверяет:
  1) каждый матч из календаря CAL, который уже прошёл (дата раньше сегодня), есть в GAMES;
  2) дата UPDATED.date не отстаёт от последнего матча в GAMES (обновление вышло после игры).
Код 1 — есть расхождение. Код 0 — всё свежее."""
import datetime, json, re, sys

MONTHS = {'января': 1, 'февраля': 2, 'марта': 3, 'апреля': 4, 'мая': 5, 'июня': 6,
          'июля': 7, 'августа': 8, 'сентября': 9, 'октября': 10, 'ноября': 11, 'декабря': 12}


def parse_ru(s):
    m = re.match(r'\s*(\d{1,2})\s+([а-яё]+)\s+(\d{4})', s or '')
    if not m or m.group(2) not in MONTHS:
        return None
    return datetime.date(int(m.group(3)), MONTHS[m.group(2)], int(m.group(1)))


def load_const(h, name):
    i = h.find('const %s=' % name)
    if i < 0:
        raise SystemExit('нет константы %s' % name)
    return json.JSONDecoder().raw_decode(h, i + len(name) + 7)[0]


h = open(sys.argv[1], encoding='utf-8').read()
today = datetime.date.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 else datetime.datetime.utcnow().date()
GAMES = load_const(h, 'GAMES')
CAL = load_const(h, 'CAL')
played_dates = {g['d'] for g in GAMES}
problems = []

# 1) прошедшие матчи календаря должны быть в GAMES
for c in CAL:
    d = datetime.date.fromisoformat(c[0])
    if d < today and c[0] not in played_dates:
        problems.append('КРИТИЧНО: матч %s с %s (%s) прошёл, но в приложении его нет' % (c[0], c[2], 'дома' if c[3] else 'в гостях'))

# 2) обновление не отстаёт от последней игры
m = re.search(r'const UPDATED=\{[^}]*?\}', h)
upd = m.group(0) if m else ''
dm = re.search(r'date:"([^"]+)"', upd)
upd_date = parse_ru(dm.group(1)) if dm else None
last_game = max((datetime.date.fromisoformat(g['d']) for g in GAMES), default=None)
if upd_date is None:
    problems.append('ВАЖНО: не разобрана дата обновления UPDATED.date')
elif last_game and upd_date < last_game:
    problems.append('ВАЖНО: обновление от %s старее последнего матча %s' % (upd_date, last_game))

print('Сегодня: %s · последний матч: %s · обновление: %s · календарь: %d' % (today, last_game, upd_date, len(CAL)))
if problems:
    print('РАСХОЖДЕНИЯ:')
    for p in problems:
        print(' !', p)
    sys.exit(1)
print('Свежо: все прошедшие матчи на месте, обновление не отстаёт.')
