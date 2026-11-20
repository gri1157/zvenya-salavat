"""Обновляет таблицу команд КХЛ (константа TEAMS) по Sports.ru. Без ИИ.
Запуск: python3 .github/data/update_table.py index.html [--write]
Без --write только показывает, что изменится. С --write правит TEAMS и дату таблицы (UPDATED.table и «Таблица на …»).
Защита: если что-то не сходится (число команд, М = В + П + ПО, очки = 2×В + ПО, незнакомая команда) —
ничего не пишет и завершается с кодом 1."""
import json, re, sys, urllib.request, datetime as dt
from html.parser import HTMLParser

URL = 'https://www.sports.ru/hockey/tournament/khl/table/'
ALIAS = {'Динамо Москва': 'Динамо М', 'Динамо Минск': 'Динамо Мн', 'Торпедо': 'Торпедо НН', 'Торпедо Нижний Новгород': 'Торпедо НН',
         'ХК Сочи': 'Сочи', 'Драконы': 'Шанхай Дрэгонс', 'Металлург Магнитогорск': 'Металлург Мг'}
MONTHS = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря']


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


path = sys.argv[1]
write = '--write' in sys.argv
h = open(path, encoding='utf-8').read()
i = h.find('const TEAMS=')
old, end = json.JSONDecoder().raw_decode(h, i + 12)
req = urllib.request.Request(URL, headers={'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) Chrome/124 Safari/537.36', 'Accept-Language': 'ru'})
p = Rows(); p.feed(urllib.request.urlopen(req, timeout=30).read().decode('utf-8', 'replace'))

conf, tables = None, 0
new, errs = {}, []
for r in p.rows:
    if len(r) >= 12 and r[0] == '#':
        tables += 1; conf = 'Запад' if tables == 1 else 'Восток'; continue
    if conf and len(r) >= 12 and r[0].isdigit():
        name = ALIAS.get(r[1], r[1])
        try:
            m, w, wo, l, lo, gf, ga = (int(x) for x in (r[3], r[4], r[5], r[6], r[7], r[8], r[9])); pts = int(r[11])
        except ValueError:
            errs.append('не число в строке ' + str(r[:12])); continue
        if m != w + l + lo: errs.append('%s: М %d != В+П+ПО %d' % (name, m, w + l + lo))
        if pts != 2 * w + lo: errs.append('%s: очки %d != 2×В+ПО %d' % (name, pts, 2 * w + lo))
        new[name] = [name, conf, m, w, lo, gf, ga, pts, wo]
known = [t[0] for t in old]
for n in new:
    if n not in known: errs.append('незнакомая команда: ' + n)
for n in known:
    if n not in new: errs.append('нет на сайте: ' + n)
if tables != 2: errs.append('таблиц на странице %d, ожидалось 2' % tables)
for n in known:
    if n in new and new[n][2] < next(t for t in old if t[0] == n)[2]: errs.append('%s: матчей стало меньше' % n)
if sum(t[8] for t in new.values()) != sum(t[4] for t in new.values()):
    errs.append('победы в ОТ/Б (%d) и поражения в ОТ/Б (%d) по лиге не равны' % (sum(t[8] for t in new.values()), sum(t[4] for t in new.values())))
if errs:
    print('НЕ СХОДИТСЯ, ничего не пишу:'); [print(' !', e) for e in errs]; sys.exit(1)

res = [new[n] for n in known]
changed = [(a, b) for a, b in zip(old, res) if a != b]
print('Команд изменилось:', len(changed))
for a, b in changed: print(' ', a[0], 'М %d→%d, очки %d→%d' % (a[2], b[2], a[7], b[7]))
if write and changed:
    txt = json.dumps(res, ensure_ascii=False, separators=(',', ':'))
    h = h[:i + 12] + txt + h[end:]
    t = dt.date.today(); ds = '%d %s' % (t.day, MONTHS[t.month - 1])
    h = re.sub(r'(const UPDATED=\{[^}]*?table:")[^"]*(")', r'\g<1>' + ds + r'\g<2>', h, 1)
    h = re.sub(r'Таблица на \d+ [а-я]+', 'Таблица на ' + ds, h)
    open(path, 'w', encoding='utf-8').write(h)
    print('Записано. Дата таблицы:', ds)
