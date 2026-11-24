// Командная статистика всех клубов КХЛ с официального сайта khl.ru → константа LTS в index.html.
// Запуск (на GitHub, где khl.ru открывается в браузере): node .github/data/league_build.js index.html [--dry]
// Без ИИ. Читает обычные страницы статистики https://www.khl.ru/stat/teams/<сезон>/<раздел>/ в Playwright.
// Если хоть одна сверка не сходится — ничего не пишет и завершается с ошибкой (запуск краснеет).
const fs = require('fs');

const SEASON = 1436; // регулярный чемпионат 2026/27 на khl.ru
const SECTIONS = ['standings', 'home', 'road', 'first-period', 'second-period', 'third-period', 'overtime',
  'goals-for', 'goals-against', 'shots', 'games-actions', 'powerplay-gf'];
const NAMES = { 'Торпедо': 'Торпедо НН', 'Драконы': 'Шанхай Дрэгонс', 'ХК Сочи': 'Сочи' };

// ---------- разбор таблиц (без сети, проверяется тестом)
const code = h => String(h).trim().split(/\s+/)[0];
const num = v => { const s = String(v).trim().replace(',', '.'); return s === '' || s === '-' ? 0 : Number(s) };
const secs = v => { const m = String(v).trim().match(/^(\d+):(\d{2})$/); return m ? +m[1] * 60 + +m[2] : 0 };

// таблица раздела: head — заголовки столбцов, rows — строки ячеек; в строке после названия клуба идёт пустая ячейка
// (логотип), дальше значения по порядку заголовков, начиная со второго
function table(sec) {
  const keys = sec.head.map(code);
  const out = {};
  for (const r of sec.rows) {
    const name = NAMES[r[0]] || r[0];
    const o = {};
    for (let k = 1; k < keys.length; k++) o[keys[k]] = r[k + 1];
    out[name] = o;
  }
  return out;
}

function build(raw) {
  const T = {};
  for (const s of SECTIONS) {
    if (!raw[s] || !raw[s].rows || raw[s].rows.length < 22) throw new Error(`раздел ${s}: строк ${raw[s] && raw[s].rows ? raw[s].rows.length : 0}, нужно 22`);
    T[s] = table(raw[s]);
  }
  const teams = Object.keys(T.standings);
  const res = {};
  for (const n of teams) {
    const st = T.standings[n], g = T['goals-for'][n], ga = T['goals-against'][n], sh = T.shots[n], ac = T['games-actions'][n], pp = T['powerplay-gf'][n];
    for (const s of SECTIONS) if (!T[s][n]) throw new Error(`нет клуба «${n}» в разделе ${s}`);
    const side = x => [num(x['И']), num(x['В']), num(x['ВО']), num(x['ВБ']), num(x['О']), num(x['ЗШ']), num(x['ПШ'])];
    const per = s => [num(T[s][n]['ЗШ']), num(T[s][n]['ПШ'])];
    res[n] = {
      gp: num(st['И']), w: num(st['В']), otw: num(st['ВО']), sow: num(st['ВБ']), sol: num(st['ПБ']), otl: num(st['ПО']) + num(st['ПП']), l: num(st['П']),
      pts: num(st['О']), gf: num(st['ЗШ']), ga: num(st['ПШ']), pim: num(st['Штр']), pima: num(st['ШтрС']), so: num(st['И"0"']),
      h: side(T.home[n]), r: side(T.road[n]),
      p: [per('first-period'), per('second-period'), per('third-period'), per('overtime')],
      ppo: num(pp['Бол']), ppg: num(pp['ШБ']), shga: num(pp['ПШБ']), ppt: secs(pp['ВПБ']),
      pko: num(pp['Мен']), ppga: num(pp['ПШМ']), shg: num(pp['ШМ']), pkt: secs(pp['ВПМ']),
      ev: [num(g['5на5']), num(ga['5на5'])], en: num(g['ПВ']),
      sf: num(sh['БВ']), shp: num(sh['%БВ']),
      blk: num(ac['БлБ']), fow: num(ac['ВВбр']), fop: num(ac['%Вбр']), hits: num(ac['СПр']), tka: num(ac['ОТБ']), int: num(ac['ПХТ']), gva: num(ac['ПТР']),
      _ppp: num(pp['%Б']), _pkp: num(pp['%М']), _gfs: g, _gas: ga, _otl_en: num(st['ПП']),
    };
  }
  return res;
}

// ---------- сверки: каждая цифра должна сходиться сама с собой и по всей лиге
function validate(res, appTeams) {
  const bad = [];
  const names = Object.keys(res);
  if (names.length !== 22) bad.push(`клубов ${names.length}, нужно 22`);
  for (const t of appTeams) if (!res[t]) bad.push(`нет клуба приложения «${t}»`);
  for (const n of names) if (!appTeams.includes(n)) bad.push(`клуб «${n}» не найден в TEAMS`);
  const sum = k => names.reduce((s, n) => s + res[n][k], 0);
  for (const n of names) {
    const x = res[n];
    if (x.pts !== 2 * (x.w + x.otw + x.sow) + x.sol + x.otl) bad.push(`${n}: очки ${x.pts} ≠ 2×победы + поражения в ОТ/Б`);
    if (x.w + x.otw + x.sow + x.sol + x.otl + x.l !== x.gp) bad.push(`${n}: сумма исходов ≠ матчам`);
    if (x.h[0] + x.r[0] !== x.gp || x.h[5] + x.r[5] !== x.gf || x.h[6] + x.r[6] !== x.ga) bad.push(`${n}: дома + в гостях ≠ всего`);
    const pf = x.p.reduce((s, q) => s + q[0], 0), pa = x.p.reduce((s, q) => s + q[1], 0);
    if (pf > x.gf || x.gf - pf > x.sow || pa > x.ga || x.ga - pa > x.sol) bad.push(`${n}: голы по периодам ${pf}:${pa} не сходятся с ${x.gf}:${x.ga}`);
    if (x.ppg > x.ppo || x.ppga > x.pko) bad.push(`${n}: голов в большинстве больше, чем большинств`);
    if (x.ppo && Math.abs(x.ppg / x.ppo * 100 - x._ppp) > 0.15) bad.push(`${n}: % большинства ${x._ppp} ≠ ${x.ppg}/${x.ppo}`);
    if (x.pko && Math.abs((1 - x.ppga / x.pko) * 100 - x._pkp) > 0.15) bad.push(`${n}: % меньшинства ${x._pkp} ≠ 1 − ${x.ppga}/${x.pko}`);
    if (x.sf < x.gf - x.en - x.sow || x.sf > 60 * x.gp) bad.push(`${n}: броски ${x.sf} не похожи на правду`);
  }
  for (const [a, b] of [['gf', 'ga'], ['ppo', 'pko'], ['ppg', 'ppga'], ['shg', 'shga'], ['pim', 'pima'], ['w', 'l']]) {
    const sa = sum(a), sb = sum(b);
    // по лиге: большинства одних = меньшинства других, голы = пропущенные и т.д.
    if (a === 'w') { const W = names.reduce((s, n) => s + res[n].w, 0), L = names.reduce((s, n) => s + res[n].l, 0); if (W !== L) bad.push(`лига: побед в основное время ${W} ≠ поражений ${L}`); continue }
    if (sa !== sb) bad.push(`лига: ${a} ${sa} ≠ ${b} ${sb}`);
  }
  const OW = sum('otw') + sum('sow'), OL = sum('otl') + sum('sol');
  if (OW !== OL) bad.push(`лига: побед в ОТ/Б ${OW} ≠ поражений ${OL}`);
  return bad;
}

// ---------- запись в index.html: одна строка const LTS=… сразу после TEAMS
function write(html, res, date) {
  const clean = {};
  for (const [n, x] of Object.entries(res)) {
    const o = {};
    for (const [k, v] of Object.entries(x)) if (!k.startsWith('_')) o[k] = v;
    clean[n] = o;
  }
  const line = 'const LTS=' + JSON.stringify({ d: date, src: 'khl.ru', t: clean }) + ';';
  if (/^const LTS=.*;$/m.test(html)) return html.replace(/^const LTS=.*;$/m, () => line);
  const m = html.match(/^const TEAMS=.*;$/m);
  if (!m) throw new Error('не найдена строка const TEAMS=');
  return html.replace(m[0], () => m[0] + '\n' + line);
}

function appTeams(html) {
  const i = html.indexOf('const TEAMS=');
  const s = html.slice(i + 12, html.indexOf('\n', i));
  return JSON.parse(s.replace(/;\s*$/, '')).map(t => t[0]);
}

// ---------- сбор со страниц khl.ru
async function collect() {
  const { chromium } = require('playwright');
  const b = await chromium.launch();
  const p = await b.newPage({ locale: 'ru-RU', userAgent: 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36' });
  const raw = {};
  for (const s of SECTIONS) {
    const url = `https://www.khl.ru/stat/teams/${SEASON}/${s === 'standings' ? '' : s + '/'}`;
    let last;
    for (let i = 0; i < 3; i++) {
      try {
        await p.goto(url, { waitUntil: 'networkidle', timeout: 60000 });
        await p.waitForSelector('table tr td', { timeout: 30000 });
        raw[s] = await p.evaluate(() => {
          const t = document.querySelector('table');
          const cells = tr => [...tr.children].map(c => c.textContent.trim().replace(/\s+/g, ' '));
          const rows = [...t.querySelectorAll('tr')];
          return { head: cells(rows[0]), rows: rows.slice(1).map(cells).filter(r => r.length > 2) };
        });
        if (raw[s].rows.length >= 22) break;
      } catch (e) { last = e }
      await p.waitForTimeout(3000);
    }
    if (!raw[s]) throw new Error(`не открылся раздел ${s}: ${last}`);
    console.log('раздел', s, 'строк', raw[s].rows.length);
  }
  await b.close();
  return raw;
}

async function main() {
  const file = process.argv[2] || 'index.html';
  const dry = process.argv.includes('--dry');
  const html = fs.readFileSync(file, 'utf8');
  const raw = await collect();
  const res = build(raw);
  const bad = validate(res, appTeams(html));
  const S = res['Салават Юлаев'];
  console.log('Салават:', JSON.stringify(S && { gp: S.gp, gf: S.gf, ga: S.ga, pp: `${S.ppg}/${S.ppo}`, pk: `${S.ppga}/${S.pko}`, sf: S.sf, fop: S.fop, p: S.p }));
  if (bad.length) { console.log('НЕ СХОДИТСЯ:\n ' + bad.join('\n ')); process.exit(1) }
  const date = new Date(Date.now() + 5 * 3600e3).toISOString().slice(0, 10); // дата по Уфе
  const out = write(html, res, date);
  if (dry) { console.log('проверка пройдена, запись пропущена (--dry)'); return }
  fs.writeFileSync(file, out);
  console.log('LTS записана:', date, Object.keys(res).length, 'клубов');
}

module.exports = { build, validate, write, appTeams, table, SECTIONS };
if (require.main === module) main().catch(e => { console.error(e); process.exit(1) });
