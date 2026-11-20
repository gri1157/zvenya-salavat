"""Отчёт «что изменилось» между старой и новой версией приложения + защита качества данных.
Запуск: python3 .github/data/diff-report.py old.html index.html
Печатает, сколько записей изменено в каждой константе, и список ПОДОЗРИТЕЛЬНЫХ изменений.
Код возврата 1, если есть подозрительное — тогда публиковать нельзя, пока не разобрался.
Работает без ИИ и без сети.
"""
import json, sys

dec = json.JSONDecoder()


def load(path):
    h = open(path, encoding='utf-8').read()
    out = {}
    for k in ['RAW', 'GAMES', 'AH', 'TEAMS', 'G', 'SE', 'KP', 'KG', 'KT', 'CAL', 'COACH', 'INJ']:
        i = h.find('const ' + k + '=')
        if i < 0:
            continue
        try:
            out[k] = dec.raw_decode(h, i + len(k) + 7)[0]
        except Exception:
            out[k] = None
    return out


old, new = load(sys.argv[1]), load(sys.argv[2])
bad, info = [], []

for k in new:
    o, n = old.get(k), new[k]
    if o is None or n is None:
        if o != n:
            bad.append('%s: константа не читается (была %s, стала %s)' % (k, type(o).__name__, type(n).__name__))
        continue
    if isinstance(n, dict):
        add = [x for x in n if x not in o]
        dele = [x for x in o if x not in n]
        chg = [x for x in n if x in o and n[x] != o[x]]
        info.append('%s: добавлено %d, изменено %d, удалено %d' % (k, len(add), len(chg), len(dele)))
        if dele:
            bad.append('%s: пропали записи %s' % (k, dele[:5]))
    else:
        info.append('%s: было %d, стало %d' % (k, len(o), len(n)))
        if len(n) < len(o):
            bad.append('%s: записей стало меньше (%d -> %d)' % (k, len(o), len(n)))

# Счётчики игроков не должны уменьшаться (матчи, голы, передачи, штраф)
if old.get('RAW') and new.get('RAW'):
    on = {r[1]: r for r in old['RAW'] if r[1]}
    for r in new['RAW']:
        p = on.get(r[1])
        if p:
            for idx, nm in ((3, 'матчи'), (4, 'голы'), (5, 'передачи'), (7, 'штраф')):
                if r[idx] < p[idx]:
                    bad.append('RAW %s: %s уменьшились (%s -> %s)' % (r[1], nm, p[idx], r[idx]))
            if r[3] - p[3] > 3:
                bad.append('RAW %s: матчей сразу +%d' % (r[1], r[3] - p[3]))
# Очки команд = 2*победы + поражения в ОТ/Б
if new.get('TEAMS'):
    for t in new['TEAMS']:
        if t[7] != 2 * t[3] + t[4]:
            bad.append('TEAMS %s: очки %s не равны 2*%s+%s' % (t[0], t[7], t[3], t[4]))
# Ничего из GAMES не должно измениться задним числом
if old.get('GAMES') and new.get('GAMES'):
    od = {g['d']: g for g in old['GAMES']}
    for g in new['GAMES']:
        if g['d'] in od and od[g['d']] != g:
            info.append('GAMES %s изменён задним числом (проверь, что это исправление, а не ошибка)' % g['d'])

print('Что изменилось:')
for s in info:
    print(' -', s)
if bad:
    print('ПОДОЗРИТЕЛЬНО:')
    for s in bad:
        print(' !', s)
    sys.exit(1)
print('Подозрительного нет.')
