from pathlib import Path
from playwright.sync_api import sync_playwright
import json, base64, re, hashlib, zipfile, io, time
from PIL import Image
import tempfile, shutil, os
root=Path(__file__).resolve().parents[1]; work=Path(tempfile.mkdtemp(prefix='en-compare-test-'))
from PIL import ImageDraw
for name,col in [('demo_before.png',(152,160,174)),('demo_after.png',(110,158,167))]:
 im=Image.new('RGB',(720,960),(239,240,236));d=ImageDraw.Draw(im)
 d.rounded_rectangle((160,180,555,790),radius=48,fill=col,outline=(45,71,70),width=5)
 d.rounded_rectangle((247,111,475,237),radius=45,outline=(45,71,70),width=18)
 d.rounded_rectangle((200,550,515,720),radius=22,outline=(248,248,235),width=8)
 d.ellipse((285,325,435,470),fill=(236,216,150));d.line((164,514,550,514),fill=(247,247,235),width=8)
 im.save(work/name)
print('Temporary test artifacts:',work)
html=(root/'index.html').read_text()
results=[]
def record(name,ok,detail=''):
 results.append({'test':name,'passed':bool(ok),'detail':str(detail)})
 print(('PASS ' if ok else 'FAIL ')+name,detail)
 assert ok,(name,detail)
def wait_text(page,selector,text,seconds=15):
 for _ in range(int(seconds*20)):
  if text in page.locator(selector).text_content():return
  page.wait_for_timeout(50)
 raise AssertionError((selector,page.locator(selector).text_content()))
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path=os.environ.get('CHROMIUM_EXECUTABLE') or shutil.which('chromium'),headless=True)
 context=browser.new_context(viewport={'width':1440,'height':980},accept_downloads=True)
 page=context.new_page(); errors=[];reqs=[]
 page.on('pageerror',lambda e:errors.append(str(e)));page.on('request',lambda r:reqs.append(r.url));page.on('dialog',lambda d:d.accept())
 page.set_content(html)
 record('CSP script hash matches source',base64.b64encode(hashlib.sha256(re.search(r'<script>([\s\S]*?)</script>',html)[1].encode()).digest()).decode() in html)
 record('Starts without JS errors',not errors,errors)
 record('Storage unavailable handled', '未能讀取' in page.locator('#storageNote').text_content())
 files=[work/'demo_before.png',work/'demo_after.png']
 page.locator('#fileInput').set_input_files([str(f) for f in files]);wait_text(page,'#encodeState','完成')
 record('Import normal PNGs',page.evaluate('S.items.length')==2)
 record('Output size values exist',page.locator('#sizeWebp').text_content()!='—')
 # Test HTML DOM drop on left blank region, avoids browser-native navigation.
 payload=base64.b64encode(files[0].read_bytes()).decode()
 page.evaluate('''data=>{const b=Uint8Array.from(atob(data),c=>c.charCodeAt(0));const dt=new DataTransfer();dt.items.add(new File([b],'drop.png',{type:'image/png'}));document.querySelector('#files').dispatchEvent(new DragEvent('drop',{bubbles:true,cancelable:true,dataTransfer:dt}));}''',payload)
 wait_text(page,'#status','已加入 1 張')
 record('Left blank area handles drop',page.evaluate('S.items.length')==3)
 # Invalid file masquerading as raster (no script inserted in app).
 page.locator('#fileInput').set_input_files({'name':'not-a-photo.jpg','mimeType':'image/jpeg','buffer':b'<svg xmlns="http://www.w3.org/2000/svg"><script>window.bad=1</script></svg>'})
 wait_text(page,'#status','略過 1 張')
 record('Reject renamed SVG input',page.evaluate('S.items.length')==3 and page.evaluate('window.bad===undefined'))
 # JSON validation and atomic state preservation.
 invalids=[{'cfg':None},{'cfg':[]},{'cfg':{'quality':'90'}},{'cfg':{'showLabels':'false'}},{'cfg':{'labelTextColor':'url(https://x.invalid)'}},{'cfg':{'layout':'unknown'}},{'cfg':{'title':{'x':1}}},{'cfg':{'width':8192,'height':8192,'autoHeight':False}}]
 before=page.evaluate('JSON.stringify(S.cfg)')
 for n,obj in enumerate(invalids):
  page.locator('#settingsInput').set_input_files({'name':'bad.json','mimeType':'application/json','buffer':json.dumps(obj).encode()})
  page.wait_for_timeout(90)
  record('Invalid cfg rejected '+str(n+1), page.evaluate('JSON.stringify(S.cfg)')==before and page.locator('#status').get_attribute('class')=='error')
 for name,s in [('prototype', '{"cfg":{"quality":80,"__proto__":{"polluted":true}}}'),('deep','{"cfg":{"quality":80},"nested":'+ '['*20+'0'+']'*20+'}'),('oversize',' '*1048577),('syntax','{')]:
  page.locator('#settingsInput').set_input_files({'name':name+'.json','mimeType':'application/json','buffer':s.encode()});page.wait_for_timeout(120)
  record('Reject '+name,page.evaluate('JSON.stringify(S.cfg)')==before)
 record('No prototype pollution',page.evaluate('({}).polluted===undefined'))
 # Oversize files rejected before invoking text().
 record('JSON size guard precedes reading',page.evaluate('''async()=>{let read=false;try{await readJSONFile({size:1048577,text(){read=true;return '{}';}});}catch(_){}return !read;}'''))
 good={'version':'5.8','cfg':{'quality':999,'background':'#F1EDE4','unknown':'discard','layout':'custom','autoHeight':False,'width':1600,'height':900,'showTitle':True,'title':'操作示意｜非真實清洗案例'}}
 page.locator('#settingsInput').set_input_files({'name':'legacy.json','mimeType':'application/json','buffer':json.dumps(good,ensure_ascii=False).encode()});wait_text(page,'#status','設定檔已載入')
 record('v5.8 import compatibility + clamp + allowlist',page.evaluate("S.cfg.quality===100 && S.cfg.background==='#f1ede4' && !Object.hasOwn(S.cfg,'unknown') && geometry(currentDoc()).W===1600"))
 # UI decimal retention.
 page.locator('#beforeLabelX').fill('12.3');page.locator('#beforeLabelX').press('Tab')
 record('Fractional positions preserved',page.evaluate('S.cfg.beforeLabelX===12.3'))
 # Watermark text must receive hit before background.
 record('Watermark text above background hit',page.evaluate("(()=>{const w=watermarkRectFor(geometry(currentDoc()),S.cfg);geom=geometry(currentDoc());return hit({x:w.cx,y:w.cy,cssScale:1})==='watermark';})()"))
 # Mouse drag actual watermark separate from bar.
 page.locator('#editorTab').click();page.wait_for_timeout(120)
 coords=page.evaluate("(()=>{const r=overlay.getBoundingClientRect(),w=watermarkRectFor(geom,S.cfg);return {x:r.x+w.cx/geom.W*r.width,y:r.y+w.cy/geom.H*r.height,bar:S.cfg.watermarkBarY};})()")
 page.mouse.move(coords['x'],coords['y']);page.mouse.down();page.mouse.move(coords['x']-40,coords['y']-80,steps=8);page.mouse.up();page.wait_for_timeout(90)
 record('Dragging watermark leaves bar unchanged',page.evaluate('S.cfg.watermarkY<97') and page.evaluate('S.cfg.watermarkBarY')==coords['bar'])
 # Wheel events on labels/title/bar no longer access undefined image transforms.
 page.evaluate("(()=>{const ev=(r)=>{if(!r)return;const a=overlay.getBoundingClientRect();overlay.dispatchEvent(new WheelEvent('wheel',{clientX:a.x+(r.x+r.w/2)/geom.W*a.width,clientY:a.y+(r.y+r.h/2)/geom.H*a.height,deltaY:100,bubbles:true,cancelable:true}));};ev(titleRectFor(geom,S.cfg));ev(watermarkRectFor(geom,S.cfg));ev(watermarkBarRectFor(geom,S.cfg));ev(labelRectFor('before',geom,S.cfg));})()")
 record('Wheel over non-photo objects no exception',not errors,errors)
 # Restore canonical screenshots/document examples.
 page.evaluate("S.cfg.title='操作示意｜非真實清洗案例';S.cfg.watermarkX=50;S.cfg.watermarkY=97;S.cfg.quality=88;syncControls();commit();pushHistory();")
 # Actual blobs and byte counts, no download required by host restrictions.
 for fmt in ['webp','png','svg']:
  obj=page.evaluate('''async f=>{const a=await ensureAssets(currentDoc());return {url:await blobDataURL(a.blobs[f]),size:a.blobs[f].size,w:a.g.W,h:a.g.H,type:a.blobs[f].type};}''',fmt)
  data=base64.b64decode(obj['url'].split(',',1)[1]);(work/('test_export.'+fmt)).write_bytes(data)
  dims=Image.open(io.BytesIO(data)).size if fmt!='svg' else (int(re.search(rb'width="(\d+)"',data)[1]),int(re.search(rb'height="(\d+)"',data)[1]))
  record(fmt.upper()+' real encoding / dimensions / bytes',dims==(1600,900) and len(data)==obj['size'],str(dims)+' / '+str(len(data)))
 # Guide overlay doesn't alter exported bitmap.
 page.locator('#guide').select_option('center60');page.wait_for_timeout(80)
 data2=page.evaluate('''async()=>{const a=await ensureAssets(currentDoc());return await blobDataURL(a.blobs.png);}''')
 record('Guides not exported',base64.b64decode(data2.split(',',1)[1])==(work/'test_export.png').read_bytes())
 page.locator('#guide').select_option('none')
 # ZIP actual structure and CRC.
 zipdata=page.evaluate('''async()=>{const d=currentDoc();const r=await encodeFormat(d,'webp');return await blobDataURL(await zipFiles([{name:'示意案例.webp',blob:r.blob},{name:'export_report.json',blob:new Blob(['{}'],{type:'application/json'})}]));}''')
 zb=base64.b64decode(zipdata.split(',',1)[1]);(work/'test_export.zip').write_bytes(zb)
 with zipfile.ZipFile(io.BytesIO(zb)) as z:record('ZIP Unicode filename and CRC',z.testzip() is None and '示意案例.webp' in z.namelist())
 # Favorites transactions and persistent-denial honest status.
 page.locator('#favoriteName').fill('網站示意');page.locator('#saveFavorite').click()
 record('Storage failure reported (not falsely saved)', '暫存' in page.locator('#status').text_content())
 fbefore=page.evaluate('JSON.stringify(favorites)')
 page.locator('#favoritesInput').set_input_files({'name':'bad-fav.json','mimeType':'application/json','buffer':json.dumps({'favorites':[{'name':'bad','cfg':{'quality':None}}]}).encode()});page.wait_for_timeout(100)
 record('Bad favorites keep existing entries',page.evaluate('JSON.stringify(favorites)')==fbefore)
 page.locator('#favoritesInput').set_input_files({'name':'fav.json','mimeType':'application/json','buffer':json.dumps({'type':'favorites','favorites':[{'name':'<img src=x onerror=alert(1)>','cfg':{'quality':80}}]}).encode()});page.wait_for_timeout(100)
 record('Template name rendered as literal text',page.locator('#favoriteList img').count()==0 and '<img' in page.locator('#favoriteList .favname').text_content())
 # Undo/redo after numeric edit and snapshot reset on clear.
 page.evaluate('checkpoint();S.cfg.quality=67;commit();pushHistory();')
 page.locator('#undoBtn').click();record('Undo config works',page.evaluate('S.cfg.quality')!=67)
 page.locator('#redoBtn').click();record('Redo config works',page.evaluate('S.cfg.quality')==67)
 # Screenshots use deliberate demo names, not malicious test labels.
 page.evaluate("favorites=[{id:uid(),name:'網站案例 1600×900',cfg:clone(S.cfg)}];S.cfg.quality=88;syncControls();commit();renderFavorites();")
 page.locator('#settings').evaluate('(e)=>e.scrollTop=0');page.locator('.workspace').evaluate('(e)=>e.scrollTop=0');page.wait_for_timeout(200)
 page.screenshot(path=str(work/'main-editor.png'),full_page=True)
 page.locator('#socialTab').click();page.wait_for_timeout(150);page.screenshot(path=str(work/'social-preview.png'),full_page=True)
 page.locator('#editorTab').click();page.locator('#favoriteName').scroll_into_view_if_needed();page.wait_for_timeout(100);page.screenshot(path=str(work/'favorites.png'),full_page=True)
 page.set_viewport_size({'width':1366,'height':768});page.wait_for_timeout(150);page.screenshot(path=str(work/'layout-1366.png'),full_page=True)
 record('Desktop has no horizontal overflow',page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
 # CSP fail-closed test. These expected violations are deliberately generated by the test.
 page.evaluate("(()=>{let s=document.createElement('script');s.textContent='window.injectedByTest=1';document.head.appendChild(s);})()")
 record('Unhashed inline script blocked',page.evaluate('window.injectedByTest===undefined'))
 record('unsafe-eval not allowed in policy', "'unsafe-eval'" not in html)
 record('Fetch blocked by CSP',page.evaluate("async()=>{try{await fetch('https://example.invalid/security-test');return false;}catch(_){return true;}}"))
 record('No ordinary remote subresource requests',not any(u.startswith(('http:','https:')) and 'example.invalid' not in u for u in reqs),reqs[:5])
 page.evaluate('S.busy=false;')
 page.locator('#clearFiles').click();record('Clear resets undo before releasing sources',page.evaluate('S.items.length===0&&S.history.length===1&&S.future.length===0'))
 record('No unhandled JS runtime errors',not errors,errors)
 meta={'browser':browser.version,'platform':'Linux; Chromium headless, about:blank set_content (navigation blocked by environment policy)','results':results,'unhandled_errors':errors,'storage_test':'Storage-denied real path tested; cross-session persistence not browser-end-to-end verified.'}
 (work/'test-results.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2))
 browser.close()
