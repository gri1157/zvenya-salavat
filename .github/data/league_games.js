// Протоколы ВСЕХ матчей регулярки КХЛ с khl.ru → кэш .github/data/league-games.json и константа LGM в index.html.
// Нужна для «Мы — они» с переключателем «Сезон / 10 / 5» и для «кто забил первым» у любого клуба.
// Запуск (на GitHub, где khl.ru открывается в браузере): node .github/data/league_games.js index.html [--max N] [--dry]
// Без ИИ. Каждый раз догружает только новые сыгранные матчи. Сверяет суммы с официальной таблицей LTS.
const fs = require('fs');
const path = require('path');

const SEASON = 1436;
const CACHE = path.join(__dirname, 'league-games.json');
const CACHE_V = 2; // меняется, когда меняется разбор: старый кэш тогда выбрасывается и всё собирается заново
const NAMES = { 'Торпедо': 'Торпедо НН', 'Драконы': 'Шанхай Дрэгонс', 'ХК Сочи': 'Сочи' };
const MON = { 'января': 1, 'февраля': 2, 'марта': 3, 'апреля': 4, 'мая': 5, 'июня': 6, 'июля': 7, 'августа': 8, 'сентября': 9, 'октября': 10, 'ноября': 11, 'декабря': 12 };
const nm = s => NAMES[s] || s;

// Разбор страницы протокола (выполняется внутри браузера) → сырые таблицы
function pageTables() {
  const capOf = t => { let cap = ''; let el = t; for (let k = 0; k < 6 && !cap; k++) { el = el.parentElement; const hh = el && el.querySelector('h2,h3,h4,.title,[class*=title]'); if (hh) cap = hh.innerText.trim(); } return cap; };
  const rows = t => [...t.rows].map(r => [...r.cells].map(c => c.innerText.replace(/\s+/g, ' ').trim()));
  return {
    title: document.title,
    tables: [...document.querySelectorAll('table')].map(t => ({ cap: capOf(t), cls: t.className, rows: rows(t) })).filter(t => !/^(Вратари|Защитники|Нападающие)$/.test(t.cap)),
  };
}

// Сырые таблицы → короткая запись матча (без сети, проверяется тестом)
function compact(id, raw, fin) {
  const T = raw.tables;
  const m = raw.title.match(/^(.+?) - (.+?): .*?(\d{1,2}) ([а-я]+) (\d{4})/);
  if (!m) throw new Error(`${id}: не разобран заголовок «${raw.title}»`);
  const h = nm(m[1].trim()), a = nm(m[2].trim());
  const d = `${m[5]}-${String(MON[m[4]]).padStart(2, '0')}-${m[3].padStart(2, '0')}`;
  const n = v => { const x = parseFloat(String(v).replace(',', '.')); return isNaN(x) ? 0 : x };
  // голы: счёт по ходу матча, период, кто первый
  const gt = T.find(t => t.cap === 'Заброшенные шайбы');
  // победный буллит тоже стоит в этой таблице, но не в периоде 1–4 — его не считаем, он есть в итоговом счёте
  // (у него номер периода 5 или время от 65:00 — овертайм в регулярке 5 минут)
  const goals = gt ? gt.rows.slice(1).filter(r => /^\d+:\d+$/.test(r[3] || '') && /^[1-4]$/.test(r[1] || '') && parseInt(r[2], 10) < 65) : [];
  const per = [[0, 0], [0, 0], [0, 0], [0, 0]];
  let ph = 0, pa = 0, fg = 0;
  for (const r of goals) {
    const [sh, sa] = r[3].split(':').map(Number);
    const side = sh > ph ? 0 : 1;
    if (!fg) fg = side === 0 ? 1 : 2;
    const p = Math.min(4, +r[1]) - 1;
    per[p][side]++;
    ph = sh; pa = sa;
  }
  // буллиты: итог серии добавляет победителю 1 гол
  const so = T.some(t => t.cap === 'Буллиты');
  // две таблицы подряд с одной подписью: первая — хозяева, вторая — гости
  const pair = cap => T.filter(t => t.cap === cap).slice(0, 2);
  const total = t => {
    // строки: заголовок, «первый период», цифры, «второй период», цифры, … — складываем только цифры под подписью
    // периода или овертайма (строку «всего» не берём, иначе броски задвоятся)
    if (!t) return null;
    const head = t.rows[0]; const sum = head.map(() => 0); let any = false;
    const R = t.rows.slice(1);
    R.forEach((r, j) => {
      const lab = j > 0 && R[j - 1].length === 1 ? R[j - 1][0] : '';
      if (r.length === head.length && r.every(c => /^[\d.:,-]*$/.test(c)) && /период|овертайм/i.test(lab)) { any = true; r.forEach((c, i) => { sum[i] += /:/.test(c) ? (c.split(':')[0] * 60 + +c.split(':')[1]) : n(c) }) }
    });
    return any ? Object.fromEntries(head.map((k, i) => [k, sum[i]])) : null;
  };
  const shots = pair('Броски по воротам').map(total), act = pair('Командные показатели').map(total);
  const ner = T.find(t => t.cap === 'В неравных составах');
  const nrow = team => { const r = ner && ner.rows.find(x => nm(x[0]) === team); const hd = ner && ner.rows[0]; return r ? Object.fromEntries(hd.map((k, i) => [k, r[i]])) : null };
  const nh = nrow(h), na = nrow(a);
  const all = T.find(t => t.cap === 'Все заброшенные шайбы');
  const en = team => { const r = all && all.rows.find(x => nm(x[0]) === team); const hd = all && all.rows[0]; return r ? n(r[hd.indexOf('ПВ')]) : 0 };
  const pim = cls => T.filter(t => (t.cls || '').includes(cls)).reduce((s, t) => s + t.rows.filter(r => /^\d+:\d{2}$/.test(r[0] || '')).reduce((q, r) => q + n(r[2]), 0), 0);
  const ot = per[3][0] + per[3][1] > 0 || goals.some(r => +r[1] >= 4);
  // итоговый счёт — с карточки календаря (в нём уже учтён победный буллит)
  const s2 = fin || [ph, pa];
  return {
    id: +id, d, h, a,
    s: s2, x: so ? 'Б' : ot ? 'ОТ' : '', fg, per,
    sh: [shots[0] ? shots[0]['БВ'] : null, shots[1] ? shots[1]['БВ'] : null],
    pp: [nh ? [n(nh['Бол']), n(nh['ШБ'])] : null, na ? [n(na['Бол']), n(na['ШБ'])] : null],
    pim: [pim('penalties-home'), pim('penalties-visitor')],
    blk: [act[0] ? act[0]['БлБ'] : null, act[1] ? act[1]['БлБ'] : null],
    hit: [act[0] ? act[0]['СПр'] : null, act[1] ? act[1]['СПр'] : null],
    en: [en(h), en(a)],
  };
}

// Проверка одной записи
function check(g) {
  const bad = [];
  const pf = g.per.reduce((s, p) => s + p[0], 0), pa = g.per.reduce((s, p) => s + p[1], 0);
  const sw = g.x === 'Б' ? (g.s[0] > g.s[1] ? [1, 0] : [0, 1]) : [0, 0]; // победный буллит в периоды не входит
  if (pf + sw[0] !== g.s[0] || pa + sw[1] !== g.s[1]) bad.push(`голы по периодам ${pf}:${pa} ≠ счёт ${g.s}`);
  if (g.x !== 'Б' && g.s[0] === g.s[1]) bad.push('ничья без буллитов');
  for (const i of [0, 1]) {
    if (g.sh[i] == null || g.pp[i] == null) bad.push('нет бросков или большинства');
    else if (g.sh[i] < g.s[i] - g.en[i] || g.sh[i] > 80) bad.push(`броски ${g.sh[i]} при ${g.s[i]} голах`);
    if (g.pp[i] && g.pp[i][1] > g.pp[i][0] + 1) bad.push('голов в большинстве больше, чем большинств');
  }
  return bad;
}

// Строка для index.html: LGM.c — названия столбцов, LGM.g — матчи
const COLS = ['d', 'h', 'a', 'hs', 'as', 'x', 'fg', 'hp1', 'ap1', 'hp2', 'ap2', 'hp3', 'ap3', 'hot', 'aot', 'hsh', 'ash', 'hppo', 'hppg', 'appo', 'appg', 'hpim', 'apim', 'hblk', 'ablk', 'hhit', 'ahit', 'hen', 'aen'];
function row(g) {
  return [g.d, g.h, g.a, g.s[0], g.s[1], g.x, g.fg, g.per[0][0], g.per[0][1], g.per[1][0], g.per[1][1], g.per[2][0], g.per[2][1], g.per[3][0], g.per[3][1],
    g.sh[0], g.sh[1], g.pp[0][0], g.pp[0][1], g.pp[1][0], g.pp[1][1], g.pim[0], g.pim[1], g.blk[0], g.blk[1], g.hit[0], g.hit[1], g.en[0], g.en[1]];
}
function write(html, games, date) {
  const list = Object.values(games).sort((x, y) => x.d.localeCompare(y.d) || x.id - y.id);
  const line = 'const LGM=' + JSON.stringify({ d: date, src: 'khl.ru', c: COLS, g: list.map(row) }) + ';';
  if (/^const LGM=.*;$/m.test(html)) return html.replace(/^const LGM=.*;$/m, () => line);
  const m = html.match(/^const LTS=.*;$/m) || html.match(/^const TEAMS=.*;$/m);
  return html.replace(m[0], () => m[0] + '\n' + line);
}

// Сверка с официальной таблицей: у кого число матчей совпало, суммы обязаны совпасть
function crossCheck(html, games) {
  const mm = html.match(/^const LTS=(.*);$/m);
  if (!mm) return [];
  const L = JSON.parse(mm[1]).t, sum = {}, bad = [];
  for (const g of Object.values(games)) for (const [i, t] of [[0, g.h], [1, g.a]]) {
    const o = sum[t] = sum[t] || { gp: 0, gf: 0, ga: 0, sf: 0, ppo: 0, ppg: 0, pim: 0 };
    o.gp++; o.gf += g.s[i]; o.ga += g.s[1 - i]; o.sf += g.sh[i]; o.ppo += g.pp[i][0]; o.ppg += g.pp[i][1]; o.pim += g.pim[i];
  }
  for (const [t, o] of Object.entries(sum)) {
    const x = L[t];
    if (!x) { bad.push(`клуб «${t}» не найден в LTS`); continue }
    if (x.gp !== o.gp) { console.log(`внимание: ${t}: в протоколах ${o.gp} матчей, в таблице ${x.gp} — сверку пропускаю`); continue }
    // голы в таблице считают победный буллит, в протоколе его нет — допускаем разницу на число побед по буллитам
    if (o.gf > x.gf || x.gf - o.gf > x.sow || o.ga > x.ga || x.ga - o.ga > x.sol) bad.push(`${t}: голы ${o.gf}:${o.ga} ≠ таблица ${x.gf}:${x.ga}`);
    if (o.ppo !== x.ppo || o.ppg !== x.ppg) bad.push(`${t}: большинство ${o.ppg}/${o.ppo} ≠ таблица ${x.ppg}/${x.ppo}`);
    // броски на сайте иногда правят задним числом в одной таблице и не правят в другой: до 1% разницы — только предупреждение
    if (Math.abs(o.sf - x.sf) > Math.max(3, x.sf * 0.01)) bad.push(`${t}: броски ${o.sf} ≠ таблица ${x.sf}`);
    else if (o.sf !== x.sf) console.log(`внимание: ${t}: броски по протоколам ${o.sf}, в таблице ${x.sf}`);
    if (o.pim !== x.pim) console.log(`внимание: ${t}: штрафные минуты ${o.pim} ≠ таблица ${x.pim}`);
  }
  return bad;
}

async function main() {
  const file = process.argv[2] || 'index.html';
  const dry = process.argv.includes('--dry');
  const mi = process.argv.indexOf('--max'); const MAX = mi > 0 ? +process.argv[mi + 1] : 400;
  const old = fs.existsSync(CACHE) ? JSON.parse(fs.readFileSync(CACHE, 'utf8')) : {};
  const games = old.v === CACHE_V ? old.g : {};
  const { chromium } = require('playwright');
  const b = await chromium.launch();
  const p = await b.newPage({ locale: 'ru-RU', userAgent: 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36', viewport: { width: 1400, height: 900 } });
  await p.goto(`https://www.khl.ru/calendar/${SEASON}/00/`, { waitUntil: 'networkidle', timeout: 90000 });
  await p.waitForSelector('li.match-card', { state: 'attached', timeout: 60000 });
  const cards = await p.evaluate(() => [...document.querySelectorAll('li.match-card')].map(c => ({ href: (c.querySelector('a[href*="/game/"]') || {}).getAttribute?.('href') || '', t: c.innerText.replace(/\s+/g, ' ') })));
  const fin = {};
  for (const c of cards) { const id = (c.href.match(/\/game\/\d+\/(\d+)/) || [])[1], sc = c.t.match(/(\d+) — (\d+)/); if (id && sc) fin[id] = [+sc[1], +sc[2]] }
  const played = Object.keys(fin);
  const todo = played.filter(id => !games[id]).slice(0, MAX);
  console.log(`сыграно ${played.length}, в кэше ${Object.keys(games).length}, догружаю ${todo.length}`);
  const fails = [];
  for (const id of todo) {
    let ok = false, err;
    for (let t = 0; t < 3 && !ok; t++) {
      try {
        await p.goto(`https://www.khl.ru/game/${SEASON}/${id}/protocol/`, { waitUntil: 'networkidle', timeout: 60000 });
        await p.waitForSelector('table', { state: 'attached', timeout: 30000 });
        await p.waitForTimeout(800);
        const g = compact(id, await p.evaluate(pageTables), fin[id]);
        const bad = check(g);
        if (bad.length) throw new Error(bad.join('; '));
        games[id] = g; ok = true;
      } catch (e) { err = e; await p.waitForTimeout(2000) }
    }
    if (!ok) { fails.push(`${id}: ${String(err).slice(0, 160)}`); }
  }
  await b.close();
  if (fails.length) console.log('не взял (попробую в следующий раз):\n ' + fails.join('\n '));
  fs.writeFileSync(CACHE, JSON.stringify({ v: CACHE_V, g: games })); // кэш сохраняем всегда — следующий запуск догрузит остальное
  const html = fs.readFileSync(file, 'utf8');
  const bad = crossCheck(html, games);
  if (bad.length) { console.log('НЕ СХОДИТСЯ С ТАБЛИЦЕЙ:\n ' + bad.join('\n ')); process.exit(1) }
  if (fails.length > 10) { console.log('слишком много ошибок, в приложение не пишу'); process.exit(1) }
  const date = new Date(Date.now() + 5 * 3600e3).toISOString().slice(0, 10);
  if (dry) { console.log('проверка пройдена, запись пропущена (--dry)'); return }
  fs.writeFileSync(file, write(html, games, date));
  console.log(`LGM записана: ${Object.keys(games).length} матчей`);
}

module.exports = { compact, check, write, crossCheck, COLS };
if (require.main === module) main().catch(e => { console.error(e); process.exit(1) });
