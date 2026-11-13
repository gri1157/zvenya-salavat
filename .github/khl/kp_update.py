"""Вносит официальные протоколы сайта КХЛ (скорость, пробег, время в большинстве и меньшинстве,
кто на льду при голах, командные показатели) в константы KP, KG, KT файла index.html.
Остальные данные не трогает.

Запуск: python3 .github/khl/kp_update.py index.html khl.json [--force]
khl.json — то, что вернула функция zvKHL(...) из .github/khl/khl-browser.js: {"ND":{...},"C":[...]}.
Без --force уже внесённые даты не перезаписываются.
"""
import json, sys

src, data = sys.argv[1], sys.argv[2]
force = '--force' in sys.argv
h = open(src, encoding='utf-8').read()
dec = json.JSONDecoder()


def span(k):
    i = h.find('const ' + k + '=')
    assert i >= 0, k
    a = i + len('const ' + k + '=')
    v, e = dec.raw_decode(h, a)
    return v, a, e


def sec(t):
    if not t or ':' not in str(t):
        return 0
    m, s = str(t).split(':')
    return int(m) * 60 + int(s)


RAW, _, _ = span('RAW')
idx = {r[0]: k for k, r in enumerate(RAW) if r[0]}
GAMES, _, _ = span('GAMES')
KP, _, _ = span('KP')
KG, _, _ = span('KG')
KT, _, _ = span('KT')
C = json.load(open(data, encoding='utf-8'))['C']
KIND = {'РАВ': 'ev', 'БОЛ': 'pp', 'МЕН': 'sh'}
year = {m: (2026 if m >= 8 else 2027) for m in range(1, 13)}
done, skipped = [], []

for g in C:
    dd, mm = g['date'].split('.')
    d = '%d-%s-%s' % (year[int(mm)], mm, dd)
    if not g.get('P'):
        skipped.append((d, 'протокол на сайте КХЛ пустой'))
        continue
    if d in KP and not force:
        skipped.append((d, 'уже внесён'))
        continue
    if not any(x['d'] == d for x in GAMES):
        skipped.append((d, 'матча ещё нет в GAMES — сначала его вносит сборщик'))
        continue
    miss = [p[0] for p in g['P'] if p[0] not in idx]
    if miss:
        skipped.append((d, 'нет в RAW номеров %s' % miss))
        continue
    oppg = [k[0] for k in g['GKT']]
    ourg = [k[0] for k in g['GK']]
    og = []
    for x in g['G']:
        per, t, our, kind, sc, a1, a2, onU, onT = x
        if not kind:
            continue
        k = KIND[kind]
        conc = [int(v) for v in (onT if our else onU).split(',') if v]
        if k == 'ev' and not any(v in (oppg if our else ourg) for v in conc):
            k = 'en'
        onn = [idx[int(v)] for v in onU.split(',') if v and int(v) in idx and int(v) not in ourg]
        og.append([t, our, k, onn, len([v for v in onT.split(',') if v]) - (1 if any(int(v) in oppg for v in onT.split(',') if v) else 0)])
    KG[d] = og
    KP[d] = [[idx[p[0]], p[16], p[17], p[19], p[20], p[11], p[12], p[14], p[24], p[25], p[26], p[21], p[22], p[23]] for p in g['P']]
    tm = g['tm']
    cp = tm['Командные показатели']
    vv = tm['Время владения шайбой и пройденная дистанция']
    tl = tm['Время на льду']
    f = lambda v: float(v) if v not in ('', None) else 0
    KT[d] = [sec(vv[0][0]), sec(vv[1][0]), f(vv[0][1]), f(vv[1][1]), sec(cp[0][2]), sec(cp[1][2]), int(cp[0][1]), int(cp[1][1]),
             int(cp[0][0]), int(cp[1][0]), int(cp[0][3]), int(cp[1][3]), int(cp[0][4]), int(cp[1][4]), sec(tl[0][1]), sec(tl[0][2])]
    done.append(d)

js = lambda v: json.dumps(dict(sorted(v.items())), ensure_ascii=False, separators=(',', ':'))
for k, v in (('KP', KP), ('KG', KG), ('KT', KT)):
    _, a, e = span(k)
    h = h[:a] + js(v) + h[e:]
open(src, 'w', encoding='utf-8').write(h)
print(json.dumps({'внесено': done, 'пропущено': skipped}, ensure_ascii=False, indent=1))
