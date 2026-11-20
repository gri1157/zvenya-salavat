"""Разведчик: только читает открытые сайты и печатает, что удалось достать. Ничего не меняет.
Запуск (на GitHub, где есть интернет): python3 .github/data/scout.py index.html
Нужен, чтобы понять, можно ли часть сбора данных отдать скрипту без ИИ."""
import json, sys, re, urllib.request
from html.parser import HTMLParser

URLS = {
    'sports.ru таблица': 'https://www.sports.ru/hockey/tournament/khl/table/',
    'allhockey матчи Салавата': 'https://allhockey.ru/stat/khl/2027/335/teams/13-Salavat_Yulaev/matches',
    'allhockey вратари лиги': 'https://allhockey.ru/stat/khl/2027/335/player/keeper',
    'khl.ru главная': 'https://www.khl.ru/',
    'khl.ru таблица': 'https://www.khl.ru/standings/',
    'sport-express игроки': 'https://www.sport-express.net/tag/salavat-yulaev-11/players-stats/',
}


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


def get(url):
    r = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36', 'Accept-Language': 'ru'})
    with urllib.request.urlopen(r, timeout=30) as x:
        return x.status, x.read().decode('utf-8', 'replace')


h = open(sys.argv[1], encoding='utf-8').read()
i = h.find('const TEAMS=')
TEAMS = json.JSONDecoder().raw_decode(h, i + 12)[0]
print('В приложении команд:', len(TEAMS))
for name, url in URLS.items():
    print('\n=====', name, url)
    try:
        st, body = get(url)
    except Exception as e:
        print('НЕ ОТКРЫЛОСЬ:', repr(e)[:200]); continue
    p = Rows(); p.feed(body)
    print('статус', st, 'размер', len(body), 'строк таблиц', len(p.rows))
    for r in p.rows[:6]:
        print('  ', r[:12])
    if 'sports.ru' in url:
        found = 0
        for t in TEAMS:
            for r in p.rows:
                if any(t[0].lower() in c.lower() for c in r[:3]):
                    print('  сверка', t[0], 'приложение: М', t[2], 'очки', t[7], '| сайт:', r[:10]); found += 1; break
        print('  команд найдено на странице:', found, 'из', len(TEAMS))
