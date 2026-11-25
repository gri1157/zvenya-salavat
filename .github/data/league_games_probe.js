// Проба: календарь и протокол матча на khl.ru — какие командные таблицы есть. Ничего не меняет.
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ locale: 'ru-RU', userAgent: 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36', viewport: { width: 1400, height: 900 } });
  await p.goto('https://www.khl.ru/calendar/1436/00/', { waitUntil: 'networkidle', timeout: 90000 });
  await p.waitForTimeout(3000);
  const cards = await p.evaluate(() => [...document.querySelectorAll('li.match-card')].map(c => ({ href: (c.querySelector('a[href*="/game/"]') || {}).getAttribute?.('href') || '', t: c.innerText.replace(/\s+/g, ' ').trim().slice(0, 140) })));
  console.log('CARDS', cards.length, 'played', cards.filter(c => /\d+ — \d+/.test(c.t)).length);
  console.log('FIRST', JSON.stringify(cards.slice(0, 3)));
  console.log('SAL', JSON.stringify(cards.filter(c => /Салават/.test(c.t) && /\d+ — \d+/.test(c.t)).slice(-2)));
  const last = cards.filter(c => /Салават/.test(c.t) && /\d+ — \d+/.test(c.t)).slice(-1)[0];
  const id = (last.href.match(/\/game\/1436\/(\d+)/) || [])[1];
  await p.goto(`https://www.khl.ru/game/1436/${id}/protocol/`, { waitUntil: 'networkidle', timeout: 90000 });
  await p.waitForTimeout(3000);
  const r = await p.evaluate(() => {
    const capOf = t => { let cap = ''; let el = t; for (let k = 0; k < 6 && !cap; k++) { el = el.parentElement; const hh = el && el.querySelector('h2,h3,h4,.title,[class*=title]'); if (hh) cap = hh.innerText.trim(); } return cap; };
    const rows = t => [...t.rows].map(r => [...r.cells].map(c => c.innerText.replace(/\s+/g, ' ').trim()));
    return { title: document.title, tables: [...document.querySelectorAll('table')].map(t => ({ cap: capOf(t).slice(0, 60), cls: t.className, n: t.rows.length, rows: rows(t).slice(0, 4) })) };
  });
  console.log('TITLE', r.title);
  for (const t of r.tables) if (!/^(Вратари|Защитники|Нападающие)$/.test(t.cap)) console.log('TAB', JSON.stringify(t).slice(0, 1500));
  await b.close();
})();
