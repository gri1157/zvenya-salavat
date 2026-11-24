// Проба: REST-запросы командной статистики khl.ru (тело и ответ). Ничего не меняет.
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ locale: 'ru-RU', userAgent: 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36' });
  p.on('response', async r => {
    const u = r.url();
    if (!/\/rest\/(stat|filters)\//.test(u)) return;
    let body = ''; try { body = await r.text(); } catch (e) {}
    console.log('REST', r.request().method(), u, 'POST:', (r.request().postData() || '').slice(0, 600), 'HEADERS:', JSON.stringify(r.request().headers()).slice(0, 500));
    console.log('RESP', u, body.length, body.slice(0, 3500));
  });
  await p.goto('https://www.khl.ru/stat/teams/1436/', { waitUntil: 'networkidle', timeout: 60000 });
  await p.waitForTimeout(3000);
  await b.close();
})();
