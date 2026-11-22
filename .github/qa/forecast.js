// Журнал прогнозов модели. Без ИИ.
// Запуск: node .github/qa/forecast.js index.html .github/data/forecast-log.json
// Берёт у приложения вероятность победы «Салавата» в ближайшем матче (salSchedule()),
// записывает в журнал и обновляет её каждый день, пока не наступил день матча (по UTC).
// В день матча и позже прогноз заморожен: подгонять под результат нельзя.
// Когда матч появляется в GAMES, в запись вносится итог. Зеркало журнала кладётся в index.html константой FCL.
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const src = path.resolve(process.argv[2] || 'index.html');
const logp = path.resolve(process.argv[3] || '.github/data/forecast-log.json');
(async () => {
  let html = fs.readFileSync(src, 'utf8');
  const wrapped = '<!doctype html><html lang="ru"><head><meta charset="utf-8"></head><body>' + html + '</body></html>';
  const tmp = path.join(path.dirname(src), '.fc-page.html');
  fs.writeFileSync(tmp, wrapped);
  const b = await chromium.launch();
  const pg = await b.newPage({ viewport: { width: 390, height: 844 } });
  const errs = [];
  pg.on('pageerror', e => errs.push(e.message));
  await pg.route(/fonts\.(googleapis|gstatic)/, r => r.abort());
  await pg.goto('file://' + tmp + '#board');
  await pg.waitForTimeout(800);
  const data = await pg.evaluate(() => {
    const s = salSchedule();
    const r = s.rows[0];
    return {
      next: r ? { d: r.d, o: r.o, h: r.h ? 1 : 0, pw: r.p.win, lS: r.lS, lO: r.lO, gk: r.gk ? r.gk.name : null } : null,
      games: GAMES.map(g => ({ d: g.d, o: g.o, gf: +g.gf, ga: +g.ga, win: g.r === 'W' }))
    };
  });
  await b.close();
  fs.unlinkSync(tmp);
  if (errs.length) { console.error('ошибки страницы:', errs.join('; ')); process.exit(1); }
  const today = new Date().toISOString().slice(0, 10);
  let log = JSON.parse(fs.readFileSync(logp, 'utf8'));
  const by = Object.fromEntries(log.map(e => [e.d, e]));
  const n = data.next;
  let changed = [];
  if (n && n.d > today && !(by[n.d] && by[n.d].res)) {
    const e = { d: n.d, o: n.o, h: n.h, pw: Math.round(n.pw * 1000) / 1000, lS: Math.round(n.lS * 100) / 100, lO: Math.round(n.lO * 100) / 100, gk: n.gk, at: today, res: null };
    const old = by[n.d];
    if (!old || old.pw !== e.pw || old.gk !== e.gk) { by[n.d] = e; changed.push('прогноз ' + n.d + ' ' + n.o + ' ' + e.pw); }
  }
  data.games.forEach(g => {
    const e = by[g.d];
    if (e && !e.res) { e.res = { gf: g.gf, ga: g.ga, win: g.win }; changed.push('итог ' + g.d + ' ' + g.gf + ':' + g.ga); }
  });
  log = Object.values(by).sort((a, b) => a.d.localeCompare(b.d));
  fs.writeFileSync(logp, JSON.stringify(log, null, 1) + '\n');
  // зеркало в index.html
  const line = 'const FCL=' + JSON.stringify(log) + ';';
  let h = fs.readFileSync(src, 'utf8');
  if (/^const FCL=.*;$/m.test(h)) h = h.replace(/^const FCL=.*;$/m, () => line);
  else h = h.replace(/^const AH=/m, () => line + '\nconst AH=');
  if (h !== fs.readFileSync(src, 'utf8')) { fs.writeFileSync(src, h); changed.push('index.html'); }
  console.log(changed.length ? 'изменено: ' + changed.join(', ') : 'без изменений');
})();
