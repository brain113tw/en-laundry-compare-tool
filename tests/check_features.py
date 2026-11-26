"""Developer regression checks for the project file, pinch zoom, HEIC recognition and unsaved-work guard.

Decoding HEIC with the bundled decoder is covered by tests/check_heic.py, which opens the real files.

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
    answer = {'accept': True, 'queue': [], 'seen': []}

    def on_dialog(d):
        answer['seen'].append(d.message)
        ok = answer['queue'].pop(0) if answer['queue'] else answer['accept']
        d.accept() if ok else d.dismiss()
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.on('dialog', on_dialog)
    page.set_content(html)
    page.wait_for_timeout(100)
    page.evaluate("window.__dl = []; window.download = (blob, name) => { window.__dl.push({blob, name}); };")
    record('Starts without script errors', not errors, errors)

    # ------------------------------------------------------------------ HEIC recognition
    # This page is set from a string and has no address, so the bundled decoder cannot be loaded here: a HEIC either decodes natively or is skipped.
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
           native or ('HEIC 無法解碼' in status(page) and 'vendor 資料夾' in status(page) and 'Safari' in status(page) and is_error(page) and page.locator('iframe').count() == 0), status(page))
    if native:
        page.evaluate("resetSession(); syncControls(); renderFiles(); renderCases(); commit(); pushHistory();")
    jpeg = io.BytesIO()
    Image.new('RGB', (64, 64), (200, 30, 30)).save(jpeg, 'JPEG')
    page.locator('#fileInput').set_input_files({'name': 'renamed.heic', 'mimeType': 'image/heic', 'buffer': jpeg.getvalue()})
    wait_for(page, '() => !S.importing')
    page.wait_for_timeout(120)
    record('JPEG renamed to .heic is rejected by signature, not blamed on the browser',
           page.evaluate('S.items.length') == 0 and 'HEIC 無法解碼' not in status(page) and '檔案內容與副檔名不符' in page.locator('#log').text_content())

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
    # In CDP a touchEnd lists the fingers that lift; the others stay down.
    touch('touchEnd', [(1, (c['x'] + 90, c['y']))])
    record('Lifting one finger hands over to a single-finger pan, with no undo step yet',
           page.evaluate("!!S.drag && !S.drag.kind && S.drag.side === 'before'") and page.evaluate('S.history.length') == hist0 and page.evaluate('S.tr.before.scale') == scale)
    x_hand = page.evaluate('S.tr.before.x')
    expect = page.evaluate('30 * geom.W / overlay.getBoundingClientRect().width / geom.before.w * 100')
    touch('touchMove', [(0, (c['x'] - 60, c['y']))])
    moved = page.evaluate('S.tr.before.x') - x_hand
    record('The finger that stays down pans from where it is, without a jump', abs(moved - expect) < 0.6 and page.evaluate('S.tr.before.scale') == scale, (moved, expect))
    touch('touchStart', [(0, (c['x'] - 60, c['y'])), (1, (c['x'] + 60, c['y']))])
    record('A returning second finger resumes the pinch', page.evaluate("!!S.drag && S.drag.kind === 'pinch'"))
    touch('touchMove', [(0, (c['x'] - 60, c['y'])), (1, (c['x'] + 40, c['y']))])
    record('The resumed pinch zooms instead of sliding the photo', page.evaluate('S.tr.before.scale') < scale - 20, page.evaluate('S.tr.before.scale'))
    touch('touchEnd', [])
    scale = page.evaluate('S.tr.before.scale')
    record('The whole multi-finger gesture is one undo step', page.evaluate('S.drag === null') and page.evaluate('S.history.length') == hist0 + 1)
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
    ax = page.evaluate("(() => { const r = overlay.getBoundingClientRect(), b = geom.after; return {x: r.x + (b.x + b.w / 2) / geom.W * r.width, y: r.y + (b.y + b.h / 2) / geom.H * r.height, k: geom.W / r.width / b.w * 100}; })()")
    x0 = page.evaluate('S.tr.after.x')
    page.mouse.move(ax['x'], ax['y']); page.mouse.down(); page.mouse.move(ax['x'] + 25, ax['y'], steps=3)
    page.mouse.down(button='right'); page.mouse.up(button='right')
    page.mouse.move(ax['x'] + 80, ax['y'], steps=4); page.mouse.up()
    moved = page.evaluate('S.tr.after.x') - x0
    record('A right-click during a left-button drag does not cut the drag short', abs(moved - 80 * ax['k']) < 0.8 and page.evaluate('S.drag === null'), (moved, 80 * ax['k']))
    page.evaluate("S.tr = {before: freshTransform(), after: freshTransform()}; syncTransformControls(); commit(); pushHistory();")

    # ------------------------------------------------------------------ unsaved-work guard
    def leave_blocked():
        return page.evaluate("(() => { const ev = new Event('beforeunload', {cancelable: true}); window.dispatchEvent(ev); return ev.defaultPrevented; })()")

    def dl():
        return page.evaluate('window.__dl.length')

    def click_and_download(selector):
        n = dl()
        page.locator(selector).click()
        wait_for(page, '() => !S.busy && !EnToolbox.getState().busy && window.__dl.length >= %d' % (n + 1))
        page.wait_for_timeout(60)

    record('Photos that were only added do not raise the leave prompt', not leave_blocked())
    page.evaluate("S.tr.before.x = 7; syncTransformControls(); commit(); pushHistory();")
    record('Leaving with unexported edits asks for confirmation', leave_blocked())
    click_and_download('.export[data-format="png"]')
    record('A simple comparison is considered done once exported', not leave_blocked())
    # toolbox edits are tracked photo by photo, and separately from the comparison
    two = page.evaluate('S.items.map(i => i.id)')
    page.locator('#toolboxOpen').click(); page.wait_for_timeout(120)
    page.evaluate('id => EnToolbox.select(id)', two[1]); page.locator('[data-tb-tab="rotate"]').click(); page.locator('#tbRotateRight').click(); page.wait_for_timeout(60)
    record('A toolbox setting without crop or masks is unsaved work too', leave_blocked())
    page.locator('#tbBack').click(); page.wait_for_timeout(80)
    page.evaluate("S.tr.after.y = 5; syncTransformControls(); commit(); pushHistory();")
    page.locator('#toolboxOpen').click(); page.wait_for_timeout(120)
    click_and_download('#tbExport')
    record('Exporting a toolbox photo does not cover an unexported comparison', leave_blocked())
    page.locator('#tbBack').click(); page.wait_for_timeout(80)
    click_and_download('.export[data-format="png"]')
    record('With the comparison exported as well, nothing is unsaved', not leave_blocked())
    page.locator('#toolboxOpen').click(); page.wait_for_timeout(120)
    page.evaluate('id => EnToolbox.select(id)', two[0]); page.locator('#tbRotateRight').click()
    page.evaluate('id => EnToolbox.select(id)', two[1]); page.locator('#tbRotateRight').click(); page.wait_for_timeout(60)
    click_and_download('#tbExport')
    record('Exporting one toolbox photo does not cover edits on another', leave_blocked())
    page.evaluate('id => EnToolbox.select(id)', two[0]); page.wait_for_timeout(60)
    click_and_download('#tbExport')
    record('Each toolbox photo is done once it was exported itself', not leave_blocked())
    page.locator('#tbBack').click(); page.wait_for_timeout(80)
    # batch cases are tracked case by case
    page.locator('#casesTab').click(); page.locator('#addCase').click(); page.wait_for_timeout(80)
    record('A new batch case is unsaved work', leave_blocked())
    click_and_download('#batchExport')
    record('Batch cases are done once a ZIP containing them was downloaded', not leave_blocked())
    page.locator('#cases .case button.small').first.click(); page.wait_for_timeout(80)
    record('Opening a batch case for preview is not unsaved work', page.evaluate('!!S.activeCase') and not leave_blocked())
    page.evaluate("S.tr.before.x = 11; syncTransformControls(); commit(); pushHistory();")
    record('Editing inside a batch case raises the prompt again', leave_blocked())
    click_and_download('.export[data-format="png"]')
    record('Exporting the open batch case as a single image covers that case', not leave_blocked())
    page.evaluate("resetSession(); EnToolbox.refresh(); syncControls(); renderFiles(); renderCases(); commit(); pushHistory();")
    page.locator('#photosTab').click()
    record('An emptied session has nothing to lose', not leave_blocked())

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
    def patch_entries(data, replace):
        """Re-write a project, replacing the bytes of the named entries."""
        src = zipfile.ZipFile(io.BytesIO(data)); out = io.BytesIO()
        with zipfile.ZipFile(out, 'w', zipfile.ZIP_STORED) as zz:
            for i in src.infolist():
                zz.writestr(zipfile.ZipInfo(i.filename), replace.get(i.filename, src.read(i.filename)))
        return out.getvalue()

    junk = b'not an image at all' * 10
    rejected('no photo can be shown, so nothing is replaced', patch_entries(project, {'photos/000%d.png' % n: junk for n in (1, 2, 3)}), '都無法載入')

    def twins(o):
        o['photos'][1].update(name=o['photos'][0]['name'], path=o['photos'][0]['path'], lastModified=o['photos'][0]['lastModified'])
    rejected('two photos that share path, size and date', patch_entries(rebuild(project, twins), {'photos/0002.png': z.read('photos/0001.png')}), '重複的照片')

    def overlap(data):
        """Point the directory record of photo 2 at the bytes of photo 1."""
        zz = zipfile.ZipFile(io.BytesIO(data)); one = zz.getinfo('photos/0001.png'); raw = bytearray(data); o = zz.start_dir
        while raw[o:o + 4] == b'PK\x01\x02':
            n, e, c = struct.unpack_from('<HHH', raw, o + 28)
            if raw[o + 46:o + 46 + n] == b'photos/0002.png':
                struct.pack_into('<III', raw, o + 16, one.CRC, one.file_size, one.file_size); struct.pack_into('<I', raw, o + 42, one.header_offset)
            o += 46 + n + e + c
        return bytes(raw)
    rejected('two entries that share the same bytes', overlap(project), '重疊')

    def heic_project(data, count):
        """The same project with its first `count` photos stored as HEIC (as a project saved in Safari would have them)."""
        src = zipfile.ZipFile(io.BytesIO(data)); meta = json.loads(src.read('project.json')); out = io.BytesIO()
        for n in range(count):
            meta['photos'][n].update(name='p%d.heic' % n, path='p%d.heic' % n)
        with zipfile.ZipFile(out, 'w', zipfile.ZIP_STORED) as zz:
            zz.writestr(zipfile.ZipInfo('project.json'), json.dumps(meta, ensure_ascii=False).encode())
            for n, ph in enumerate(meta['photos']):
                heic = ph['name'].endswith('.heic')
                zz.writestr(zipfile.ZipInfo('photos/%04d.%s' % (n + 1, 'heic' if heic else 'png')), heic_fixture.read_bytes() if heic else src.read('photos/%04d.png' % (n + 1)))
            zz.writestr(zipfile.ZipInfo('logo/logo.png'), src.read('logo/logo.png'))
        return out.getvalue()
    if not native:
        rejected('every photo is HEIC and this browser cannot decode HEIC', heic_project(project, 3), 'Safari 17')
    record('No prototype pollution after hostile files', page.evaluate('({}).polluted === undefined && window.bad === undefined'))

    # a size the user still has to correct is restored as it was; the limit is enforced when drawing, not when reading
    open_bytes(page, rebuild(project, lambda o: o['compare']['cfg'].update(width=8192, height=8192, autoHeight=False, layout='custom')))
    record('An over-limit canvas in a project opens as saved and is refused when drawn',
           page.evaluate("S.items.length === 3 && S.cfg.width === 8192 && (() => { try { geometry(currentDoc()); return false; } catch (e) { return true; } })()")
           and '開啟專案檔：' in page.locator('#log').text_content().splitlines()[-1] + page.locator('#log').text_content().splitlines()[-2] and '超出限制' in status(page), status(page))
    if not native:
        open_bytes(page, heic_project(project, 1))
        record('A project with some HEIC photos opens the rest and says why', page.evaluate('S.items.length') == 2 and is_error(page) and 'HEIC' in status(page) and 'Safari 17' in status(page), status(page))

    def lone(o):
        o['compare']['cfg']['title'] = '案例\ud800A'
        o['compare']['cases'][0]['name'] = 'case\udc00'
        return json.dumps(o).encode()
    open_bytes(page, rebuild(project, lone))
    record('Unpaired surrogates in project text are replaced, so every name can be written to a file again',
           page.evaluate("S.cfg.title === '案例\\uFFFDA' && S.cases.every(c => c.name.isWellFormed())"), page.evaluate('JSON.stringify([S.cfg.title, S.cases.map(c => c.name)])'))
    open_bytes(page, rebuild(project, drop='logo/logo.png'))
    record('A recorded logo that cannot be restored is reported', is_error(page) and 'Logo 無法還原' in status(page) and page.evaluate('S.items.length') == 3 and page.evaluate('EnToolbox.projectLogo()') is None, status(page))

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
    open_bytes(page, project)
    whole = snapshot(page)
    answer['queue'] = [True, False]; answer['seen'].clear()
    open_bytes(page, junk_photo(project))
    record('Declining after hearing that a photo cannot be loaded keeps the session', snapshot(page) == whole and '已取消' in status(page) and len(answer['seen']) == 2 and '有 1 張無法載入' in answer['seen'][1], answer['seen'])
    answer['queue'] = []
    n_err = len(errors)
    open_bytes(page, junk_photo(project))
    record('A photo that cannot be decoded is skipped and its references dropped', page.evaluate('''() => S.items.length === 2 && S.before === null && S.tr.before.scale === 100 && S.tr.before.rotation === 0
        && S.cases.every(c => item(c.doc.before) && item(c.doc.after)) && !!item(EnToolbox.getState().active)''') and '無法載入' in status(page) and len(errors) == n_err, status(page))

    # a size the user still has to correct must not block saving the rest of the work
    open_bytes(page, project)
    n_dl = dl()
    page.evaluate("S.cfg.layout = 'custom'; S.cfg.autoHeight = false; S.cfg.width = 8192; S.cfg.height = 8192; syncControls(); commit();")
    page.locator('#saveProject').click()
    wait_for(page, '() => !S.busy && window.__dl.length >= %d' % (n_dl + 1))
    record('A session with an over-limit canvas can still be saved', '專案檔已交給瀏覽器下載' in status(page) and not is_error(page) and page.locator('#saveProject').is_enabled(), status(page))
    open_bytes(page, saved_bytes(page))
    record('It reopens with the same size still to be corrected', page.evaluate('S.cfg.width === 8192 && S.cfg.height === 8192 && S.items.length === 3'), status(page))

    # a source file that can no longer be read is named
    open_bytes(page, project)
    n_dl = dl()
    page.evaluate('''() => { const f = S.items[1].file; S.items[1].file = new Proxy(f, {get(t, k) { if (k === 'arrayBuffer') return () => Promise.reject(new DOMException('gone', 'NotReadableError'));
        const v = t[k]; return typeof v === 'function' ? v.bind(t) : v; }}); }''')
    page.locator('#saveProject').click()
    wait_for(page, '() => !S.busy'); page.wait_for_timeout(80)
    record('A photo whose file can no longer be read is named in the save error', dl() == n_dl and is_error(page) and '照片「demo_after.png」' in status(page) and page.locator('#saveProject').is_enabled(), status(page))

    # a logo with a long file name, stale fields of the replaced session, locking while loading, dropping a project file
    open_bytes(page, project)
    page.locator('#tbLogoInput').set_input_files({'name': 'L' * 150 + '.png', 'mimeType': 'image/png', 'buffer': (work / 'logo.png').read_bytes()})
    wait_for(page, "() => document.querySelector('#tbLogoName').textContent.startsWith('LLL')")
    n_dl = dl()
    page.locator('#saveProject').click()
    wait_for(page, '() => !S.busy && window.__dl.length >= %d' % (n_dl + 1))
    open_bytes(page, saved_bytes(page))
    record('A logo with a very long file name survives save and reopen', page.evaluate("!!EnToolbox.projectLogo() && EnToolbox.projectLogo().name.endsWith('.png')") and not is_error(page), status(page))
    page.locator('#filename').fill('舊檔名'); page.locator('#searchFiles').fill('zzz')
    page.evaluate("document.querySelector('#tbSearch').value = 'zzz'; document.querySelector('#tbBatchPrefix').value = '舊前綴';")
    page.evaluate("window.__lock = []; window.__decode = decodeEntries; decodeEntries = async (...a) => { window.__lock.push(S.busy && EnToolbox.getState().busy && [...document.querySelectorAll('#saveProject,#openProject,#clearFiles,.export')].every(b => b.disabled)); return window.__decode(...a); }; void 0;")
    open_bytes(page, project)
    page.evaluate('decodeEntries = window.__decode; void 0;')
    record('The workspace stays locked while a project loads', page.evaluate('window.__lock.length === 1 && window.__lock[0] === true'), page.evaluate('window.__lock'))
    record('Opening a project clears the previous output name, search filters and batch prefix',
           page.evaluate("['filename', 'searchFiles', 'tbSearch', 'tbBatchPrefix'].every(id => document.getElementById(id).value === '')") and page.locator('#files .file').count() == 3)
    # the output name, the batch format and the toolbox prefix travel with the project
    page.locator('#filename').fill('案例A_輸出')
    page.evaluate("document.querySelector('#batchFormat').value = 'png'; document.querySelector('#tbBatchPrefix').value = 'en_case';")
    n_dl = dl()
    page.locator('#saveProject').click()
    wait_for(page, '() => !S.busy && window.__dl.length >= %d' % (n_dl + 1))
    named_project = saved_bytes(page)
    page.locator('#filename').fill('別的')
    page.evaluate("document.querySelector('#batchFormat').value = 'svg'; document.querySelector('#tbBatchPrefix').value = 'other';")
    open_bytes(page, named_project)
    naming = lambda: page.evaluate("[document.querySelector('#filename').value, document.querySelector('#batchFormat').value, document.querySelector('#tbBatchPrefix').value]")
    record('The output name, batch format and file name prefix are saved in the project and restored', naming() == ['案例A_輸出', 'png', 'en_case'] and not is_error(page), naming())
    open_bytes(page, rebuild(named_project, lambda o: (o['compare'].update(batchFormat='exe', filename='a\u0007b\u0000' + 'x' * 300), o['toolbox'].update(prefix='p\u0001q\u007f' + 'p' * 90))[0]))
    record('Odd values in those fields lose their control characters, are cut to length or replaced by the default',
           naming() == ['ab' + 'x' * 98, 'webp', 'pq' + 'p' * 38] and not is_error(page), [len(v) for v in naming()])
    for label, edit in (('the output name is not text', lambda o: o['compare'].update(filename=7)), ('the file name prefix is not text', lambda o: o['toolbox'].update(prefix=['a']))):
        before_try = naming()
        open_bytes(page, rebuild(named_project, edit))
        record('Rejected, session unchanged: ' + label, is_error(page) and '無法開啟專案檔' in status(page) and naming() == before_try, status(page))
    open_bytes(page, project)
    record('A project written before these fields existed opens with them empty', naming() == ['', 'webp', ''] and not is_error(page), naming())
    record('A reopened project is not unsaved work, and previewing one of its cases does not change that',
           (not leave_blocked(), page.locator('#casesTab').click(), page.locator('#cases .case button.small').first.click(), page.wait_for_timeout(80), page.evaluate('!!S.activeCase') and not leave_blocked(), page.locator('#photosTab').click())[4])
    # keyboard focus survives the batch list being redrawn
    page.locator('#casesTab').click()
    n_cases = page.locator('#cases .case').count()
    page.locator('#cases .case').nth(n_cases - 1).locator('button.small').first.focus()
    page.keyboard.press('Enter'); page.wait_for_timeout(100)
    record('Previewing a batch item from the keyboard keeps focus on that button',
           n_cases >= 2 and page.evaluate("document.activeElement.textContent === '預覽 / 調整' && document.activeElement.closest('.case') === [...document.querySelectorAll('#cases .case')].at(-1) && document.activeElement.closest('.case').classList.contains('active')"), n_cases)
    page.locator('#cases .case').first.locator('button.danger').focus()
    page.keyboard.press('Enter'); page.wait_for_timeout(100)
    record('Removing a batch item from the keyboard moves focus to the item that takes its place',
           page.locator('#cases .case').count() == n_cases - 1 and page.evaluate("document.activeElement.textContent === '移除' && document.activeElement.closest('.case') === document.querySelector('#cases .case')"))
    # a held Enter key repeats: it must not take the next item with it
    before_hold = page.locator('#cases .case').count()
    page.evaluate("for (let n = 0; n < 4; n++) S.cases.push({id: uid(), name: 'hold ' + n, checked: false, doc: clone(S.cases[0].doc)}); renderCases();")
    held = page.locator('#cases .case').count()
    page.locator('#cases .case').first.locator('button.danger').focus()
    for _ in range(5):
        page.keyboard.down('Enter')
    page.keyboard.up('Enter'); page.wait_for_timeout(100)
    record('Holding Enter on a remove button removes one item, not the ones that move up', held == before_hold + 4 and page.locator('#cases .case').count() == held - 1, (before_hold, held, page.locator('#cases .case').count()))
    page.keyboard.press('Enter'); page.wait_for_timeout(80)
    record('A fresh press of Enter removes the next one as before', page.locator('#cases .case').count() == held - 2)
    page.locator('#photosTab').click()
    page.evaluate("status('x')")
    page.evaluate('''b64 => { const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0)), dt = new DataTransfer(); dt.items.add(new File([bytes], 'dropped.enproj'));
        document.querySelector('#files').dispatchEvent(new DragEvent('drop', {bubbles: true, cancelable: true, dataTransfer: dt})); }''', base64.b64encode(project).decode())
    wait_for(page, "() => !S.busy && !S.importing && document.querySelector('#status').textContent.includes('已開啟專案檔')")
    page.wait_for_timeout(150)
    record('A single project file dropped on the photo list is opened', snapshot(page) == before_state, status(page))
    page.evaluate("resetSession(); EnToolbox.refresh(); syncControls(); renderFiles(); renderCases(); commit(); pushHistory();")
    n_dl = dl()
    page.locator('#saveProject').click(); page.wait_for_timeout(100)
    record('Saving with no photos explains instead of producing an empty file', dl() == n_dl and '沒有照片可儲存' in status(page))
    # ------------------------------------------------------------------ total-pixel budget
    huge = io.BytesIO(); Image.new('P', (9000, 6500), 3).save(huge, 'PNG', compress_level=1)
    set_device = '''([mem, mobile, mouse = true]) => { Object.defineProperty(navigator, 'deviceMemory', {configurable: true, get: () => mem});
        Object.defineProperty(navigator, 'userAgentData', {configurable: true, get: () => mobile === null ? undefined : ({mobile})});
        window.__matchMedia = window.__matchMedia || window.matchMedia; window.matchMedia = q => q === '(pointer:fine)' ? {matches: mouse} : window.__matchMedia.call(window, q); return pixelBudget(); }'''
    budgets = [page.evaluate(set_device, v) for v in ([16, False], [8, False], [4, False], [None, False], [8, True], [8, None], [16, False, False])]
    record('The photo budget is larger only on desktop browsers that report 8 GB of memory or more and are driven by a mouse or trackpad',
           budgets == [240000000, 240000000, 120000000, 120000000, 120000000, 120000000, 120000000], budgets)

    def add_huge(names):
        page.evaluate("status('…')")
        page.locator('#fileInput').set_input_files([{'name': n, 'mimeType': 'image/png', 'buffer': huge.getvalue()} for n in names])
        wait_for(page, "() => !S.importing && document.querySelector('#status').textContent.includes('已加入')", 180)
    page.evaluate(set_device, [4, False])
    add_huge(['huge1.png', 'huge2.png', 'huge3.png'])
    record('Photos beyond the budget are skipped and the reason names the budget', page.evaluate('S.items.map(i => i.file.name)') == ['huge1.png', 'huge2.png']
           and '略過：huge3.png（已載入照片合計超過 1.2 億像素，請拆批）' in page.locator('#log').text_content(), status(page))
    page.evaluate(set_device, [8, False])
    add_huge(['huge3.png'])
    record('The larger budget accepts the photo the smaller one refused', page.evaluate('S.items.length') == 3 and not is_error(page), status(page))
    page.evaluate("delete navigator.deviceMemory; delete navigator.userAgentData; window.matchMedia = window.__matchMedia; resetSession(); EnToolbox.refresh(); syncControls(); renderFiles(); renderCases(); commit(); pushHistory();")
    record('No runtime JS errors during the whole run', not errors, errors)
    (work / 'test-results.json').write_text(json.dumps({'browser': browser.version, 'results': results, 'pageErrors': errors}, ensure_ascii=False, indent=2), encoding='utf-8')
    browser.close()
print('TOTAL', len(results), 'PASS', sum(r['passed'] for r in results), flush=True)
