// Сбор официальных протоколов сайта КХЛ для «Звеньев Салавата».
// Выполнять в браузере на открытой странице https://www.khl.ru/ (тот же сайт, чтобы читать страницы через скрытый iframe).
// 1) Вставить весь этот файл и выполнить.
// 2) await zvKHLGames()  -> список матчей Салавата: [{id, date:"ДД.ММ", score, played}]
// 3) await zvKHL([id1,id2])  -> JSON-строка {"ND":{номер:имя}, "C":[...]} для .github/khl/kp_update.py
// Сайт рисует таблицы скриптом, поэтому fetch не годится — только iframe.

window.zvLoad = (url, ms = 30000) => new Promise((res, rej) => {
  const f = document.createElement('iframe');
  f.style.cssText = 'position:fixed;left:-5000px;top:0;width:1400px;height:900px';
  f.src = url;
  const to = setTimeout(() => { rej('timeout'); f.remove(); }, ms);
  f.onload = () => { clearTimeout(to); setTimeout(() => res(f), 800); };
  document.body.appendChild(f);
});

window.zvExtract = (d, id) => {
  const ts = [...d.querySelectorAll('table')];
  const capOf = t => { let cap = ''; let el = t; for (let k = 0; k < 6 && !cap; k++) { el = el.parentElement; const hh = el && el.querySelector('h2,h3,h4,.title,[class*=title]'); if (hh) cap = hh.innerText.trim(); } return cap; };
  const rows = t => [...t.rows].map(r => [...r.cells].map(c => c.innerText.replace(/\s+/g, ' ').trim()));
  const o = { id, team: {}, pl: [], goals: null, so: null, pen: {} };
  const g0 = ts.find(t => /Заброшенные шайбы/.test(capOf(t))); if (g0) o.goals = rows(g0);
  const so = ts.find(t => /Буллиты/.test(capOf(t))); if (so) o.so = rows(so);
  const ph = d.querySelector('table.penalties-home'), pv = d.querySelector('table.penalties-visitor');
  if (ph) o.pen.h = rows(ph); if (pv) o.pen.a = rows(pv);
  ts.forEach(t => {
    const c = capOf(t);
    if (/^(Вратари|Защитники|Нападающие)$/.test(c)) o.pl.push([c, rows(t)]);
    else if (/неравных|Все заброшенные|Все пропущенные|Броски по воротам|Командные показатели|Время владения|Время на льду/.test(c)) (o.team[c] = o.team[c] || []).push(rows(t));
  });
  o.title = d.title;
  return o;
};

window.zvKHLGames = async () => {
  const f = await zvLoad('/calendar/1436/00/');
  const d = f.contentDocument;
  const sal = [...d.querySelectorAll('li.match-card')].filter(c => /Салават/.test(c.innerText));
  const out = sal.map(c => {
    const a = (c.querySelector('a[href*="/game/"]') || {}).getAttribute?.('href') || '';
    const id = (a.match(/\/game\/1436\/(\d+)/) || [])[1];
    const t = c.innerText.replace(/\s+/g, ' ').trim();
    const sc = (t.match(/(\d+) — (\d+)/) || []).slice(1).join(':');
    const dm = t.match(/(\d{1,2})\.(\d{2})/);
    return { id, date: dm ? dm[1].padStart(2, '0') + '.' + dm[2] : '', score: sc, played: !!sc, text: t.slice(0, 90) };
  });
  f.remove();
  return out;
};

const zvCompact = o => {
  const MON = { 'января': 1, 'февраля': 2, 'марта': 3, 'апреля': 4, 'мая': 5, 'июня': 6, 'июля': 7, 'августа': 8, 'сентября': 9, 'октября': 10, 'ноября': 11, 'декабря': 12 };
  const sec = t => { if (!t || t === '-') return 0; const p = t.split(':').map(Number); return p.length == 2 ? p[0] * 60 + p[1] : 0; };
  const num = s => { const n = parseFloat(String(s).replace(',', '.')); return isNaN(n) ? null : n; };
  const m = o.title.match(/(\d+) ([а-я]+) (\d{4})/);
  const date = m ? (m[1].padStart(2, '0') + '.' + String(MON[m[2]]).padStart(2, '0')) : '';
  const hdr = o.goals ? o.goals[0] : []; const home = hdr[7], away = hdr[8]; const H = home === 'Салават Юлаев'; const opp = H ? away : home;
  const pl = o.pl; const us = H ? pl.slice(0, 3) : pl.slice(3, 6); const them = H ? pl.slice(3, 6) : pl.slice(0, 3);
  const P = [];
  for (const [cap, R] of us) {
    if (cap === 'Вратари') continue; const pos = cap === 'Защитники' ? 'D' : 'F';
    for (const r of R.slice(1)) {
      if (r.length < 39) continue;
      P.push([+r[1], r[0], pos, +r[3], +r[4], +r[6], +r[7], +r[8], +r[9], +r[11], +r[12], +r[16], +r[18], +r[19], sec(r[21]), num(r[22]), sec(r[23]), sec(r[25]), sec(r[27]), sec(r[29]), +r[31], +r[32], sec(r[33]), +r[34], +r[35], num(r[36]), num(r[37]), num(r[38])]);
    }
  }
  const GK = []; for (const [cap, R] of us) { if (cap !== 'Вратари') continue; for (const r of R.slice(1)) GK.push([+r[1], r[0], +r[6], +r[7], sec(r[15]), +r[3], +r[4]]); }
  const GKT = []; for (const [cap, R] of them) { if (cap !== 'Вратари') continue; for (const r of R.slice(1)) GKT.push([+r[1], r[0], +r[6], +r[7], sec(r[15])]); }
  let ph = 0; const G = [];
  for (const r of (o.goals || []).slice(1)) {
    const sc = (r[3] || '').split(':').map(Number); let ourGoal; if (sc[0] > ph) ourGoal = H ? 1 : 0; else ourGoal = H ? 0 : 1; ph = sc[0];
    const nums = s => [...String(s).matchAll(/№(\d+)/g)].map(x => +x[1]); const sco = nums(r[5])[0] || 0; const as = nums(r[6]);
    const onUs = (H ? r[7] : r[8]) || ''; const onTh = (H ? r[8] : r[7]) || '';
    G.push([+r[1], sec(r[2]), ourGoal, r[4], sco, as[0] || 0, as[1] || 0, onUs, onTh]);
  }
  const T = o.team; const side = (k, i) => { const a = T[k]; if (!a) return null; const t = a[H ? i : 1 - i]; if (!t) return null; return t[t.length - 1]; };
  const tm = {}; for (const k of ['Командные показатели', 'Время владения шайбой и пройденная дистанция', 'Время на льду', 'Броски по воротам']) tm[k] = [side(k, 0), side(k, 1)];
  const ner = T['В неравных составах'] ? T['В неравных составах'][0].slice(1) : null;
  return { id: +o.id, date, opp, h: H ? 1 : 0, P, GK, GKT, G, tm, ner, so: o.so ? o.so.slice(1) : null };
};

window.zvKHL = async ids => {
  const C = [], ND = {}, log = [];
  for (const id of ids) {
    let ok = false;
    for (let t = 0; t < 3 && !ok; t++) {
      try {
        const f = await zvLoad('/game/1436/' + id + '/protocol/', 30000);
        await new Promise(r => setTimeout(r, 2500));
        const g = zvCompact(zvExtract(f.contentDocument, id));
        f.remove();
        for (const p of g.P) ND[p[0]] = p[1];
        for (const k of g.GK) ND[k[0]] = k[1];
        g.P = g.P.map(p => [p[0], ...p.slice(2)]);
        g.GK = g.GK.map(k => [k[0], ...k.slice(2)]);
        C.push(g); ok = true; log.push(id + ': ' + g.date + ' игроков ' + g.P.length);
      } catch (e) { log.push(id + ': ошибка ' + e); await new Promise(r => setTimeout(r, 3000)); }
    }
  }
  console.log(log.join('\n'));
  return JSON.stringify({ ND, C });
};
