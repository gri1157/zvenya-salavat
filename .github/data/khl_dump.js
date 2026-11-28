// Разовая выгрузка протокола матча khl.ru со всеми таблицами (в том числе игроки и вратари обеих команд).
// node .github/data/khl_dump.js 902308 > out.json
const { chromium } = require('playwright');
(async () => {
  const id = process.argv[2];
  const b = await chromium.launch();
  const p = await b.newPage({ locale: 'ru-RU', userAgent: 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36', viewport: { width: 1400, height: 900 } });
  await p.goto(`https://www.khl.ru/game/1436/${id}/protocol/`, { waitUntil: 'networkidle', timeout: 90000 });
  await p.waitForSelector('table', { state: 'attached', timeout: 30000 });
  await p.waitForTimeout(1500);
  const out = await p.evaluate(() => {
    const ctx = t => { const caps = []; let el = t; for (let k = 0; k < 8; k++) { el = el.parentElement; if (!el) break; const hh = el.querySelector(':scope > h2, :scope > h3, :scope > h4, :scope > .title, :scope > [class*=title], :scope > [class*=head]'); if (hh) caps.push(hh.innerText.replace(/\s+/g, ' ').trim().slice(0, 80)); } return caps; };
    const rows = t => [...t.rows].map(r => [...r.cells].map(c => c.innerText.replace(/\s+/g, ' ').trim()));
    return { title: document.title, tables: [...document.querySelectorAll('table')].map((t, i) => ({ i, ctx: ctx(t), cls: t.className, rows: rows(t) })) };
  });
  console.log(JSON.stringify(out));
  await b.close();
})();
