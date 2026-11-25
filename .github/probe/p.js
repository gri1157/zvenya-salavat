const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ locale: 'ru-RU', userAgent: 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36', viewport: { width: 1400, height: 900 } });
  await p.goto('https://www.khl.ru/game/1436/902296/protocol/', { waitUntil: 'networkidle', timeout: 90000 });
  await p.waitForTimeout(2000);
  const r = await p.evaluate(() => [...document.querySelectorAll('table')].filter(t => /^(Ш|БлБ)/.test((t.rows[0]?.innerText || '').trim())).slice(0, 4).map(t => [...t.rows].map(r => [...r.cells].map(c => c.innerText.replace(/\s+/g, ' ').trim() + (c.colSpan > 1 ? '[cs' + c.colSpan + ']' : '')))));
  console.log('T', JSON.stringify(r));
  await b.close();
})();
