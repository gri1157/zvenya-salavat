// Разбор последнего матча для Telegram: открывает само приложение (index.html) в браузере, берёт текст
// из razborTG() — тот же, что в разделе «Разбор матча», — и кладёт в .github/data/razbor.json.
// Сервер бота читает этот файл и утром рассылает разбор подписчикам «Матча онлайн».
// Запуск: node .github/data/razbor_export.js index.html
const fs = require('fs'), path = require('path');
const { chromium } = require('playwright');
(async () => {
  const file = path.resolve(process.argv[2] || 'index.html');
  const out = path.join(__dirname, 'razbor.json');
  const b = await chromium.launch();
  const p = await b.newPage();
  const errs = [];
  p.on('pageerror', e => errs.push(String(e)));
  await p.route('**/*', r => /^file:/.test(r.request().url()) ? r.continue() : r.abort());
  await p.goto('file://' + file + '#games');
  await p.waitForFunction(() => typeof razborTG === 'function', null, { timeout: 30000 });
  const r = await p.evaluate(() => razborTG());
  await b.close();
  if (errs.length) { console.log('ошибки страницы:', errs.join(' | ')); process.exit(1) }
  if (!r || !r.d || !r.text) { console.log('разбора нет'); return }
  const old = fs.existsSync(out) ? JSON.parse(fs.readFileSync(out, 'utf8')) : {};
  if (old.d === r.d && old.text === r.text && old.full === r.full) { console.log('разбор не изменился:', r.d); return }
  fs.writeFileSync(out, JSON.stringify({ d: r.d, full: r.full, text: r.text }, null, 1) + '\n');
  console.log('разбор записан:', r.d, r.full ? '(полный)' : '(без протокола игроков)');
  console.log(r.text);
})().catch(e => { console.error(e); process.exit(1) });
