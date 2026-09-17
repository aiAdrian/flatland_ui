#!/usr/bin/env node
// i18n coverage report (docs/plans/i18n-strategy.md). English is the reference;
// German and French may be partial by design, so this reports and never fails.
//   npm run i18n:coverage            per namespace
//   npm run i18n:coverage -- --missing   also list missing keys
import fs from 'node:fs';
import path from 'node:path';

const dir = path.resolve(import.meta.dirname, '../public/i18n');
const flat = (obj, prefix = '') =>
  Object.entries(obj).flatMap(([k, v]) =>
    v && typeof v === 'object' ? flat(v, `${prefix}${k}.`) : [`${prefix}${k}`]);
const load = (lang) => {
  const file = path.join(dir, `${lang}.json`);
  return fs.existsSync(file) ? new Set(flat(JSON.parse(fs.readFileSync(file, 'utf8')))) : new Set();
};

const en = load('en');
const targets = ['de', 'fr'];
const namespaces = [...new Set([...en].map((k) => k.split('.')[0]))].sort();
const showMissing = process.argv.includes('--missing');

const pad = (s, n) => String(s).padEnd(n);
console.log(pad('namespace', 14) + pad('en', 6) + targets.map((t) => pad(t, 12)).join(''));
for (const ns of namespaces) {
  const keys = [...en].filter((k) => k.split('.')[0] === ns);
  const cells = targets.map((t) => {
    const have = load(t);
    const n = keys.filter((k) => have.has(k)).length;
    return pad(`${n}/${keys.length} ${Math.round((100 * n) / keys.length)}%`, 12);
  });
  console.log(pad(ns, 14) + pad(keys.length, 6) + cells.join(''));
}
for (const t of targets) {
  const have = load(t);
  const missing = [...en].filter((k) => !have.has(k));
  const extra = [...have].filter((k) => !en.has(k));
  console.log(`\n${t}: ${en.size - missing.length}/${en.size} keys` + (extra.length ? ` · ${extra.length} not in en (stale?)` : ''));
  if (showMissing) missing.forEach((k) => console.log(`  missing ${k}`));
}
