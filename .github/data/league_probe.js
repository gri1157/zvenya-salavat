// Проба: khl.ru в настоящем браузере (Playwright) — какие командные таблицы видны. Ничего не меняет.
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ locale: 'ru-RU', userAgent: 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36' });
  for (const url of ['https://www.khl.ru/stat/teams/']) {
    try {
      await p.goto(url, { waitUntil: 'networkidle', timeout: 60000 });
      await p.waitForTimeout(4000);
      const r = await p.evaluate(() => ({
        title: document.title,
        links: [...new Set([...document.querySelectorAll('a[href*="/stat/"]')].map(a => a.getAttribute('href') + ' | ' + a.textContent.trim().slice(0, 40)))].slice(0, 80),
        tables: [...document.querySelectorAll('table')].slice(0, 8).map(t => [...t.querySelectorAll('tr')].slice(0, 4).map(tr => [...tr.children].map(c => c.textContent.trim().replace(/\s+/g, ' ')).join(' | '))),
        text: document.body.innerText.replace(/\s+/g, ' ').slice(0, 3000),
      }));
      console.log('URL', url, JSON.stringify(r, null, 1));
    } catch (e) { console.log('FAIL', url, String(e).slice(0, 300)); }
  }
  await b.close();
})();
