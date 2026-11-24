// Проба: страницы разделов командной статистики khl.ru (/stat/teams/1436/<раздел>/) — столбцы и строка «Салавата». Ничего не меняет.
const { chromium } = require('playwright');
const SECS = ['', 'home', 'road', 'first-period', 'second-period', 'third-period', 'overtime', 'goals-for', 'goals-against', 'shots', 'games-actions', 'powerplay-gf', 'powerplay-ga', 'shorthanded-gf', 'shorthanded-ga', 'penalties', 'faceoffs'];
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ locale: 'ru-RU', userAgent: 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36' });
  for (const s of SECS) {
    const url = `https://www.khl.ru/stat/teams/1436/${s ? s + '/' : ''}`;
    try {
      const resp = await p.goto(url, { waitUntil: 'networkidle', timeout: 60000 });
      await p.waitForTimeout(1500);
      const r = await p.evaluate(() => {
        const t = document.querySelector('table');
        const rows = t ? [...t.querySelectorAll('tr')] : [];
        const cells = tr => [...tr.children].map(c => c.textContent.trim().replace(/\s+/g, ' '));
        const opts = [...document.querySelectorAll('.filter-sheet button, .filter-sheet li, [data-value]')].map(e => (e.getAttribute('data-value') || '') + ':' + e.textContent.trim().replace(/\s+/g, ' ').slice(0, 30)).slice(0, 60);
        return { n: rows.length, head: rows[0] ? cells(rows[0]) : [], sal: (rows.find(tr => /Салават/.test(tr.textContent)) && cells(rows.find(tr => /Салават/.test(tr.textContent)))) || [], opts };
      });
      console.log('SEC', s || 'standings', resp && resp.status(), JSON.stringify({ n: r.n, head: r.head, sal: r.sal }));
      if (!s) console.log('OPTS', JSON.stringify(r.opts));
    } catch (e) { console.log('FAIL', s, String(e).slice(0, 200)); }
  }
  await b.close();
})();
