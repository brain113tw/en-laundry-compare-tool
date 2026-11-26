/** Developer tool only. End users do not need Node.js.
 *
 * vendor/heic-decoder.html is the sandboxed helper page that decodes HEIC files with libheif (LGPL-3.0). It holds
 *   1. the unmodified wasm bundle of the npm package libheif-js, as an inert text block, and
 *   2. the glue script from tools/heic_decoder_glue.js, pinned by its SHA-256 in the page's own Content-Security-Policy.
 *
 *   node tools/build_heic_decoder.mjs <path to libheif-wasm/libheif-bundle.js>   build the page
 *   node tools/build_heic_decoder.mjs --check                                    verify the committed page
 *
 * To move to another libheif-js release: download it from npm, check it, then change LIB below on purpose.
 */
import {readFileSync, writeFileSync, mkdirSync} from 'node:fs';
import {createHash} from 'node:crypto';

const LIB = {name: 'libheif-js', version: '1.23.5', file: 'libheif-wasm/libheif-bundle.js', sha256: '074b2b55ef3de477ba9f794ca381f3f0324c1cba8c91b4af07395f39c22d54cc'};
const out = new URL('../vendor/heic-decoder.html', import.meta.url);
const glue = readFileSync(new URL('./heic_decoder_glue.js', import.meta.url), 'utf8');
const hex = text => createHash('sha256').update(text, 'utf8').digest('hex');
const b64 = text => createHash('sha256').update(text, 'utf8').digest('base64');

// Text placed inside a <script> element must not be able to end the element or change how it is parsed.
function embeddable(text, what) {
  for (const bad of ['</script', '<!--', '\r']) if (text.toLowerCase().includes(bad)) throw new Error(`${what} contains ${JSON.stringify(bad)} and cannot be embedded unchanged.`);
  return text;
}
function page(lib) {
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'sha256-${b64(glue)}' 'wasm-unsafe-eval'; worker-src blob:; base-uri 'none'; form-action 'none'">
<meta name="referrer" content="no-referrer">
<title>HEIC decoder (sandboxed helper)</title>
</head>
<body>
<p>This page is a helper of the En Laundry image tools. index.html loads it in a sandboxed frame to decode HEIC photos; it has no use on its own. It contains ${LIB.name} ${LIB.version} (libheif and libde265, LGPL-3.0), unmodified. See THIRD_PARTY_NOTICES.md next to this file.</p>
<script type="text/plain" id="libheif">${embeddable(lib, 'The library')}</script>
<script>${embeddable(glue, 'The glue script')}</script>
</body>
</html>
`;
}
function parts(html) {
  const lib = html.match(/<script type="text\/plain" id="libheif">([\s\S]*?)<\/script>/), code = html.match(/<script>([\s\S]*?)<\/script>/), csp = html.match(/script-src '(sha256-[^']+)'/);
  if (!lib || !code || !csp) throw new Error('vendor/heic-decoder.html does not have the expected structure.');
  return {lib: lib[1], code: code[1], csp: csp[1]};
}

if (process.argv.includes('--check')) {
  const html = readFileSync(out, 'utf8'), p = parts(html), problems = [];
  if (hex(p.lib) !== LIB.sha256) problems.push(`the library block is not ${LIB.name} ${LIB.version} (${LIB.file})`);
  if (p.code !== glue) problems.push('the glue script differs from tools/heic_decoder_glue.js');
  if (p.csp !== 'sha256-' + b64(p.code)) problems.push('the policy hash does not match the glue script');
  if (html !== page(p.lib)) problems.push('the page differs from what this tool writes');
  if (problems.length) { console.error('vendor/heic-decoder.html: ' + problems.join('; ') + '.'); process.exit(1); }
  console.log(`HEIC decoder page verified: ${LIB.name} ${LIB.version} sha256 ${LIB.sha256}, glue 'sha256-${b64(glue)}'.`);
} else {
  const src = process.argv[2];
  if (!src) throw new Error('Usage: node tools/build_heic_decoder.mjs <path to libheif-wasm/libheif-bundle.js>   (or --check)');
  const lib = readFileSync(src, 'utf8');
  if (hex(lib) !== LIB.sha256) throw new Error(`${src} has sha256 ${hex(lib)}, expected ${LIB.sha256} (${LIB.name} ${LIB.version}). Change LIB in this tool only after checking the new release.`);
  mkdirSync(new URL('../vendor/', import.meta.url), {recursive: true});
  writeFileSync(out, page(lib), 'utf8');
  console.log(`vendor/heic-decoder.html written: ${page(lib).length} bytes, glue 'sha256-${b64(glue)}'.`);
}
