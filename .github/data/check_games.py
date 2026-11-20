"""Сверка результатов матчей Салавата с Allhockey. Без ИИ, только чтение.
Запуск: python3 .github/data/check_games.py index.html
Печатает: матчи, которых нет в приложении (сыграны), и матчи, где счёт или ОТ/Б не совпадает. Код 1, если есть расхождения."""
import json, re, sys, urllib.request
from html.parser import HTMLParser

URL = 'https://allhockey.ru/stat/khl/2027/335/teams/13-Salavat_Yulaev/matches'


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


h = open(sys.argv[1], encoding='utf-8').read()
i = h.find('const GAMES=')
GAMES = json.JSONDecoder().raw_decode(h, i + 12)[0]
mine = {g['d']: g for g in GAMES}
req = urllib.request.Request(URL, headers={'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) Chrome/124 Safari/537.36', 'Accept-Language': 'ru'})
p = Rows(); p.feed(urllib.request.urlopen(req, timeout=30).read().decode('utf-8', 'replace'))
site, bad = {}, []
for r in p.rows:
    if len(r) < 4: continue
    m = re.match(r'(\d\d)\.(\d\d)\.(\d{4})', r[1])
    s = re.match(r'(\d+):(\d+)\s*(ОТ|Б)?', r[3])
    if not m or not s or '–' not in r[2]: continue
    d = '%s-%s-%s' % (m.group(3), m.group(2), m.group(1))
    home = r[2].split('–')[0].strip().startswith('Салават')
    a, b = int(s.group(1)), int(s.group(2))
    gf, ga = (a, b) if home else (b, a)
    site[d] = (gf, ga, s.group(3) or '', home)
for d, (gf, ga, x, home) in sorted(site.items()):
    g = mine.get(d)
    if not g:
        bad.append('нет в приложении: %s %s:%s %s' % (d, gf, ga, x)); continue
    if (g['gf'], g['ga']) != (gf, ga) or (g.get('x') or '') != x or bool(g['h']) != home:
        bad.append('не совпадает %s: приложение %s:%s %s дома=%s | сайт %s:%s %s дома=%s' % (d, g['gf'], g['ga'], g.get('x') or '', bool(g['h']), gf, ga, x, home))
for d in mine:
    if d not in site: bad.append('в приложении есть, на сайте нет: ' + d)
print('Матчей на сайте: %d, в приложении: %d' % (len(site), len(mine)))
if bad:
    print('РАСХОЖДЕНИЯ:'); [print(' !', b) for b in bad]; sys.exit(1)
print('Все результаты совпадают.')
