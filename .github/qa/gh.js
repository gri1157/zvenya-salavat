// Мелкие помощники для работы с GitHub из скриптов команды.
const { execFileSync } = require('child_process');
const fs = require('fs');
const REPO = process.env.GITHUB_REPOSITORY;

function api(path, opts = {}) {
  const args = ['api', path];
  if (opts.method) args.push('-X', opts.method);
  let input;
  if (opts.body) { args.push('--input', '-'); input = JSON.stringify(opts.body); }
  const out = execFileSync('gh', args, { input, encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 });
  return out.trim() ? JSON.parse(out) : null;
}
function issues(q) { return api(`repos/${REPO}/issues?${q}&per_page=100`).filter(i => !i.pull_request); }
function ensureLabel(name, color) {
  try { api(`repos/${REPO}/labels`, { method: 'POST', body: { name, color } }); } catch (e) { /* уже есть */ }
}
function createIssue(title, body, labels) {
  labels.forEach(l => ensureLabel(l, LABEL_COLORS[l] || 'ededed'));
  return api(`repos/${REPO}/issues`, { method: 'POST', body: { title, body, labels } });
}
function comment(n, body) { return api(`repos/${REPO}/issues/${n}/comments`, { method: 'POST', body: { body } }); }
function addLabels(n, labels) {
  labels.forEach(l => ensureLabel(l, LABEL_COLORS[l] || 'ededed'));
  return api(`repos/${REPO}/issues/${n}/labels`, { method: 'POST', body: { labels } });
}
const LABEL_COLORS = {
  'bug': 'd73a4a', 'sev-critical': 'b60205', 'sev-major': 'd93f0b', 'sev-minor': 'fbca04',
  'in-progress': '1d76db', 'qa-report': 'c5def5', 'qa-lite': 'bfdadc', 'qa-pro': 'bfd4f2',
  'qa-critic': 'f9d0c4', 'fix': '0e8a16', 'review-ok': '0e8a16', 'review-rework': 'e99695',
  'council': '5319e7', 'data-check': 'fef2c0',
};
const SEV = { 'критично': 'sev-critical', 'важно': 'sev-major', 'мелочь': 'sev-minor' };
const SEV_ORDER = { 'sev-critical': 0, 'sev-major': 1, 'sev-minor': 2 };
const readJSON = (f, d) => { try { return JSON.parse(fs.readFileSync(f, 'utf8')); } catch (e) { return d; } };
const today = () => new Date().toLocaleDateString('ru-RU', { timeZone: 'Asia/Yekaterinburg' });
module.exports = { api, issues, createIssue, comment, addLabels, ensureLabel, SEV, SEV_ORDER, readJSON, today, REPO };
