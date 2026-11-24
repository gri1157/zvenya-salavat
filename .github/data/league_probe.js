// Проба: где на khl.ru переключатели командной статистики. Ничего не меняет.
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ locale: 'ru-RU', userAgent: 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36' });
  const reqs = [];
  p.on('request', r => { const u = r.url(); if (/khl\.ru/.test(u) && !/\.(png|jpg|svg|css|woff2?|gif|webp)(\?|$)/.test(u)) reqs.push(r.method() + ' ' + u); });
  await p.goto('https://www.khl.ru/stat/teams/1436/', { waitUntil: 'networkidle', timeout: 60000 });
  await p.waitForTimeout(2500);
  const r = await p.evaluate(() => {
    const kw = /Брос|Больш|Меньш|Вбрас|Штраф|Период|Удален|Реализ|Нейтрал|Общ|Сэйв|Отраж/;
    return [...document.querySelectorAll('a,button,li,span,div,option,label')].filter(e => e.children.length <= 2 && kw.test(e.textContent) && e.textContent.trim().length < 50)
      .slice(0, 60).map(e => e.tagName + ' ' + e.textContent.trim().replace(/\s+/g, ' ') + ' :: ' + e.outerHTML.slice(0, 220).replace(/\s+/g, ' '));
  });
  console.log('NAV', JSON.stringify(r, null, 1));
  console.log('REQS', JSON.stringify(reqs.slice(0, 60), null, 1));
  await b.close();
})();
