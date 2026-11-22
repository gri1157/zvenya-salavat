"""Полный текст регламентов КХЛ для поиска в приложении.
Берёт PDF из docs/reg/*.pdf, вытаскивает текст по страницам (нужен poppler: pdftotext),
сжимает (gzip+base64) и кладёт в index.html константой REGT.
Запуск: python3 .github/data/reg_text_build.py index.html"""
import sys, os, re, json, gzip, base64, subprocess
p = sys.argv[1]
base = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'docs', 'reg')
out = {}
for f in sorted(os.listdir(base)):
    if not f.endswith('.pdf'): continue
    path = os.path.join(base, f)
    n = int(re.search(r'Pages:\s+(\d+)', subprocess.check_output(['pdfinfo', path]).decode()).group(1))
    t = subprocess.check_output(['pdftotext', '-layout', path, '-']).decode('utf-8', 'replace')
    pages = t.split('\f')[:n]
    out[f[:-4]] = [re.sub(r'[ \t]+', ' ', re.sub(r'\n\s*\n+', '\n', x)).strip() for x in pages]
raw = json.dumps(out, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
b = base64.b64encode(gzip.compress(raw, 9)).decode()
h = open(p, encoding='utf-8').read()
line = 'const REGT="%s";\n' % b
if re.search(r'^const REGT=.*\n', h, re.M):
    h = re.sub(r'^const REGT=.*\n', lambda m: line, h, count=1, flags=re.M)
else:
    h = h.replace('const REG={', line + 'const REG={', 1)
open(p, 'w', encoding='utf-8').write(h)
print('документов:', len(out), 'страниц:', sum(len(v) for v in out.values()), 'текст:', len(raw), 'сжато base64:', len(b))
