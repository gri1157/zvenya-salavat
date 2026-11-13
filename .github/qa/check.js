// Автопроверка приложения без ИИ.
// Запуск: node .github/qa/check.js [путь к index.html] [папка для скриншотов]
// Проверяет: ошибки страницы, selfChecks(), горизонтальную прокрутку на 390 px во всех вкладках Lite и Pro.
// Печатает JSON и выходит с кодом 1, если есть проблемы.
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const src = path.resolve(process.argv[2] || 'index.html');
const shots = process.argv[3] || '';
const LITE = ['board', 'game', 'games', 'table', 'leaders', 'players'];
const PRO = ['board', 'game', 'plan', 'rival', 'sched', 'toi', 'form', 'special', 'leaders', 'players', 'settings', 'method'];

(async () => {
  let html = fs.readFileSync(src, 'utf8');
  if (!/^\s*<!doctype/i.test(html)) html = '<!doctype html><html lang="ru"><head><meta charset="utf-8"></head><body>' + html + '</body></html>';
  const tmp = path.join(path.dirname(src), '.qa-page.html');
  fs.writeFileSync(tmp, html);
  const url = 'file://' + tmp;
  const res = { file: src, errors: [], failedChecks: [], overflow: [], ok: true };
  const b = await chromium.launch();
  const pg = await b.newPage({ viewport: { width: 390, height: 844 } });
  pg.on('pageerror', e => res.errors.push(e.message));
  await pg.route(/fonts\.(googleapis|gstatic)/, r => r.abort());
  await pg.goto(url + '#board');
  await pg.waitForTimeout(800);
  try {
    res.failedChecks = await pg.evaluate(() => (typeof selfChecks === 'function' ? selfChecks() : []).filter(c => !c.ok).map(c => c.t || c.name || JSON.stringify(c)));
  } catch (e) { res.errors.push('selfChecks: ' + e.message); }
  for (const [ui, views] of [['lite', LITE], ['pro', PRO]]) {
    await pg.goto(url + '#board');
    await pg.waitForTimeout(400);
    await pg.click(`[data-uiset="${ui}"]`).catch(() => {});
    await pg.click('[data-roleset="coach"]').catch(() => {});
    for (const v of views) {
      await pg.goto(url + '#' + v);
      await pg.waitForTimeout(350);
      const w = await pg.evaluate(() => document.documentElement.scrollWidth);
      if (w > 391) res.overflow.push(`${ui}/${v}: ширина ${w}`);
      if (shots) { fs.mkdirSync(shots, { recursive: true }); await pg.screenshot({ path: path.join(shots, `${ui}-${v}.png`) }); }
    }
  }
  await b.close();
  fs.unlinkSync(tmp);
  res.ok = !res.errors.length && !res.failedChecks.length && !res.overflow.length;
  console.log(JSON.stringify(res, null, 1));
  process.exit(res.ok ? 0 : 1);
})();
