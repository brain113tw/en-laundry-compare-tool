"""Developer regression checks for HEIC photos in browsers that cannot show them: the bundled decoder and its sandbox.

Needs Python, Playwright, Pillow and Chromium (set CHROMIUM_EXECUTABLE or have `chromium` on PATH).
End users never need this; the tool itself is index.html plus the vendor folder.

Unlike the other suites this one opens the real files, once from disk (file://) and once from a local web server,
because the decoder is a second page that has to be found next to index.html.
Fixtures are synthetic colour boards written by tests/make_heic_fixtures.py, never customer photos.
"""
from pathlib import Path
from playwright.sync_api import sync_playwright
from PIL import Image
import base64, functools, hashlib, http.server, io, json, os, re, shutil, tempfile, threading, time, zipfile

root = Path(__file__).resolve().parents[1]
fixtures = root / 'tests' / 'fixtures'
expected = json.loads((fixtures / 'heic_expected.json').read_text(encoding='utf-8'))['files']
work = Path(tempfile.mkdtemp(prefix='en-heic-tests-'))
print('Temporary test artifacts:', work)

results = []


def record(name, ok, detail=''):
    results.append({'test': name, 'passed': bool(ok), 'detail': str(detail)})
    print(('PASS ' if ok else 'FAIL ') + name, detail, flush=True)
    assert ok, (name, detail)


# ---------------------------------------------------------------- static checks: what is shipped
index_html = (root / 'index.html').read_text(encoding='utf-8')
decoder_html = (root / 'vendor' / 'heic-decoder.html').read_text(encoding='utf-8')
glue = (root / 'tools' / 'heic_decoder_glue.js').read_text(encoding='utf-8')
b64hash = lambda text: 'sha256-' + base64.b64encode(hashlib.sha256(text.encode('utf-8')).digest()).decode()
policy = re.findall(r'<meta http-equiv="Content-Security-Policy" content="([^"]*)">', decoder_html)
blocks = re.findall(r'<script([^>]*)>([\s\S]*?)</script>', decoder_html)
record('The decoder page allows only its own pinned script and WebAssembly: no network, no other code',
       len(policy) == 1 and policy[0] == "default-src 'none'; script-src '%s' 'wasm-unsafe-eval'; worker-src blob:; base-uri 'none'; form-action 'none'" % b64hash(glue), policy)
shell = decoder_html.replace(blocks[0][1], '').replace(blocks[1][1], '')      # the page without the two script bodies
record('The decoder page holds exactly the library as inert text and the reviewed glue script, and refers to nothing else',
       [b[0] for b in blocks] == [' type="text/plain" id="libheif"', ''] and blocks[1][1] == glue
       and not re.search(r'<(link|img|iframe|object|embed|form|a|base|style)\b|\s(src|href|on\w+|style)\s*=', shell, re.I), len(shell))
pinned = re.search(r"version: '([\d.]+)', file: '([^']+)', sha256: '([0-9a-f]{64})'", (root / 'tools' / 'build_heic_decoder.mjs').read_text(encoding='utf-8'))
record('The bundled library is the pinned, unmodified libheif-js build', hashlib.sha256(blocks[0][1].encode('utf-8')).hexdigest() == pinned.group(3), pinned.group(1))
main_policy = re.findall(r'<meta http-equiv="Content-Security-Policy" content="([^"]*)">', index_html)[0]
directives = {d.split()[0]: d.split()[1:] for d in main_policy.split(';') if d.strip()}
record('The main page gained only the permission to frame its own decoder page',
       directives['frame-src'] == ["'self'"] and directives['default-src'] == ["'none'"] and directives['connect-src'] == ["'none'"] and directives['worker-src'] == ["'none'"]
       and directives['object-src'] == ["'none'"] and all(s.startswith("'sha256-") for s in directives['script-src']) and 'eval' not in main_policy, main_policy[:60])
notices = root / 'vendor' / 'THIRD_PARTY_NOTICES.md'
licence = root / 'vendor' / 'LICENSE-libheif-js.txt'
record('The licence texts ship next to the decoder', notices.is_file() and licence.is_file() and 'LGPL' in notices.read_text(encoding='utf-8') and pinned.group(1) in notices.read_text(encoding='utf-8')
       and 'GNU LESSER GENERAL PUBLIC LICENSE' in licence.read_text(encoding='utf-8'))
for name, info in expected.items():
    assert hashlib.sha256((fixtures / name).read_bytes()).hexdigest() == info['sha256'], ('fixture changed without regenerating heic_expected.json', name)

# ---------------------------------------------------------------- the folders a user could end up with
site = work / 'site'                                   # the tool with its vendor folder
(site / 'vendor').mkdir(parents=True)
shutil.copy(root / 'index.html', site / 'index.html')
shutil.copy(root / 'vendor' / 'heic-decoder.html', site / 'vendor' / 'heic-decoder.html')
lone = work / 'lone'                                   # index.html copied somewhere on its own
lone.mkdir()
shutil.copy(root / 'index.html', lone / 'index.html')

SPY = '''<!doctype html><meta charset="utf-8"><script>
(async () => {
  const out = {origin: self.origin};
  const attempt = (key, run) => { try { out[key] = run(); } catch (e) { out[key] = e.name; } };
  attempt('parentDocument', () => { void parent.document.title; return 'reachable'; });
  attempt('parentWindow', () => { void parent.localStorage; return 'reachable'; });
  attempt('storage', () => { void localStorage.length; return 'reachable'; });
  attempt('cookie', () => { void document.cookie; return 'reachable'; });
  attempt('database', () => { indexedDB.open('x'); return 'reachable'; });
  attempt('popup', () => window.open('about:blank') ? 'opened' : 'blocked');
  attempt('top', () => { top.location.href = 'about:blank#taken'; return 'navigated'; });
  try { const r = await fetch(new URL('../index.html', location.href)); out.readTool = r.ok ? 'readable' : 'unreadable'; } catch (e) { out.readTool = 'blocked'; }
  parent.postMessage({type: 'spy', out}, '*');
  // Then try to leave for another site, taking data along. It never answers "ready".
  setTimeout(() => { location.href = '__LEAK__'; }, 200);
})();
</script>'''
LIAR = '''<!doctype html><meta charset="utf-8"><script>
addEventListener('message', e => {
  const m = e.data; if (!m || m.type !== 'decode') return;
  const px = n => new ArrayBuffer(n), say = extra => parent.postMessage({type: 'result', id: m.id, ok: true, opaque: true, colour: '', ...extra}, '*');
  switch (m.buffer.byteLength % 10) {
    case 0: return say({width: 10, height: 10, buffer: px(16)});            // fewer bytes than the size needs
    case 1: return say({width: 0, height: 10, buffer: px(0)});              // empty picture
    case 2: return say({width: 1000000, height: 1000000, buffer: px(16)});  // absurd size
    case 3: return say({width: 2.5, height: 2, buffer: px(20)});            // fractional size
    case 4: return say({width: 2, height: 2});                              // no pixels at all
    case 5: return say({width: 2, height: 2, buffer: 'AAAAAAAAAAAAAAAA'});  // pixels of the wrong type
    case 6: return say({width: -2, height: -2, buffer: px(16)});            // negative size
    case 7: return parent.postMessage({type: 'fatal', message: 'boom'}, '*');
    case 8: say({width: 2, height: 2, buffer: px(16), id: m.id + 1000}); return say({width: 3, height: 1, buffer: new Uint8Array([255, 0, 0, 255, 0, 255, 0, 255, 0, 0, 255, 255]).buffer});
    default: return say({width: 2, height: 2, buffer: new Uint8Array(16).fill(255).buffer});
  }
});
parent.postMessage({type: 'ready'}, '*');
</script>'''


LATE = '''<!doctype html><meta charset="utf-8"><script>
parent.postMessage({type: 'ready'}, '*');
addEventListener('message', e => { const m = e.data; if (!m || m.type !== 'decode') return;
  setTimeout(() => parent.postMessage({type: 'result', id: m.id, ok: true, opaque: true, colour: '', width: 2, height: 2, buffer: new Uint8Array(16).fill(255).buffer}, '*'), 9500); });
</script><img src="../slow.png" alt="">'''


class Quiet(http.server.SimpleHTTPRequestHandler):
    seen = None

    def log_message(self, *args):
        pass

    def do_GET(self):
        self.seen.append(self.path)
        if 'slow' in self.path:
            time.sleep(1.2)                               # keeps the page that asked for it from finishing its load
        super().do_GET()


def serve(folder):
    seen = []
    handler = functools.partial(type('Handler', (Quiet,), {'seen': seen}), directory=str(folder))
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, 'http://127.0.0.1:%d/' % server.server_address[1], seen


elsewhere = work / 'elsewhere'                          # stands for somebody else's web site
elsewhere.mkdir()
(elsewhere / 'leak.html').write_text('<!doctype html>leak', encoding='utf-8')
other_server, other_url, other_seen = serve(elsewhere)
for folder, page_text in (('spy', SPY.replace('__LEAK__', other_url + 'leak.html?photo-bytes')), ('liar', LIAR), ('late', LATE)):
    (work / folder / 'vendor').mkdir(parents=True)
    shutil.copy(root / 'index.html', work / folder / 'index.html')
    (work / folder / 'vendor' / 'heic-decoder.html').write_text(page_text, encoding='utf-8')
server, base_url, _ = serve(work)

HOOKS = '''() => {
  window.__dl = []; window.download = (blob, name) => { window.__dl.push({blob, name}); };
  window.__status = []; const say = status; status = (...a) => { window.__status.push(String(a[0])); return say(...a); };
  window.__heic = []; const decode = heicDecode; heicDecode = async f => { const r = await decode(f);
    const head = new Uint8Array(await r.blob.slice(0, 2048).arrayBuffer()); window.__heic.push({name: f.name, type: r.blob.type, size: r.blob.size, colour: r.colour, head: btoa(String.fromCharCode(...head))}); return r; };
  window.__frames = []; window.__violations = []; window.__spy = null;
  document.addEventListener('securitypolicyviolation', e => window.__violations.push({directive: e.effectiveDirective, blocked: e.blockedURI}));
  addEventListener('message', e => { if (e.data && e.data.type === 'spy') window.__spy = e.data.out; });
  new MutationObserver(list => { for (const m of list) {
    for (const n of m.addedNodes) if (n.tagName === 'IFRAME') {
      const box = n.getBoundingClientRect(), rec = {node: n, sandbox: n.getAttribute('sandbox'), src: n.src, visibility: getComputedStyle(n).visibility, area: box.width * box.height, messages: 0, origin: '', document: '', window: '', removed: false};
      window.__frames.push(rec);
      addEventListener('message', e => { if (e.source !== n.contentWindow) return; rec.messages++; rec.origin = e.origin;
        try { rec.document = n.contentDocument === null ? 'null' : 'reachable'; } catch (err) { rec.document = err.name; }
        try { void n.contentWindow.document; rec.window = 'reachable'; } catch (err) { rec.window = err.name; } });
    }
    for (const n of m.removedNodes) if (n.tagName === 'IFRAME') window.__frames.filter(r => r.node === n).forEach(r => r.removed = true);
  } }).observe(document.body, {childList: true});
}'''
FRAMES = "() => window.__frames.map(({node, ...rest}) => rest)"
SAMPLE = '''([name, points]) => { const it = S.items.find(i => i.file.name === name); if (!it) return null;
  const cv = document.createElement('canvas'); cv.width = it.w; cv.height = it.h; const g = cv.getContext('2d', {willReadFrequently: true}); g.drawImage(it.img, 0, 0);
  return {w: it.w, h: it.h, px: points.map(([x, y]) => Array.from(g.getImageData(x, y, 1, 1).data))}; }'''


def status(page):
    return page.locator('#status').text_content()


def is_error(page):
    return 'error' in (page.locator('#status').get_attribute('class') or '')


def log_text(page):
    return page.locator('#log').text_content()


def add(page, files, selector='#fileInput', seconds=60):
    """Hand files to a file input and wait until the import has finished."""
    page.evaluate("status('…'); window.__status.length = 0; void 0;")
    page.locator(selector).set_input_files(files)
    page.wait_for_function("() => !S.importing && document.querySelector('#status').textContent.includes('已加入')", timeout=seconds * 1000)
    page.wait_for_timeout(80)


def named(source, name):
    return {'name': name, 'mimeType': 'image/heic', 'buffer': (fixtures / source).read_bytes()}


def worst_error(page, name, shown_as=None):
    """Largest difference between the colours on screen and the colours the fixture stands for; None if the size is wrong."""
    info = expected[name]
    got = page.evaluate(SAMPLE, [shown_as or name, [s[:2] for s in info['samples']]])
    if not got or (got['w'], got['h']) != (info['width'], info['height']):
        return None, got and (got['w'], got['h'])
    colour = alpha = 0
    for (x, y, want), have in zip(info['samples'], got['px']):
        alpha = max(alpha, abs(want[3] - have[3]))
        if want[3] >= 128:
            colour = max(colour, max(abs(a - b) for a, b in zip(want[:3], have[:3])))
    return max(colour, alpha), {'colour': colour, 'alpha': alpha}


def jpeg_sampling(head):
    """Sampling factors of the three components in a JPEG header: [0x11, 0x11, 0x11] means full colour resolution."""
    o = 2
    while o + 4 <= len(head) and head[o] == 0xFF:
        marker, size = head[o + 1], int.from_bytes(head[o + 2:o + 4], 'big')
        if marker in (0xC0, 0xC1, 0xC2):
            return [head[o + 11 + 3 * n] for n in range(head[o + 9])]
        o += 2 + size
    return None


def open_tool(context, url):
    page = context.new_page()
    problems = {'page': [], 'console': []}
    page.on('pageerror', lambda e: problems['page'].append(str(e)))
    page.on('console', lambda m: problems['console'].append(m.text) if m.type == 'error' else None)
    page.on('dialog', lambda d: d.accept())
    page.goto(url)
    page.wait_for_function("() => typeof S === 'object' && typeof EnToolbox === 'object'")
    page.evaluate(HOOKS)
    return page, problems


TOLERANCE = 5
with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=os.environ.get('CHROMIUM_EXECUTABLE') or shutil.which('chromium'), headless=True)
    context = browser.new_context(viewport={'width': 1440, 'height': 1000})

    # ================================================================ opened from disk, the way the tool is normally used
    page, problems = open_tool(context, (site / 'index.html').as_uri())
    record('Opens from a local folder without errors', not problems['page'] and not problems['console'], problems)
    all_names = list(expected)
    t0 = time.time()
    add(page, [str(fixtures / n) for n in all_names])
    took = time.time() - t0
    record('Every HEIC fixture is added in one import', page.evaluate('S.items.length') == len(all_names) and not is_error(page) and '略過' not in status(page), status(page))
    cases = [('heic_patches.heic', 'A plain HEIC shows the right colours'),
             ('heic_rotated.heic', 'A HEIC with a rotation box is shown turned'),
             ('heic_mirrored.heic', 'A HEIC with rotation and mirroring is shown turned and mirrored'),
             ('heic_grid.heic', 'A HEIC stored as tiles, as phones store them, is put together correctly'),
             ('heic_p3_icc.heic', 'Display P3 declared by an ICC profile is converted to sRGB'),
             ('heic_p3_nclx.heic', 'Display P3 declared by an nclx box is converted to sRGB'),
             ('heic_p3_both.heic', 'When a file carries both, the ICC profile decides and not the nclx box'),
             ('heic_bt2020.heic', 'Another colour space is left as it is'),
             ('heic_phone_like.heic', 'A phone-like file (tiles, rotation, Display P3) shows the right colours the right way up'),
             ('heic_alpha.heic', 'Transparency survives decoding')]
    assert [c[0] for c in cases] == all_names
    for name, title in cases:
        err, detail = worst_error(page, name)
        record(title, err is not None and err <= TOLERANCE, 'largest difference %s of 255, %s x %s' % (detail, expected[name]['width'], expected[name]['height']))
    decoded = {d['name']: d for d in page.evaluate('window.__heic')}
    log = log_text(page)
    record('The log says which photos were converted from Display P3 and which use another colour space',
           all((('HEIC：%s（Display P3 已換算成 sRGB）' % n) in log) == (expected[n]['reports'] == 'p3') and (('HEIC：%s（色彩描述檔不是' % n) in log) == (expected[n]['reports'] == 'other') for n in all_names)
           and all(decoded[n]['colour'] == expected[n]['reports'] for n in all_names), {n: d['colour'] for n, d in decoded.items()})
    record('Opaque photos are kept as JPEG with full colour resolution, transparent ones as PNG',
           all(decoded[n]['type'] == ('image/jpeg' if expected[n]['opaque'] else 'image/png') for n in all_names)
           and all(jpeg_sampling(base64.b64decode(decoded[n]['head'])) == [0x11, 0x11, 0x11] for n in all_names if expected[n]['opaque']),
           jpeg_sampling(base64.b64decode(decoded['heic_patches.heic']['head'])))
    originals = page.evaluate('''async () => { const out = {}; for (const i of S.items) out[i.file.name] = await blobDataURL(i.file); return out; }''')
    record('Each photo keeps its original HEIC bytes and name', all(hashlib.sha256(base64.b64decode(originals[n].split(',', 1)[1])).hexdigest() == expected[n]['sha256'] for n in all_names))
    frames = page.evaluate(FRAMES)
    record('One decoder frame serves the whole import', len(frames) == 1 and frames[0]['messages'] == 1 + len(all_names) and frames[0]['src'].endswith('/vendor/heic-decoder.html'), [(f['src'][-30:], f['messages']) for f in frames])
    record('The frame is sandboxed with scripts only, so the tool cannot be reached from it',
           frames[0]['sandbox'] == 'allow-scripts' and frames[0]['origin'] == 'null' and frames[0]['document'] == 'null' and frames[0]['window'] == 'SecurityError', frames[0])
    record('The frame is invisible and is removed when the import ends',
           frames[0]['visibility'] == 'hidden' and frames[0]['area'] == 0 and frames[0]['removed'] and page.locator('iframe').count() == 0 and page.evaluate('HEIC.frame === null && HEIC.ready === null && HEIC.waiting.size === 0'))
    record('Progress names the HEIC step while it runs', any(re.search(r'正在解碼 HEIC \d+ / %d…' % len(all_names), s) for s in page.evaluate('window.__status')), page.evaluate('window.__status.slice(0, 3)'))
    record('Ten small HEIC files decode in a few seconds', took < 20, '%.1f s' % took)
    record('No errors and no policy violations while decoding', not problems['page'] and not problems['console'] and not page.evaluate('window.__violations.length'), problems)

    # ---- the rest of the tool works with these photos
    page.evaluate('''() => { const id = n => S.items.find(i => i.file.name === n).id; assign('before', id('heic_patches.heic')); assign('after', id('heic_rotated.heic')); }''')
    page.wait_for_timeout(150)
    counts = page.evaluate('''async () => { const r = await encodeFormat(currentDoc(), 'png'), im = await createImageBitmap(r.blob), cv = document.createElement('canvas'); cv.width = im.width; cv.height = im.height;
        const g = cv.getContext('2d'); g.drawImage(im, 0, 0); const d = g.getImageData(0, 0, cv.width, cv.height).data; let red = 0, green = 0;
        for (let i = 0; i < d.length; i += 4) { if (d[i] > 245 && d[i + 1] < 12 && d[i + 2] < 12) red++; if (d[i] < 12 && d[i + 1] > 245 && d[i + 2] < 12) green++; }
        return {type: r.blob.type, width: cv.width, red, green}; }''')
    record('A before / after picture is produced from two HEIC photos', counts['type'] == 'image/png' and counts['red'] > 500 and counts['green'] > 500, counts)
    page.locator('#toolboxOpen').click()
    page.wait_for_timeout(200)
    add(page, [named('heic_phone_like.heic', 'toolbox.heic')], '#tbInput')
    said = page.locator('#tbStatus').text_content()
    err, detail = worst_error(page, 'heic_phone_like.heic', 'toolbox.heic')
    shot = page.evaluate('''() => { const src = S.items.find(i => i.file.name === 'toolbox.heic'); EnToolbox.select(src.id); const cv = EnToolbox.core.renderDoc(src, EnToolbox.getState().doc).cv;
        return {w: cv.width, h: cv.height, any: Array.from(cv.getContext('2d').getImageData(cv.width >> 1, cv.height >> 1, 1, 1).data)}; }''')
    record('The toolbox takes a HEIC photo through its own file button', err is not None and err <= TOLERANCE and (shot['w'], shot['h']) == (96, 128) and shot['any'][3] == 255 and '已加入 1 張' in said, (detail, shot, said))
    page.keyboard.press('Escape')
    page.wait_for_timeout(150)

    # ---- project files keep the HEIC bytes and decode them again when opened
    n_before = page.evaluate('S.items.length')
    page.locator('#saveProject').click()
    page.wait_for_function('() => !S.busy && window.__dl.length >= 1', timeout=60000)
    project = base64.b64decode(page.evaluate('async () => await blobDataURL(window.__dl.at(-1).blob)').split(',', 1)[1])
    z = zipfile.ZipFile(io.BytesIO(project))
    stored = [n for n in z.namelist() if n.startswith('photos/')]
    record('A project file stores the HEIC photos as they were', len(stored) == n_before and all(n.endswith('.heic') for n in stored)
           and hashlib.sha256(z.read(stored[0])).hexdigest() == expected[all_names[0]]['sha256'], stored[:2])
    n_frames = len(page.evaluate(FRAMES))
    page.evaluate('''async b64 => { await openProjectFile(new File([Uint8Array.from(atob(b64), c => c.charCodeAt(0))], 'heic.enproj')); }''', base64.b64encode(project).decode())
    page.wait_for_function('() => !S.busy && !S.importing', timeout=60000)
    page.wait_for_timeout(150)
    err, detail = worst_error(page, 'heic_phone_like.heic')
    record('Opening that project decodes the HEIC photos again', page.evaluate('S.items.length') == n_before and '已開啟專案檔' in status(page) and not is_error(page) and err is not None and err <= TOLERANCE
           and len(page.evaluate(FRAMES)) == n_frames + 1 and page.locator('iframe').count() == 0, (status(page), detail))

    closed = page.evaluate('''async () => { const opening = heicOpen(); heicClose('closed early');
        try { await opening; return 'opened'; } catch (e) { return [e.message, e.unavailable === true, HEIC.gone, HEIC.frame === null]; } }''')
    record('Closing the decoder while it is still starting ends the wait instead of hanging', closed == ['closed early', False, '', True] and page.locator('iframe').count() == 0, closed)

    # ---- files that cannot be decoded
    good = (fixtures / 'heic_patches.heic').read_bytes()
    page.evaluate("resetSession(); EnToolbox.refresh(); syncControls(); renderFiles(); renderCases(); commit(); pushHistory(); S.log.length = 0; window.__frames.length = 0; void 0;")
    add(page, [{'name': 'cut_header.heic', 'mimeType': 'image/heic', 'buffer': good[:180]}, {'name': 'cut_data.heic', 'mimeType': 'image/heic', 'buffer': good[:-90]},
               {'name': 'noise.heic', 'mimeType': 'image/heic', 'buffer': good[:32] + bytes(range(256)) * 3}, named('heic_grid.heic', 'after_bad.heic')])
    log = log_text(page)
    err, detail = worst_error(page, 'heic_grid.heic', 'after_bad.heic')
    record('Damaged HEIC files are skipped with a reason and the next file still decodes',
           page.evaluate('S.items.map(i => i.file.name)') == ['after_bad.heic'] and err is not None and err <= TOLERANCE and '略過 3 張' in status(page)
           and all(('略過：%s（HEIC 解碼失敗' % n) in log for n in ('cut_header.heic', 'cut_data.heic', 'noise.heic')), log[-300:])
    frames = page.evaluate(FRAMES)
    record('After a failure the next file gets a fresh decoder', len(frames) == 4 and all(f['removed'] for f in frames) and page.evaluate("HEIC.gone === ''"), len(frames))
    page.evaluate('HEIC.limit = 1000; void 0;')
    add(page, [named('heic_patches.heic', 'too_big.heic')])
    record('A HEIC over the pixel limit is refused by the decoder before it allocates the picture',
           page.evaluate('S.items.length') == 1 and '略過：too_big.heic（單張超過 6000 萬像素）' in log_text(page), log_text(page)[-120:])
    page.evaluate('HEIC.limit = 60000000; void 0;')
    n_frames = len(page.evaluate(FRAMES))
    png = io.BytesIO(); Image.new('RGB', (64, 48), (10, 120, 200)).save(png, 'PNG')
    add(page, [{'name': 'plain.png', 'mimeType': 'image/png', 'buffer': png.getvalue()}])
    record('Ordinary photos never start the decoder', page.evaluate('S.items.length') == 2 and len(page.evaluate(FRAMES)) == n_frames)
    page.evaluate('''() => { window.postMessage({type: 'ready'}, '*'); window.postMessage({type: 'result', id: 1, ok: true, width: 1, height: 1, buffer: new ArrayBuffer(4)}, '*'); window.postMessage({type: 'fatal'}, '*'); }''')
    page.wait_for_timeout(100)
    record('Messages that do not come from the decoder frame are ignored', page.evaluate("HEIC.frame === null && HEIC.gone === '' && S.items.length === 2") and not problems['page'])
    record('No script errors in the whole local run', not problems['page'], problems['page'])
    page.close()

    # ---- the tool copied somewhere without its vendor folder
    page, problems = open_tool(context, (lone / 'index.html').as_uri())
    t0 = time.time()
    add(page, [str(fixtures / 'heic_patches.heic')])
    took = time.time() - t0
    record('Without the vendor folder a HEIC is skipped and the message says what to do',
           page.evaluate('S.items.length') == 0 and is_error(page) and 'HEIC 無法解碼' in status(page) and 'vendor 資料夾' in status(page) and 'Safari 17' in status(page)
           and '此瀏覽器無法解碼 HEIC' in log_text(page) and page.locator('iframe').count() == 0, status(page))
    record('That answer comes after a short wait, not a long one', 6 < took < 25, '%.1f s' % took)
    t0 = time.time()
    add(page, [named('heic_rotated.heic', 'again.heic'), {'name': 'plain.png', 'mimeType': 'image/png', 'buffer': png.getvalue()}])
    record('The missing decoder is remembered: later HEIC files are skipped at once and other photos still load',
           time.time() - t0 < 4 and len(page.evaluate(FRAMES)) == 1 and page.evaluate('S.items.map(i => i.file.name)') == ['plain.png'] and 'vendor 資料夾' in status(page) and not problems['page'], '%.1f s' % (time.time() - t0))
    page.close()

    # ================================================================ served by a web server
    page, problems = open_tool(context, base_url + 'site/index.html')
    add(page, [str(fixtures / n) for n in ('heic_phone_like.heic', 'heic_alpha.heic')])
    errs = [worst_error(page, n)[0] for n in ('heic_phone_like.heic', 'heic_alpha.heic')]
    frames = page.evaluate(FRAMES)
    record('Served over HTTP, HEIC photos decode the same way', all(e is not None and e <= TOLERANCE for e in errs) and len(frames) == 1 and frames[0]['src'] == base_url + 'site/vendor/heic-decoder.html'
           and frames[0]['origin'] == 'null' and frames[0]['removed'] and not problems['page'] and not problems['console'], (errs, problems))

    # ---- what the real decoder page and its worker are allowed to do, tried from inside them
    # The attempts run from a timer: code started directly by the debugger is exempt from some of these rules and would prove nothing.
    PROBE = '''url => { self.__probe = null; const seen = []; self.addEventListener('securitypolicyviolation', e => seen.push(e.effectiveDirective));
      setTimeout(async () => { const out = {};
        try { new Function('return 1')(); out.code = 'ran'; } catch (e) { out.code = 'blocked'; }
        try { await fetch(url, {mode: 'no-cors'}); out.fetch = 'sent'; } catch (e) { out.fetch = 'blocked'; }
        if (typeof importScripts === 'function') { try { importScripts(url); out.load = 'loaded'; } catch (e) { out.load = 'blocked'; } }
        else out.load = await new Promise(done => { const im = new Image(); im.onload = () => done('loaded'); im.onerror = () => done('blocked'); im.src = url; });
        out.socket = await new Promise(done => { try { const ws = new WebSocket(url.replace('http', 'ws')); ws.onopen = () => done('open'); ws.onerror = ws.onclose = () => done('blocked'); } catch (e) { done('blocked'); } setTimeout(() => done('silent'), 1500); });
        if (typeof document === 'object') {
          try { const el = document.createElement('script'); el.textContent = 'self.__injected = 1'; document.head.append(el); out.inline = self.__injected ? 'ran' : 'blocked'; } catch (e) { out.inline = 'blocked'; }
          try { void parent.document.title; out.parent = 'reachable'; } catch (e) { out.parent = e.name; }
          try { void localStorage.length; out.storage = 'reachable'; } catch (e) { out.storage = e.name; }
        }
        await new Promise(r => setTimeout(r, 150));
        out.violations = [...new Set(seen)].sort(); self.__probe = out; }, 0); }'''

    def probe(target, tag):
        target.evaluate(PROBE, other_url + 'leak.html?' + tag)
        for _ in range(60):
            page.wait_for_timeout(100)
            got = target.evaluate('self.__probe')
            if got:
                return got
        return None

    page.evaluate('heicOpen()')
    inner = next(f for f in page.frames if f.url.endswith('/vendor/heic-decoder.html'))
    got = probe(inner, 'from-page')
    record('The real decoder page cannot send anything out, load anything or run other code',
           got is not None and got['code'] == 'blocked' and got['fetch'] == 'blocked' and got['load'] == 'blocked' and got['socket'] == 'blocked' and got['inline'] == 'blocked'
           and got['parent'] == 'SecurityError' and got['storage'] == 'SecurityError' and {'connect-src', 'img-src', 'script-src'} <= set(got['violations']) and not other_seen, (got, other_seen))
    workers = [w for w in page.workers if w.url.startswith('blob:')]
    got = probe(workers[0], 'from-worker') if len(workers) == 1 else None
    record('The worker that runs the library is under the same rules: no network, no other code',
           got is not None and got['code'] == 'blocked' and got['fetch'] == 'blocked' and got['load'] == 'blocked' and got['socket'] == 'blocked'
           and {'connect-src', 'script-src'} <= set(got['violations']) and not other_seen, (got, other_seen))
    page.evaluate('window.__violations.length = 0; void 0;')
    try:
        inner.evaluate("url => { location.href = url; }", other_url + 'leak.html?navigate')
    except Exception:
        pass
    page.wait_for_timeout(600)
    record('The decoder frame cannot be sent to another site', any(v['directive'] == 'frame-src' for v in page.evaluate('window.__violations')) and not other_seen, (page.evaluate('window.__violations'), other_seen))
    page.evaluate('heicClose(); void 0;')
    page.close()

    # ---- a decoder page that lies about what it decoded
    page, problems = open_tool(context, base_url + 'liar/index.html')
    pad = lambda k: good + bytes((k - len(good)) % 10)
    add(page, [{'name': 'case%d.heic' % k, 'mimeType': 'image/heic', 'buffer': pad(k)} for k in range(10)])
    log = log_text(page)
    kept = page.evaluate('S.items.map(i => [i.file.name, i.w, i.h])')
    record('Answers with impossible sizes or missing pixels are rejected', all(('略過：case%d.heic（HEIC 解碼結果不正確）' % k) in log for k in range(7)) and not problems['page'], log[-200:])
    record('A decoder that reports a crash only costs the photo it was working on', '略過：case7.heic（HEIC 解碼元件發生錯誤）' in log and kept == [['case8.heic', 3, 1], ['case9.heic', 2, 2]], kept)
    record('An answer for another request is ignored', ['case8.heic', 3, 1] in kept and page.evaluate("HEIC.gone === ''") and page.locator('iframe').count() == 0)
    page.close()

    # ---- a decoder that is ready before its page has finished loading, and slow to answer
    page, problems = open_tool(context, base_url + 'late/index.html')
    t0 = time.time()
    add(page, [str(fixtures / 'heic_patches.heic')])
    record('A working decoder is not given up on, however the start-up events are ordered and however long a photo takes',
           page.evaluate('S.items.map(i => [i.w, i.h])') == [[2, 2]] and time.time() - t0 > 9 and page.evaluate("HEIC.gone === ''") and not problems['page'], '%.1f s, %s' % (time.time() - t0, status(page)))
    page.close()

    # ---- a decoder page that tries to reach the tool, the computer and the network
    page, problems = open_tool(context, base_url + 'spy/index.html')
    start_url = page.url
    add(page, [str(fixtures / 'heic_patches.heic')])
    spy = page.evaluate('window.__spy')
    record('A hostile page in the decoder frame cannot reach the tool, its storage, pop-ups or the top window',
           spy is not None and spy['origin'] == 'null' and spy['parentDocument'] == 'SecurityError' and spy['parentWindow'] == 'SecurityError' and spy['storage'] == 'SecurityError'
           and spy['cookie'] == 'SecurityError' and spy['database'] == 'SecurityError' and spy['popup'] == 'blocked' and spy['top'] == 'SecurityError' and spy['readTool'] == 'blocked' and page.url == start_url and len(context.pages) == 1, spy)
    record('It cannot leave for another site either, and the photo is simply skipped',
           any(v['directive'] == 'frame-src' and v['blocked'].startswith(other_url.rstrip('/')) for v in page.evaluate('window.__violations')) and not other_seen
           and page.evaluate('S.items.length') == 0 and 'vendor 資料夾' in status(page) and not problems['page'], (page.evaluate('window.__violations'), other_seen))
    page.close()

    # ---- a web server without the vendor folder
    page, problems = open_tool(context, base_url + 'lone/index.html')
    add(page, [str(fixtures / 'heic_patches.heic')])
    record('On a web server without the vendor folder the same guidance appears', page.evaluate('S.items.length') == 0 and is_error(page) and 'vendor 資料夾' in status(page) and not problems['page'], status(page))
    page.close()

    (work / 'test-results.json').write_text(json.dumps({'browser': browser.version, 'results': results}, ensure_ascii=False, indent=2), encoding='utf-8')
    browser.close()
server.shutdown(); other_server.shutdown()
print('TOTAL', len(results), 'PASS', sum(r['passed'] for r in results), flush=True)
