// Проба: вкладки командной статистики khl.ru и их столбцы. Ничего не меняет.
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ locale: 'ru-RU', userAgent: 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36' });
  const grab = async (url) => {
    await p.goto(url, { waitUntil: 'networkidle', timeout: 60000 });
    await p.waitForTimeout(2500);
    return p.evaluate(() => ({
      links: [...new Set([...document.querySelectorAll('a[href*="/stat/teams/"]')].map(a => a.getAttribute('href') + ' | ' + a.textContent.trim().replace(/\s+/g, ' ').slice(0, 40)))],
      selects: [...document.querySelectorAll('select,option')].slice(0, 40).map(o => (o.value || '') + ':' + o.textContent.trim().slice(0, 30)),
      tables: [...document.querySelectorAll('table')].map(t => ({ rows: t.querySelectorAll('tr').length, head: [...(t.querySelector('tr')?.children || [])].map(c => c.textContent.trim().replace(/\s+/g, ' ')), r1: [...(t.querySelectorAll('tr')[1]?.children || [])].map(c => c.textContent.trim().replace(/\s+/g, ' ')) })),
    }));
  };
  const first = await grab('https://www.khl.ru/stat/teams/1436/');
  console.log('BASE', JSON.stringify(first));
  const tabs = [...new Set(first.links.map(l => l.split(' | ')[0]).filter(h => /\/stat\/teams\/1436\/[a-z_]+\/?$/.test(h)))];
  for (const t of tabs) {
    try { const r = await grab(new URL(t, 'https://www.khl.ru').href); console.log('TAB', t, JSON.stringify(r.tables)); }
    catch (e) { console.log('FAIL', t, String(e).slice(0, 200)); }
  }
  await b.close();
})();
