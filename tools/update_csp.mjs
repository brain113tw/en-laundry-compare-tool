/** Developer tool only. End users do not need Node.js. */
import {readFileSync, writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
const path = new URL('../index.html', import.meta.url);
const raw = readFileSync(path, 'utf8');
const text = raw.replace(/\r\n?/g, '\n');
const scripts = [...text.matchAll(/<script>([\s\S]*?)<\/script>/g)];
if (scripts.length !== 1) throw new Error('Expected exactly one inline script. Update this tool if architecture changes.');
const hash = createHash('sha256').update(scripts[0][1], 'utf8').digest('base64');
const directive = `script-src 'sha256-${hash}'`;
const updated = text.replace(/script-src\s+'sha256-[^']+'/, directive);
if (!updated.includes(directive)) throw new Error('CSP script hash directive not found.');
if (process.argv.includes('--check')) {
  if (updated !== text || raw !== text) { console.error('CSP hash / LF newlines need update.'); process.exit(1); }
  console.log('CSP hash verified:', hash);
} else { writeFileSync(path, updated, 'utf8'); console.log('CSP hash updated:', hash); }
