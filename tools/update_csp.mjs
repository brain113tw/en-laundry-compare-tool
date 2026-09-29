/** Developer tool only. End users do not need Node.js. Mirrors tools/update_csp.py. */
import {readFileSync, writeFileSync, existsSync} from 'node:fs';
import {createHash} from 'node:crypto';
const path = new URL('../index.html', import.meta.url);
const mirror = new URL('../en_compare_manager_v6_2_toolbox.html', import.meta.url);
const raw = readFileSync(path, 'utf8');
const text = raw.replace(/\r\n?/g, '\n');
const scripts = [...text.matchAll(/<script>([\s\S]*?)<\/script>/g)];
if (!scripts.length) throw new Error('No inline <script> found. Update this tool if architecture changes.');
const hashes = scripts.map(m => `'sha256-${createHash('sha256').update(m[1], 'utf8').digest('base64')}'`);
const directive = `script-src ${hashes.join(' ')};`;
const updated = text.replace(/script-src [^;]+;/, directive);
if (!updated.includes(directive)) throw new Error('CSP script-src directive not found.');
const mirrorStale = existsSync(mirror) && readFileSync(mirror, 'utf8') !== updated;
if (process.argv.includes('--check')) {
  if (updated !== text || raw !== text || mirrorStale) { console.error('CSP hash / LF newlines / v6.2 mirror file need update.'); process.exit(1); }
  console.log('CSP hashes verified:', hashes.join(' '));
} else {
  writeFileSync(path, updated, 'utf8');
  if (existsSync(mirror)) writeFileSync(mirror, updated, 'utf8');
  console.log(`CSP updated with ${hashes.length} script hash(es); mirror file synchronized.`);
}
