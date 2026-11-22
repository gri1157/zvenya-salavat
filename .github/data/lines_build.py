"""Звенья по протоколу: для каждого матча, где в COACH нет опубликованного состава Козлова,
собирает звенья из протокола Allhockey (AH): игроки по амплуа, по времени на льду за матч,
тройки нападающих и пары защитников подряд. Это оценка, а не заявка тренера.
Запуск: python3 .github/data/lines_build.py index.html  (меняет только константу COACH, добавляет недостающие даты)"""
import json, re, sys
p = sys.argv[1]
h = open(p, encoding='utf-8').read()
dec = json.JSONDecoder()
def const(name):
    i = h.find('const %s=' % name)
    return i, dec.raw_decode(h[i + len(name) + 7:])[0], i + len(name) + 7
_, RAW, _ = const('RAW'); _, AH, _ = const('AH'); _, GAMES, _ = const('GAMES')
ci = h.find('const COACH=[')
# конец массива COACH
depth = 0; j = ci + len('const COACH=')
for k in range(j, len(h)):
    c = h[k]
    if c == '[': depth += 1
    elif c == ']':
        depth -= 1
        if depth == 0: end = k + 1; break
body = h[j:end]
have = set(re.findall(r'date:"(\d{4}-\d\d-\d\d)"', body))
have_auto = set(re.findall(r'id:"p(\d{4}-\d\d-\d\d)"', body))
G = {g['d']: g for g in GAMES}
last_pub = max(have) if have else ''
new = []
for a in AH:
    d = a[0]
    if d in have or d <= last_pub or not a[4] or len(a[4]) < 17 or d not in G: continue
    g = G[d]
    F = sorted([r for r in a[4] if RAW[r[0]][2] == 'F'], key=lambda r: -r[1])
    D = sorted([r for r in a[4] if RAW[r[0]][2] == 'D'], key=lambda r: -r[1])
    nm = lambda r: RAW[r[0]][1]
    f = [[nm(r) for r in F[i:i + 3]] for i in range(0, len(F), 3)]
    dd = [[nm(r) for r in D[i:i + 2]] for i in range(0, len(D), 2)]
    gks = sorted(a[3], key=lambda x: -x[1]) if a[3] else []
    gl = [x[0] for x in gks if x[0] != '?'] or (['Семен Вязовой'])
    day = d[8:10] + '.' + d[5:7]
    mon = ['января','февраля','марта','апреля','мая','июня','июля','августа','сентября','октября','ноября','декабря'][int(d[5:7]) - 1]
    sc = '%s:%s%s' % (g['gf'], g['ga'], ' ОТ/Б' if g.get('x') else '')
    new.append((d, '{id:"p%s",label:"По протоколу · %s",date:"%s",title:"Звенья по протоколу на матч с %s (%d %s, %s). Оценка по времени на льду, не заявка тренера",g:%s,\n  f:%s,\n  d:%s}' % (d, day, d, g['o'], int(d[8:10]), mon, sc, json.dumps(gl[:2], ensure_ascii=False), json.dumps(f, ensure_ascii=False), json.dumps(dd, ensure_ascii=False))))
if not new:
    print('новых матчей для звеньев нет'); sys.exit(0)
# вставляем так, чтобы по датам новые шли первыми
items = []
for m in re.finditer(r'\n \{id:"[^"]+".*?date:"(\d{4}-\d\d-\d\d)"', body): pass
allnew = sorted(new, key=lambda x: x[0], reverse=True)
newtxt = ''.join('\n ' + t + ',' for _, t in allnew)
# в начало массива, затем сортировка по дате не нужна: COACH[0] должен быть самым свежим
body2 = '[' + newtxt + body[1:]
h = h[:j] + body2 + h[end:]
open(p, 'w', encoding='utf-8').write(h)
print('добавлено звеньев по протоколу:', ', '.join(d for d, _ in allnew))
