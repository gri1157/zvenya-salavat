// Очки «Моей игры» для Телеграм-версии: берёт закрытые прогнозы с сервера,
// считает их той же функцией, что и приложение (scorePick), и пишет .github/data/results.json.
// Сервер забирает этот файл с GitHub и рассылает участникам итоги матча.
// Запуск: node .github/qa/score.js [index.html]
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

(async () => {
  const host = process.env.SCORE_HOST || fs.readFileSync('.github/server/host.txt', 'utf8').trim();
  const res = await fetch(host + '/api/public/seal');
  if (!res.ok) throw new Error('сервер ответил ' + res.status);
  const seal = await res.json(); // {дата: {псевдоним: прогноз}}
  const src = path.resolve(process.argv[2] || 'index.html');
  let html = fs.readFileSync(src, 'utf8');
  if (!/^\s*<!doctype/i.test(html)) html = '<!doctype html><html lang="ru"><head><meta charset="utf-8"></head><body>' + html + '</body></html>';
  const tmp = path.join(path.dirname(src), '.score-page.html');
  fs.writeFileSync(tmp, html);
  const b = await chromium.launch();
  const pg = await b.newPage();
  await pg.route(/fonts\.(googleapis|gstatic)/, r => r.abort());
  await pg.goto('file://' + tmp + '#board');
  await pg.waitForTimeout(800);
  const out = await pg.evaluate(seal => {
    const r = {};
    for (const [d, picks] of Object.entries(seal)) {
      const g = GAMES.find(z => z.d === d);
      if (!g) continue; // матч ещё не внесён в статистику
      const m = { o: g.o, h: g.h ? 1 : 0, gf: g.gf, ga: g.ga, x: g.x || '', s: {} };
      for (const [pid, pk] of Object.entries(picks)) {
        const s = scorePick(d, pk);
        if (s) m.s[pid] = { mgr: s.mgr, coach: s.coach, agent: s.agent, tot: s.tot, gf: +pk.gf, ga: +pk.ga, w: pk.w };
      }
      r[d] = m;
    }
    return r;
  }, seal);
  await b.close();
  fs.unlinkSync(tmp);
  const file = '.github/data/results.json';
  const prev = fs.existsSync(file) ? fs.readFileSync(file, 'utf8') : '';
  const next = JSON.stringify(out, null, 1) + '\n';
  if (prev !== next) { fs.writeFileSync(file, next); console.log('обновлено:', Object.keys(out).join(', ') || 'матчей нет'); }
  else console.log('без изменений');
})().catch(e => { console.error(e.message); process.exit(1); });
