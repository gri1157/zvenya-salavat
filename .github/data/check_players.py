"""Сверка сезонных цифр игроков Салавата со Спорт-Экспрессом (И, Г, П, +/-, ШВ). Без ИИ, только чтение.
Запуск: python3 .github/data/check_players.py index.html
Печатает расхождения; код 1, если они есть. Нужен, чтобы понять, можно ли обновлять RAW скриптом."""
import json, re, sys, urllib.request
from html.parser import HTMLParser

URL = 'https://www.sport-express.net/tag/salavat-yulaev-11/players-stats/'


class Rows(HTMLParser):
    def __init__(s):
        super().__init__(); s.rows = []; s.cur = None; s.cell = None
    def handle_starttag(s, t, a):
        if t == 'tr': s.cur = []
        if t in ('td', 'th') and s.cur is not None: s.cell = ''
    def handle_endtag(s, t):
        if t in ('td', 'th') and s.cur is not None and s.cell is not None:
            s.cur.append(re.sub(r'\s+', ' ', s.cell).strip()); s.cell = None
        if t == 'tr' and s.cur:
            s.rows.append(s.cur); s.cur = None
    def handle_data(s, d):
        if s.cell is not None: s.cell += d


def norm(n):
    n = re.sub(r'\s*\((н|з|вр)\)\s*', ' ', n).replace('ё', 'е').replace('Ё', 'Е')
    return re.sub(r'\s+', ' ', n).strip().lower()


def num(x):
    x = x.replace('−', '-').replace('+', '').strip()
    return int(x) if re.fullmatch(r'-?\d+', x) else None


h = open(sys.argv[1], encoding='utf-8').read()
i = h.find('const RAW=')
RAW = json.JSONDecoder().raw_decode(h, i + 10)[0]
req = urllib.request.Request(URL, headers={'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) Chrome/124 Safari/537.36', 'Accept-Language': 'ru'})
p = Rows(); p.feed(urllib.request.urlopen(req, timeout=30).read().decode('utf-8', 'replace'))
hdr = None
site = {}
for r in p.rows:
    if 'Игрок' in r and 'И' in r and 'Г' in r:
        hdr = r; print('Заголовок таблицы:', r); continue
    if hdr and len(r) == len(hdr) and r[hdr.index('Игрок')]:
        d = dict(zip(hdr, r))
        site[norm(d['Игрок'])] = d
print('Игроков на сайте:', len(site))
bad, seen = [], 0
for row in RAW:
    num_, name, pos, m, g, a, pm, pim = row[:8]
    if not name or m == 0: continue
    s = site.get(norm(name))
    if not s:
        bad.append('нет на сайте: ' + name); continue
    seen += 1
    for lab, mine, key in (('М', m, 'И'), ('Г', g, 'Г'), ('П', a, 'П'), ('+/-', pm, '+/-'), ('Шв', pim, 'ШВ')):
        v = num(s.get(key, ''))
        if v is not None and v != mine:
            bad.append('%s: %s приложение %s, сайт %s' % (name, lab, mine, v))
print('Сверено игроков:', seen)
# второй источник — Allhockey: покажет, кто прав в спорных ячейках
AH = 'https://allhockey.ru/stat/khl/2027/335/teams/13-Salavat_Yulaev/players'
q = Rows()
try:
    q.feed(urllib.request.urlopen(urllib.request.Request(AH, headers=req.headers), timeout=30).read().decode('utf-8', 'replace'))
except Exception as e:
    print('Allhockey не открылся:', repr(e)[:120])
ah = {}
ahdr = None
for r in q.rows:
    if 'Игрок' in r and ('Штр' in r or '+/-' in r):
        ahdr = r; print('Заголовок Allhockey:', r); continue
    if ahdr and len(r) == len(ahdr) and r[ahdr.index('Игрок')]:
        d = dict(zip(ahdr, r)); ah[norm(d['Игрок'])] = d
def third(name, lab):
    d = ah.get(norm(name))
    if not d: return '?'
    key = {'+/-': '+/-', 'Шв': 'Штр', 'М': 'И', 'Г': 'Ш', 'П': 'А'}[lab]
    return d.get(key, '?')
out = []
for b in bad:
    if b.startswith('нет на сайте'):
        out.append(b); continue
    lab = 'Шв' if ' Шв ' in b else ('+/-' if '+/-' in b else 'М')
    mine = b.split('приложение ')[1].split(',')[0]
    t = third(b.split(':')[0], lab)
    # спорно только если Allhockey не подтверждает приложение (или не знает игрока)
    if t.replace('+', '') != mine:
        out.append(b + ' | Allhockey: ' + t)
    else:
        print('  (Спорт-Экспресс отстаёт, Allhockey подтверждает приложение:', b.split(' |')[0], ')')
bad = out
if bad:
    print('РАСХОЖДЕНИЯ:'); [print(' !', b) for b in bad]; sys.exit(1)
print('Все цифры совпадают.')
