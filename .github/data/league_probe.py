"""Проба: какие командные таблицы есть на khl.ru (с cookie). Ничего не меняет."""
import re, urllib.request, http.cookiejar, html
UA = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36', 'Accept-Language': 'ru'}
cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
def get(url):
    with op.open(urllib.request.Request(url, headers=UA), timeout=30) as x:
        return x.read().decode('utf-8', 'replace')
h = get('https://www.khl.ru/stat/teams/')
links = sorted(set(re.findall(r'href="(/stat/[^"]+)"', h)))
print('LINKS', len(links)); [print('  ', l) for l in links[:80]]
heads = re.findall(r'<th[^>]*>(.*?)</th>', h, re.S)
print('TH', [re.sub(r'<[^>]+>|\s+', ' ', x).strip() for x in heads][:80])
txt = re.sub(r'\s+', ' ', html.unescape(re.sub(r'(?s)<script.*?</script>|<style.*?</style>|<[^>]+>', ' ', h)))
i = txt.find('Больш'); print('TXT', txt[max(0, i-1500):i+3000])
