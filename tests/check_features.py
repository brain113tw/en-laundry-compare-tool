"""Developer regression checks for the project file, pinch zoom, HEIC recognition and unsaved-work guard.

Needs Python, Playwright, Pillow and Chromium (set CHROMIUM_EXECUTABLE or have `chromium` on PATH).
End users never need this; the tool itself is a single HTML file.
Fixtures are synthetic shapes, never customer photos.
"""
from pathlib import Path
from playwright.sync_api import sync_playwright
from PIL import Image, ImageDraw
import base64, io, json, os, shutil, struct, tempfile, zipfile, zlib

root = Path(__file__).resolve().parents[1]
work = Path(tempfile.mkdtemp(prefix='en-feature-tests-'))
html = (root / 'index.html').read_text(encoding='utf-8')
heic_fixture = root / 'tests' / 'fixtures' / 'sample.heic'

for name, col in [('demo_before.png', (152, 160, 174)), ('demo_after.png', (110, 158, 167)), ('demo_third.png', (190, 150, 120))]:
    im = Image.new('RGB', (720, 960), (239, 240, 236))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((160, 180, 555, 790), radius=48, fill=col, outline=(45, 71, 70), width=5)
    d.rectangle((0, 0, 90, 75), fill=(210, 30, 40))
    d.ellipse((285, 325, 435, 470), fill=(236, 216, 150))
    im.save(work / name)
logo = Image.new('RGBA', (200, 80), (0, 0, 0, 0))
ImageDraw.Draw(logo).rounded_rectangle((4, 4, 196, 76), radius=14, fill=(18, 103, 80, 255))
logo.save(work / 'logo.png')
print('Temporary test artifacts:', work)

results = []


def record(name, ok, detail=''):
    results.append({'test': name, 'passed': bool(ok), 'detail': str(detail)})
    print(('PASS ' if ok else 'FAIL ') + name, detail, flush=True)
    assert ok, (name, detail)


def wait_for(page, expr, seconds=20):
    page.wait_for_function(expr, timeout=seconds * 1000)


def load(page, names):
    page.locator('#fileInput').set_input_files([str(work / n) for n in names])
    wait_for(page, '() => !S.importing && S.items.length >= %d' % len(names))
    page.wait_for_timeout(150)


def snapshot(page):
    """Everything a project file is supposed to preserve, keyed by file name instead of session ids."""
    return json.dumps(json.loads(page.evaluate('''() => {
      const nm = id => item(id)?.file.name || null, st = EnToolbox.projectState(id => nm(id));
      return JSON.stringify({
        photos: S.items.map(i => [i.file.name, i.path, i.file.size, i.w, i.h]),
        before: nm(S.before), after: nm(S.after), selected: nm(S.selected), activeSide: S.activeSide,
        cfg: S.cfg, tr: S.tr,
        cases: S.cases.map(c => ({name: c.name, checked: c.checked, active: c.id === S.activeCase, before: nm(c.doc.before), after: nm(c.doc.after), cfg: c.doc.cfg, tr: c.doc.tr})),
        toolbox: st, logo: EnToolbox.projectLogo() ? EnToolbox.projectLogo().name : null});
    }''')), sort_keys=True, ensure_ascii=False)


def compare_png(page):
    return page.evaluate('''async () => { const r = await encodeFormat(currentDoc(), 'png'); return await blobDataURL(r.blob); }''')


def toolbox_png(page, name):
    return page.evaluate('''name => { const src = S.items.find(i => i.file.name === name); EnToolbox.select(src.id);
      return EnToolbox.core.renderDoc(src, EnToolbox.getState().doc).cv.toDataURL('image/png'); }''', name)


def saved_bytes(page, index=-1):
    data = page.evaluate('async i => await blobDataURL(window.__dl.at(i).blob)', index)
    return base64.b64decode(data.split(',', 1)[1])


def open_bytes(page, data, name='test.enproj'):
    """Feed bytes to the real loader and wait until it has finished."""
    page.evaluate('''async ([b64, name]) => { const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
      await openProjectFile(new File([bytes], name)); }''', [base64.b64encode(data).decode(), name])
    wait_for(page, '() => !S.busy && !S.importing')
    page.wait_for_timeout(120)


def status(page):
    return page.locator('#status').text_content()


def is_error(page):
    return 'error' in (page.locator('#status').get_attribute('class') or '')


def rebuild(data, mutate=None, compression=zipfile.ZIP_STORED, drop=None, extra=None):
    """Re-write a project with another ZIP writer, optionally editing project.json."""
    src = zipfile.ZipFile(io.BytesIO(data))
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', compression) as z:
        for info in src.infolist():
            if drop and info.filename == drop:
                continue
            body = src.read(info.filename)
            if info.filename == 'project.json' and mutate:
                obj = json.loads(body)
                res = mutate(obj)
                body = res if isinstance(res, (bytes, bytearray)) else json.dumps(obj, ensure_ascii=False).encode()
            z.writestr(zipfile.ZipInfo(info.filename), body, compression)
        for name, body in (extra or {}).items():
            z.writestr(zipfile.ZipInfo(name), body, compression)
    return out.getvalue()


with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=os.environ.get('CHROMIUM_EXECUTABLE') or shutil.which('chromium'), headless=True)
    context = browser.new_context(viewport={'width': 1440, 'height': 1000}, has_touch=True)
    page = context.new_page()
    errors = []
    answer = {'accept': True}
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.on('dialog', lambda d: d.accept() if answer['accept'] else d.dismiss())
    page.set_content(html)
    page.wait_for_timeout(100)
    page.evaluate("window.__dl = []; window.download = (blob, name) => { window.__dl.push({blob, name}); };")
    record('Starts without script errors', not errors, errors)

    # ------------------------------------------------------------------ HEIC recognition (native decode only)
    record('Desktop file dialogs list HEIC', '.heic' in page.locator('#fileInput').get_attribute('accept') and '.heif' in page.locator('#tbInput').get_attribute('accept'))
    record('HEIC signature accepted for a real HEIC file', page.evaluate('''async b64 => { const f = new File([Uint8Array.from(atob(b64), c => c.charCodeAt(0))], 'a.heic');
        try { await verifyImageSignature(f, 'heic'); await verifyImageSignature(f, 'heif'); return true; } catch (e) { return String(e); } }''',
        base64.b64encode(heic_fixture.read_bytes()).decode()) is True)
    record('AVIF container is not accepted as HEIC', page.evaluate('''async () => { const b = new Uint8Array(32); b.set([0,0,0,28, 0x66,0x74,0x79,0x70, 0x61,0x76,0x69,0x66, 0,0,0,0, 0x61,0x76,0x69,0x66, 0x6d,0x69,0x66,0x31]);
        try { await verifyImageSignature(new File([b], 'a.heic'), 'heic'); return false; } catch (_) { return true; } }'''))
    page.locator('#fileInput').set_input_files(str(heic_fixture))
    wait_for(page, '() => !S.importing')
    page.wait_for_timeout(150)
    native = page.evaluate('S.items.length') == 1
    record('HEIC either decodes natively or is skipped with specific guidance',
           native or ('HEIC 此瀏覽器無法解碼' in status(page) and 'Safari' in status(page) and is_error(page)), status(page))
    if native:
        page.evaluate("resetSession(); syncControls(); renderFiles(); renderCases(); commit(); pushHistory();")
    jpeg = io.BytesIO()
    Image.new('RGB', (64, 64), (200, 30, 30)).save(jpeg, 'JPEG')
    page.locator('#fileInput').set_input_files({'name': 'renamed.heic', 'mimeType': 'image/heic', 'buffer': jpeg.getvalue()})
    wait_for(page, '() => !S.importing')
    page.wait_for_timeout(120)
    record('JPEG renamed to .heic is rejected by signature, not blamed on the browser',
           page.evaluate('S.items.length') == 0 and 'HEIC 此瀏覽器無法解碼' not in status(page) and '檔案內容與副檔名不符' in page.locator('#log').text_content())

    # ------------------------------------------------------------------ two-finger pinch (real touch input through CDP)
    load(page, ['demo_before.png', 'demo_after.png'])
    page.wait_for_timeout(250)
    cdp = context.new_cdp_session(page)

    def touch(kind, points):
        cdp.send('Input.dispatchTouchEvent', {'type': kind, 'touchPoints': [{'x': x, 'y': y, 'id': i} for i, (x, y) in points]})
        page.wait_for_timeout(40)

    c = page.evaluate("(() => { const r = overlay.getBoundingClientRect(), b = geom.before; return {x: r.x + (b.x + b.w / 2) / geom.W * r.width, y: r.y + (b.y + b.h / 2) / geom.H * r.height}; })()")
    hist0 = page.evaluate('S.history.length')
    touch('touchStart', [(0, (c['x'] - 30, c['y']))])
    touch('touchStart', [(0, (c['x'] - 30, c['y'])), (1, (c['x'] + 30, c['y']))])
    record('Second finger turns a photo drag into a pinch', page.evaluate("S.drag && S.drag.kind === 'pinch' && S.drag.side === 'before'"))
    for step in range(1, 7):
        touch('touchMove', [(0, (c['x'] - 30 - 10 * step, c['y'])), (1, (c['x'] + 30 + 10 * step, c['y']))])
    scale = page.evaluate('S.tr.before.scale')
    record('Pinch out enlarges the photo in proportion to finger distance', abs(scale - 300) < 6, scale)
    record('Symmetric pinch keeps the photo centred under the fingers', page.evaluate('Math.abs(S.tr.before.x) < 1.5 && Math.abs(S.tr.before.y) < 1.5'), page.evaluate('[S.tr.before.x, S.tr.before.y]'))
    record('The other photo is untouched by a pinch', page.evaluate('S.tr.after.scale === 100 && S.tr.after.x === 0'))
    touch('touchEnd', [(0, (c['x'] - 90, c['y']))])
    record('Lifting one finger ends the gesture and records one undo step', page.evaluate('S.drag === null') and page.evaluate('S.history.length') == hist0 + 1)
    touch('touchMove', [(0, (c['x'] - 150, c['y'] + 40))])
    record('The remaining finger does not jerk the photo', page.evaluate('S.tr.before.scale') == scale and page.evaluate('Math.abs(S.tr.before.x) < 1.5'))
    touch('touchEnd', [])
    touch('touchStart', [(0, (c['x'] - 60, c['y']))])
    touch('touchStart', [(0, (c['x'] - 60, c['y'])), (1, (c['x'] + 60, c['y']))])
    for step in range(1, 30):
        touch('touchMove', [(0, (c['x'] - 60 + 2 * step, c['y'])), (1, (c['x'] + 60 - 2 * step, c['y']))])
    touch('touchEnd', [])
    record('Pinch in shrinks and stops at the 20% limit', page.evaluate('S.tr.before.scale') == 20, page.evaluate('S.tr.before.scale'))
    page.locator('#undoBtn').click()
    record('Pinch is undoable', abs(page.evaluate('S.tr.before.scale') - scale) < 0.01)
    x0 = page.evaluate('S.tr.before.x')
    touch('touchStart', [(0, (c['x'], c['y']))])
    touch('touchMove', [(0, (c['x'] + 40, c['y']))])
    touch('touchEnd', [])
    record('Single finger still pans the photo', page.evaluate('S.tr.before.x') > x0 + 1 and page.evaluate('S.drag === null'))
    lab = page.evaluate("(() => { const r = overlay.getBoundingClientRect(), l = labelRectFor('before', geom, S.cfg); return {x: r.x + (l.x + l.w / 2) / geom.W * r.width, y: r.y + (l.y + l.h / 2) / geom.H * r.height}; })()")
    sc = page.evaluate('S.tr.before.scale')
    touch('touchStart', [(0, (lab['x'], lab['y']))])
    touch('touchStart', [(0, (lab['x'], lab['y'])), (1, (c['x'] + 80, c['y']))])
    touch('touchMove', [(0, (lab['x'], lab['y'])), (1, (c['x'] + 160, c['y']))])
    touch('touchEnd', [])
    record('A second finger while dragging a label does not zoom', page.evaluate('S.tr.before.scale') == sc and page.evaluate('S.drag === null'))
    bb = page.locator('#overlay').bounding_box()
    page.mouse.move(c['x'], c['y']); page.mouse.down(); page.mouse.move(c['x'] + 25, c['y'] + 10, steps=4); page.mouse.up()
    record('Mouse drag still works after touch gestures', page.evaluate('S.drag === null') and not errors, errors)
    page.evaluate("S.tr = {before: freshTransform(), after: freshTransform()}; syncTransformControls(); commit(); pushHistory();")

    # ------------------------------------------------------------------ unsaved-work guard
    def leave_blocked():
        return page.evaluate("(() => { const ev = new Event('beforeunload', {cancelable: true}); window.dispatchEvent(ev); return ev.defaultPrevented; })()")

    record('Leaving with unexported edits asks for confirmation', leave_blocked())
    page.locator('.export[data-format="png"]').click()
    wait_for(page, '() => !S.busy && window.__dl.length >= 1')
    record('A simple comparison is considered done once exported', not leave_blocked())
    page.locator('#casesTab').click(); page.locator('#addCase').click(); page.wait_for_timeout(80); page.locator('#photosTab').click()
    page.locator('.export[data-format="png"]').click()
    wait_for(page, '() => !S.busy && window.__dl.length >= 2')
    record('Batch setup stays protected after an export until a project is saved', leave_blocked())

    # ------------------------------------------------------------------ build a rich session, save, reopen
    load(page, ['demo_before.png', 'demo_after.png', 'demo_third.png'])
    page.evaluate('''() => { S.cfg.showTitle = true; S.cfg.title = '專案測試｜示意'; S.cfg.quality = 71; S.cfg.layout = 'custom'; S.cfg.autoHeight = false; S.cfg.width = 1200; S.cfg.height = 800;
        S.cfg.background = '#f1ede4'; S.tr.before = {scale: 137.5, x: -12.5, y: 8, rotation: 90}; S.tr.after = {scale: 80, x: 3, y: -4, rotation: -15};
        S.selected = S.items[2].id; S.activeSide = 'after'; syncControls(); commit(); pushHistory(); }''')
    page.locator('#casesTab').click(); page.locator('#addCase').click(); page.wait_for_timeout(80)
    page.evaluate('''() => { const d = currentDoc(); d.before = S.items[2].id; d.cfg.title = '第二組'; d.tr.before.rotation = 0; addCase(d, '第二組 / 測試', false); renderCases(); pushHistory(); }''')
    page.locator('#photosTab').click()
    page.locator('#toolboxOpen').click(); page.wait_for_timeout(120)
    ids = page.evaluate('S.items.map(i => i.id)')
    page.evaluate('id => EnToolbox.select(id)', ids[0])
    page.locator('#tbLogoInput').set_input_files(str(work / 'logo.png'))
    wait_for(page, "() => document.querySelector('#tbLogoName').textContent.includes('logo.png')")
    page.locator('[data-tb-tab="crop"]').click(); page.select_option('#tbCropAspect', '1'); page.wait_for_timeout(80)
    page.locator('[data-tb-tab="privacy"]').click(); page.select_option('#tbMaskType', 'mosaic'); page.locator('#tbMaskAdd').click(); page.locator('#tbMaskAdd').click(); page.wait_for_timeout(60)
    page.locator('[data-tb-tab="draw"]').click(); page.select_option('#tbDrawType', 'arrow'); page.select_option('#tbDrawDir', 'sw'); page.locator('#tbDrawAdd').click()
    page.select_option('#tbDrawType', 'text'); page.locator('#tbDrawText').fill('重點 A'); page.locator('#tbDrawAdd').click(); page.wait_for_timeout(60)
    page.locator('[data-tb-tab="size"]').click(); page.select_option('#tb-format', 'jpg'); page.locator('#tb-quality').evaluate("e => { e.value = 63; e.dispatchEvent(new Event('input', {bubbles: true})); e.dispatchEvent(new Event('change', {bubbles: true})); }")
    page.evaluate('id => EnToolbox.select(id)', ids[1])
    page.locator('[data-tb-tab="rotate"]').click(); page.locator('#tbRotateRight').click(); page.wait_for_timeout(60)
    page.evaluate("ids => { document.querySelectorAll('#tbFiles .tb-file input[type=checkbox]').forEach((c, n) => { if (n !== 1) c.click(); }); }", ids)
    page.evaluate('id => EnToolbox.select(id)', ids[0])
    before_state = snapshot(page)
    before_tb_png = toolbox_png(page, 'demo_before.png')
    n_dl = page.evaluate('window.__dl.length')
    page.locator('#tbSaveProject').click()
    wait_for(page, '() => !S.busy && window.__dl.length >= %d' % (n_dl + 1))
    record('Toolbox save button produces a project and reports it in the toolbox footer',
           page.evaluate("window.__dl.at(-1).name.endsWith('.enproj')") and '專案檔已交給瀏覽器下載' in page.locator('#tbStatus').text_content())
    record('Toolbox controls are usable again after saving', page.locator('#tbSaveProject').is_enabled() and page.locator('#tbBack').is_enabled() and not page.evaluate('EnToolbox.getState().busy'))
    page.locator('#tbBack').click(); page.wait_for_timeout(100)
    before_png = compare_png(page)
    project = saved_bytes(page)
    (work / 'saved.enproj').write_bytes(project)
    z = zipfile.ZipFile(io.BytesIO(project))
    names = z.namelist()
    record('Project is a valid stored ZIP with intact CRCs', z.testzip() is None and all(i.compress_type == zipfile.ZIP_STORED for i in z.infolist()), names)
    record('Project holds project.json, every photo and the logo', names[0] == 'project.json' and names[1:4] == ['photos/0001.png', 'photos/0002.png', 'photos/0003.png'] and 'logo/logo.png' in names, names)
    record('Photo bytes are stored unmodified', z.read('photos/0001.png') == (work / 'demo_before.png').read_bytes() and z.read('logo/logo.png') == (work / 'logo.png').read_bytes())
    meta = json.loads(z.read('project.json'))
    record('project.json is typed, versioned and free of session ids',
           meta['type'] == 'en-project' and meta['version'] == 1 and [p['id'] for p in meta['photos']] == ['p1', 'p2', 'p3'] and not any(i in z.read('project.json').decode() for i in ids))
    record('Saving a project clears the unsaved-work guard', not leave_blocked())

    # reopen into a different session (other photos, other settings)
    page.evaluate("S.busy = false; resetSession(); EnToolbox.refresh(); syncControls(); renderFiles(); renderCases(); commit(); pushHistory();")
    load(page, ['demo_third.png'])
    page.evaluate("S.cfg.title = 'other'; S.cfg.quality = 99; syncControls(); commit(); pushHistory();")
    answer['accept'] = False
    other = snapshot(page)
    open_bytes(page, project)
    record('Declining the replace prompt keeps the current session', snapshot(page) == other and '已取消' in status(page), status(page))
    answer['accept'] = True
    page.locator('#projectInput').set_input_files(str(work / 'saved.enproj'))
    wait_for(page, "() => !S.busy && !S.importing && S.items.length === 3 && document.querySelector('#status').textContent.includes('已開啟專案檔')")
    page.wait_for_timeout(200)
    after_state = snapshot(page)
    record('Reopened project restores photos, settings, positions, batch and toolbox edits exactly', after_state == before_state,
           '' if after_state == before_state else [k for k in json.loads(before_state) if json.loads(before_state)[k] != json.loads(after_state)[k]])
    record('Reopened project gets fresh session ids and a clean history', page.evaluate('S.history.length === 1 && S.future.length === 0') and not set(ids) & set(page.evaluate('S.items.map(i => i.id)')))
    record('Reopened comparison renders pixel-identical output', compare_png(page) == before_png)
    record('Reopened toolbox photo renders pixel-identical output (crop, masks, marks, logo)', toolbox_png(page, 'demo_before.png') == before_tb_png)
    record('Reopened project starts without unsaved work', not leave_blocked())
    page.locator('#toolboxOpen').click(); page.wait_for_timeout(120)
    record('Toolbox list shows restored edits and ticks', '已裁切' in page.locator('#tbFiles .tb-file').first.locator('.tb-tag').text_content()
           and page.evaluate("[...document.querySelectorAll('#tbFiles .tb-file input[type=checkbox]')].map(c => c.checked).join()") == 'true,false,true')
    page.locator('#tbBack').click(); page.wait_for_timeout(80)
    page.locator('#saveProject').click()
    wait_for(page, '() => !S.busy && window.__dl.length >= %d' % (n_dl + 2))
    again = zipfile.ZipFile(io.BytesIO(saved_bytes(page)))
    a, b = json.loads(again.read('project.json')), json.loads(z.read('project.json'))
    a.pop('created'); b.pop('created')
    record('Saving the reopened project reproduces the same project data', a == b and again.read('photos/0002.png') == z.read('photos/0002.png'))
    record('A project re-written by another ZIP tool (stored) still opens', (open_bytes(page, rebuild(project)), snapshot(page) == before_state)[1], status(page))

    # ------------------------------------------------------------------ hostile and damaged project files leave the session untouched
    good = snapshot(page)

    def rejected(label, data, expect=''):
        n_err = len(errors)
        open_bytes(page, data)
        ok = snapshot(page) == good and is_error(page) and '無法開啟專案檔' in status(page) and (expect in status(page)) and len(errors) == n_err
        record('Rejected, session unchanged: ' + label, ok, status(page))

    flipped = bytearray(project)
    info = z.getinfo('photos/0002.png')
    flipped[info.header_offset + 30 + len(info.filename) + 200] ^= 0xFF
    rejected('photo bytes altered (CRC mismatch)', bytes(flipped), 'CRC')
    rejected('re-compressed with deflate', rebuild(project, compression=zipfile.ZIP_DEFLATED), '重新壓縮')
    rejected('truncated file', project[:len(project) // 2], 'ZIP')
    rejected('not a ZIP at all', b'<html><script>window.bad=1</script></html>' * 20, 'ZIP')
    rejected('missing photo entry', rebuild(project, drop='photos/0003.png'), '缺少照片')
    rejected('missing project.json', rebuild(project, drop='project.json'), 'project.json')
    rejected('wrong type', rebuild(project, lambda o: o.update(type='favorites')), '不是對比圖專案檔')
    rejected('future version', rebuild(project, lambda o: o.update(version=2)), '版本')
    rejected('prototype key', rebuild(project, lambda o: json.dumps(o).replace('"compare":', '"__proto__":{"polluted":true},"compare":', 1).encode()), '禁止')
    rejected('reference to an unknown photo', rebuild(project, lambda o: o['compare'].update(before='p9')), '不存在的照片')
    rejected('photo renamed to .html', rebuild(project, lambda o: o['photos'][0].update(name='evil.html')), '不支援的照片類型')
    rejected('photo ids out of order', rebuild(project, lambda o: o['photos'][1].update(id='p7')), '照片編號')
    rejected('non-numeric setting', rebuild(project, lambda o: o['compare']['cfg'].update(quality='90')), 'quality')
    rejected('non-finite position', rebuild(project, lambda o: o['compare']['tr']['before'].update(scale='big')), '位置數值')
    rejected('over-limit canvas', rebuild(project, lambda o: o['compare']['cfg'].update(width=8192, height=8192, autoHeight=False, layout='custom')), '像素')
    rejected('unknown mask type', rebuild(project, lambda o: o['toolbox']['docs']['p1']['masks'][0].update(type='none')), '遮蔽類型')
    rejected('too many masks', rebuild(project, lambda o: o['toolbox']['docs']['p1'].update(masks=o['toolbox']['docs']['p1']['masks'] * 21)), '遮蔽資料')
    rejected('marker colour that is not a colour', rebuild(project, lambda o: o['toolbox']['docs']['p1']['shapes'][0].update(color='url(x)')), '標記')
    rejected('toolbox edits for an unknown photo', rebuild(project, lambda o: o['toolbox']['docs'].update(p9=o['toolbox']['docs']['p1'])), '每張編輯')
    rejected('invalid UTF-8 in project.json', rebuild(project, lambda o: b'\xff\xfe{"type":"en-project"}'), 'UTF-8')
    rejected('deeply nested JSON', rebuild(project, lambda o: o.update(extra=json.loads('[' * 20 + ']' * 20))), '巢狀')
    huge = bytearray(project)
    eocd = huge.rfind(b'PK\x05\x06')
    struct.pack_into('<I', huge, eocd + 12, 0x7fffffff)
    rejected('directory size larger than the file', bytes(huge), '目錄')
    record('No prototype pollution after hostile files', page.evaluate('({}).polluted === undefined && window.bad === undefined'))

    # values that are merely out of range are clamped, and unknown fields are dropped
    def soften(o):
        o['compare']['tr']['before'].update(scale=99999, rotation=-9999)
        o['compare']['cfg']['quality'] = 999
        o['compare']['cfg']['unknownField'] = 'x'
        o['toolbox']['docs']['p1']['masks'][0].update(strength=9999, x=-5, w=50)
        o['photos'][0]['path'] = 'a\u0000b/' + 'demo_before.png'
    open_bytes(page, rebuild(project, soften))
    record('Out-of-range values are clamped and unknown fields dropped', page.evaluate('''() => { const d = EnToolbox.projectState(id => item(id).file.name).docs['demo_before.png'].masks[0];
        return S.tr.before.scale === 400 && S.tr.before.rotation === -180 && S.cfg.quality === 100 && !('unknownField' in S.cfg) && d.strength === 60 && d.x === 0 && d.w === 1 && !S.items[0].path.includes('\\u0000'); }'''), status(page))

    # a photo whose bytes are valid for the ZIP but not an image is skipped, and what referred to it is dropped
    def junk_photo(data):
        src = zipfile.ZipFile(io.BytesIO(data)); out = io.BytesIO()
        with zipfile.ZipFile(out, 'w', zipfile.ZIP_STORED) as zz:
            for i in src.infolist():
                zz.writestr(zipfile.ZipInfo(i.filename), b'not an image at all' * 10 if i.filename == 'photos/0001.png' else src.read(i.filename))
        return out.getvalue()
    n_err = len(errors)
    open_bytes(page, junk_photo(project))
    record('A photo that cannot be decoded is skipped and its references dropped', page.evaluate('''() => S.items.length === 2 && S.before === null && S.tr.before.scale === 100 && S.tr.before.rotation === 0
        && S.cases.every(c => item(c.doc.before) && item(c.doc.after)) && !!item(EnToolbox.getState().active)''') and '無法載入' in status(page) and len(errors) == n_err, status(page))

    # an over-limit canvas cannot be written into a project that would then refuse to open
    open_bytes(page, project)
    n_dl = page.evaluate('window.__dl.length')
    page.evaluate("S.cfg.layout = 'custom'; S.cfg.autoHeight = false; S.cfg.width = 8192; S.cfg.height = 8192; syncControls(); commit();")
    page.locator('#saveProject').click()
    wait_for(page, '() => !S.busy')
    record('Saving refuses a state it could not read back', page.evaluate('window.__dl.length') == n_dl and '無法儲存專案檔' in status(page) and is_error(page) and page.locator('#saveProject').is_enabled(), status(page))
    page.evaluate("resetSession(); EnToolbox.refresh(); syncControls(); renderFiles(); renderCases(); commit(); pushHistory();")
    page.locator('#saveProject').click(); page.wait_for_timeout(100)
    record('Saving with no photos explains instead of producing an empty file', page.evaluate('window.__dl.length') == n_dl and '沒有照片可儲存' in status(page))
    record('No runtime JS errors during the whole run', not errors, errors)
    (work / 'test-results.json').write_text(json.dumps({'browser': browser.version, 'results': results, 'pageErrors': errors}, ensure_ascii=False, indent=2), encoding='utf-8')
    browser.close()
print('TOTAL', len(results), 'PASS', sum(r['passed'] for r in results), flush=True)
