"""Проба: как устроены страницы Allhockey (результаты, протокол) и открывается ли khl.ru с cookie. Ничего не меняет."""
import re, urllib.request, http.cookiejar
UA = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36', 'Accept-Language': 'ru'}
def get(url, opener=None):
    r = urllib.request.Request(url, headers=UA)
    with (opener.open(r, timeout=30) if opener else urllib.request.urlopen(r, timeout=30)) as x:
        return x.status, x.geturl(), x.read().decode('utf-8', 'replace')
def snip(h, key, n=1800):
    i = h.find(key)
    print(f'--- [{key}] at {i}')
    if i >= 0:
        print(re.sub(r'\s+', ' ', h[max(0, i - 300):i + n]))
st, u, h = get('https://allhockey.ru/stat/khl/2027/335/result')
links = re.findall(r'/stat/khl/2027/335/match/(\d+)-([A-Za-z0-9_]+)', h)
print('RESULT', st, len(h), 'links', len(links), len(set(links)), links[:6])
snip(h, '/match/' + links[0][0], 2500)
st, u, h = get('https://allhockey.ru/stat/khl/2027/335/match/99551-Salavat_Yulaev_Barys/protocol')
print('PROTOCOL', st, len(h))
for k in ['ГОЛЫ', '5x5', '5х4', 'ПВ', 'Удален', 'удар клюшкой', '%ОБ', 'Вязовой']:
    snip(h, k)
cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
for url in ['https://www.khl.ru/stat/teams/', 'https://www.khl.ru/standings/']:
    try:
        st, u, h = get(url, op)
        t = re.search(r'<title>(.*?)</title>', h, re.S)
        print('KHL', url, st, u, len(h), t.group(1).strip()[:120] if t else '', [c.name for c in cj])
    except Exception as e:
        print('KHL fail', url, repr(e)[:200], [c.name for c in cj])
