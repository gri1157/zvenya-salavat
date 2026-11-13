// Шаги команды между вызовами ИИ. Запуск: node .github/qa/steps.js <шаг>
const fs = require('fs');
const { execSync } = require('child_process');
const G = require('./gh.js');
const step = process.argv[2];
const RUN = `${process.env.GITHUB_SERVER_URL}/${G.REPO}/actions/runs/${process.env.GITHUB_RUN_ID}`;
const sevOf = i => (i.labels || []).map(l => l.name).find(n => n in G.SEV_ORDER) || 'sev-minor';

if (step === 'tester-issue') {
  // отчёт тестировщика -> задача qa-report
  const who = process.argv[3];
  let body = fs.existsSync('report.md') ? fs.readFileSync('report.md', 'utf8') : '';
  const title = (body.split('\n')[0] || `# Тестировщик ${who} не дописал отчёт`).replace(/^#\s*/, '') + ' · ' + G.today();
  body = (body || 'Отчёт не получен.') + `\n\n---\nСкриншоты и файлы: ${RUN} (раздел Artifacts)`;
  G.createIssue(title, body, ['qa-report', `qa-${who}`]);
}

if (step === 'open-bugs') {
  const open = G.issues('labels=bug&state=open').map(i => ({ number: i.number, title: i.title, body: (i.body || '').slice(0, 3000) }));
  fs.writeFileSync('qa-open-bugs.json', JSON.stringify(open, null, 1));
  console.log('открытых ошибок:', open.length);
}

if (step === 'critic-apply') {
  // подтверждённые ошибки -> отдельные задачи bug, повторы -> комментарий
  const c = G.readJSON('critic.json', { confirmed: [], rejected: [] });
  const made = [];
  for (const b of c.confirmed || []) {
    if (b.existing) { try { G.comment(b.existing, `Ошибка повторилась при проверке ${G.today()}.\n\n${b.body || ''}`); made.push(`#${b.existing} (повтор)`); } catch (e) { } continue; }
    const sev = G.SEV[b.severity] || 'sev-minor';
    const i = G.createIssue(`${b.title}`, `**Важность:** ${b.severity || 'мелочь'}\n\n${b.body || ''}\n\n---\nПодтвердил критик ${G.today()}. Прогон: ${RUN}`, ['bug', sev]);
    made.push(`#${i.number} ${b.title}`);
  }
  let rep = fs.existsSync('report.md') ? fs.readFileSync('report.md', 'utf8') : '# Критик не дописал отчёт';
  const title = rep.split('\n')[0].replace(/^#\s*/, '') + ' · ' + G.today();
  rep += `\n\n---\n**Заведено и отмечено:**\n${made.map(x => '- ' + x).join('\n') || '- ничего'}\n\nПрогон: ${RUN}`;
  G.createIssue(title, rep, ['qa-critic']);
}

if (step === 'fix-queue') {
  const q = G.issues('labels=bug&state=open').filter(i => !(i.labels || []).some(l => l.name === 'in-progress'))
    .sort((a, b) => G.SEV_ORDER[sevOf(a)] - G.SEV_ORDER[sevOf(b)] || a.number - b.number).slice(0, 5)
    .map(i => ({ number: i.number, title: i.title, body: (i.body || '').slice(0, 4000) }));
  fs.writeFileSync('qa-fix-queue.json', JSON.stringify(q, null, 1));
  fs.appendFileSync(process.env.GITHUB_OUTPUT, `count=${q.length}\n`);
  console.log('в очереди:', q.map(x => '#' + x.number).join(' '));
}

if (step === 'fix-pr') {
  // исправление -> ветка и pull request
  const f = G.readJSON('fix.json', { fixed: [], skipped: [] });
  const changed = execSync('git status --porcelain index.html').toString().trim();
  const out = m => fs.appendFileSync(process.env.GITHUB_OUTPUT, m + '\n');
  for (const s of f.skipped || []) { try { G.comment(s.number, `Исправитель пропустил ${G.today()}: ${s.why}`); } catch (e) { } }
  if (!changed || !(f.fixed || []).length) { console.log('исправлений нет'); out('pr='); return; }
  let ok = true;
  try { execSync('node .github/qa/check.js index.html', { stdio: 'inherit' }); } catch (e) { ok = false; }
  if (!ok) { console.log('автопроверка не прошла, PR не создаю'); (f.fixed || []).forEach(n => { try { G.comment(n, `Попытка исправления ${G.today()} не прошла автопроверку и отменена. Прогон: ${RUN}`); } catch (e) { } }); out('pr='); return; }
  const br = `fix/${process.env.GITHUB_RUN_ID}`;
  execSync(`git config user.name "Claude" && git config user.email "noreply@anthropic.com"`);
  // шаг ИИ меняет настройки входа git, поэтому возвращаем токен прогона явно
  execSync(`git config --local --unset-all http.https://github.com/.extraheader || true`, { shell: '/bin/bash' });
  execSync(`git remote set-url origin https://x-access-token:${process.env.GH_TOKEN}@github.com/${G.REPO}.git`);
  execSync(`git checkout -b ${br} && git add index.html && git commit -m "Исправление ${f.fixed.map(n => '#' + n).join(', ')}" && git push origin ${br}`, { stdio: 'inherit' });
  const rep = fs.existsSync('fix-report.md') ? fs.readFileSync('fix-report.md', 'utf8') : '# Исправление';
  const title = rep.split('\n')[0].replace(/^#\s*/, '');
  const body = rep + `\n\n---\n${f.fixed.map(n => `Closes #${n}`).join('\n')}\n\nПрогон: ${RUN}`;
  const pr = G.api(`repos/${G.REPO}/pulls`, { method: 'POST', body: { title, body, head: br, base: 'main' } });
  G.addLabels(pr.number, ['fix']);
  f.fixed.forEach(n => { try { G.addLabels(n, ['in-progress']); } catch (e) { } });
  out(`pr=${pr.number}`); out(`branch=${br}`);
  console.log('PR', pr.html_url);
}

if (step === 'review-prep') {
  // материалы для проверяющего
  const pr = process.argv[3];
  fs.mkdirSync('qa-review', { recursive: true });
  execSync('git fetch origin main --depth=50');
  execSync('git diff origin/main -- index.html > qa-review/diff.txt');
  execSync('git show origin/main:index.html > qa-review/index-before.html');
  const p = G.api(`repos/${G.REPO}/pulls/${pr}`);
  fs.writeFileSync('qa-review/fix-report.md', p.body || '');
  const nums = [...(p.body || '').matchAll(/Closes #(\d+)/g)].map(m => m[1]);
  fs.writeFileSync('qa-review/issues.md', nums.map(n => { const i = G.api(`repos/${G.REPO}/issues/${n}`); return `# #${n} ${i.title}\n\n${i.body}`; }).join('\n\n=====\n\n'));
  const consts = f => Object.fromEntries([...fs.readFileSync(f, 'utf8').matchAll(/^const ([A-Z][A-Z0-9_]*)=(.*)$/gm)].map(m => [m[1], m[2]]));
  const a = consts('qa-review/index-before.html'), b = consts('index.html');
  const ch = [...new Set([...Object.keys(a), ...Object.keys(b)])].filter(k => !['I18N', 'NAMES_EN'].includes(k) && a[k] !== b[k]);
  fs.writeFileSync('qa-review/data-changed.txt', ch.join('\n'));
  const run = f => { try { return execSync(`node .github/qa/check.js ${f}`).toString(); } catch (e) { return (e.stdout || '').toString(); } };
  fs.writeFileSync('qa-review/check-before.json', run('qa-review/index-before.html'));
  fs.writeFileSync('qa-review/check-after.json', run('index.html'));
}

if (step === 'review-post') {
  const pr = process.argv[3];
  const v = fs.existsSync('verdict.md') ? fs.readFileSync('verdict.md', 'utf8') : 'ВЕРДИКТ: доработать\n\nПроверяющий не дописал отчёт.';
  const ok = /^ВЕРДИКТ:\s*принять/m.test(v.split('\n')[0]);
  G.comment(pr, `## Проверяющий\n\n${v}\n\n---\nПрогон: ${RUN}`);
  G.addLabels(pr, [ok ? 'review-ok' : 'review-rework']);
}

if (step === 'week') {
  // всё за неделю для консилиума
  const since = new Date(Date.now() - 7 * 864e5).toISOString();
  const all = G.api(`repos/${G.REPO}/issues?state=all&since=${since}&per_page=100`);
  const lab = i => (i.labels || []).map(l => l.name);
  const sec = (t, arr, f) => `\n\n## ${t}\n\n` + (arr.length ? arr.map(f).join('\n\n') : 'нет');
  const short = i => `### #${i.number} ${i.title} (${i.state === 'open' ? 'открыто' : 'закрыто'})\n${(i.body || '').slice(0, 2500)}`;
  const prs = all.filter(i => i.pull_request).map(i => {
    const p = G.api(`repos/${G.REPO}/pulls/${i.number}`);
    const cm = G.api(`repos/${G.REPO}/issues/${i.number}/comments`).map(c => c.body).filter(b => b.includes('ВЕРДИКТ')).pop() || 'вердикта нет';
    return `### PR #${i.number} ${i.title}\nСостояние: ${p.merged_at ? 'принято' : p.state === 'open' ? 'ждёт решения' : 'закрыто без принятия'}\nСсылка: ${i.html_url}\n${(p.body || '').slice(0, 1500)}\n\nВердикт: ${cm.slice(0, 800)}`;
  });
  const iss = all.filter(i => !i.pull_request);
  let md = `# Неделя по ${G.today()}`;
  md += sec('Сверка данных', iss.filter(i => lab(i).includes('data-check')), short);
  md += sec('Исправления (pull requests)', prs, x => x);
  md += sec('Подтверждённые ошибки', iss.filter(i => lab(i).includes('bug')), i => `- #${i.number} ${i.title} — ${i.state === 'open' ? 'не исправлено' : 'закрыто'} (${lab(i).filter(l => l.startsWith('sev-')).join(', ')})`);
  md += sec('Отчёты критика', iss.filter(i => lab(i).includes('qa-critic')), short);
  md += sec('Отчёты тестировщиков', iss.filter(i => lab(i).includes('qa-report')), short);
  fs.writeFileSync('qa-week.md', md);
  const prev = G.issues('labels=council&state=all')[0];
  fs.writeFileSync('qa-prev-council.md', prev ? `# ${prev.title}\n\n${prev.body}` : '');
  console.log('qa-week.md:', md.length);
}

if (step === 'council-issue') {
  const c = fs.existsSync('council.md') ? fs.readFileSync('council.md', 'utf8') : '';
  if (c) G.createIssue(c.split('\n')[0].replace(/^#\s*/, ''), c, ['council']);
}
