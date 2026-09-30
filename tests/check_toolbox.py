from pathlib import Path
from playwright.sync_api import sync_playwright
from PIL import Image, ImageDraw
import json, re, base64, hashlib, io, zipfile, traceback
import tempfile,shutil,os
root=Path(__file__).resolve().parents[1]
w=Path(tempfile.mkdtemp(prefix='en-toolbox-tests-'));f=w/'fixtures';f.mkdir(exist_ok=True)
# Calibration pictures are synthetic fixtures, not customer photos.
for n,col in [('bag-before',(117,138,143)),('bag-after',(98,156,169))]:
 im=Image.new('RGB',(800,600),(239,237,228));dd=ImageDraw.Draw(im)
 dd.rounded_rectangle((235,105,585,510),35,fill=col,outline=(42,75,72),width=6)
 dd.rounded_rectangle((320,60,498,157),30,outline=(42,75,72),width=15)
 dd.rounded_rectangle((265,340,555,465),20,outline=(237,228,198),width=10)
 dd.rectangle((0,0,90,75),fill=(210,30,40));dd.rectangle((710,0,800,75),fill=(20,160,65));dd.rectangle((0,525,90,600),fill=(20,40,190));dd.rectangle((710,525,800,600),fill=(230,180,25));dd.text((25,285),'DEMO / SYNTHETIC TEST',fill=(80,95,90))
 im.save(f/(n+'.png'))
flat=Image.new('RGB',(400,300),(120,130,140));flat.save(f/'flat.png')
a=Image.new('RGBA',(400,300),(0,0,0,0));ImageDraw.Draw(a).ellipse((100,50,300,250),fill=(220,40,70,255));a.save(f/'transparent.png')
html=(root/'index.html').read_text();results=[]
def record(name,ok,detail=''):
 results.append({'test':name,'passed':bool(ok),'detail':str(detail)});print(('PASS ' if ok else 'FAIL ')+name,detail,flush=True)
 if not ok:raise AssertionError(name+': '+str(detail))
def value(page,k,v):
 selector='#tb-'+k
 if isinstance(v,bool): page.locator(selector).set_checked(v)
 elif page.locator(selector).evaluate('(e)=>e.tagName')=='SELECT': page.select_option(selector,str(v))
 elif page.locator(selector).get_attribute('type') in ('range','color'):
  page.locator(selector).evaluate('(e,v)=>{e.value=v;e.dispatchEvent(new Event("input",{bubbles:true}));e.dispatchEvent(new Event("change",{bubbles:true}));}',str(v))
 else: page.locator(selector).fill(str(v));page.locator(selector).press('Tab')
 page.wait_for_timeout(60)
def state(p):return p.evaluate('EnToolbox.getState()')
def coreImage(p, overrides=None):
 data=p.evaluate('''opts=>{const s=EnToolbox.getState();let d=s.doc;if(opts)Object.assign(d.cfg,opts);const r=EnToolbox.core.renderDoc(item(s.active),d,null);return {data:r.cv.toDataURL('image/png'),w:r.g.W,h:r.g.H};}''',overrides)
 return Image.open(io.BytesIO(base64.b64decode(data['data'].split(',',1)[1]))).convert('RGBA'),data
with sync_playwright() as p:
 b=p.chromium.launch(executable_path=os.environ.get('CHROMIUM_EXECUTABLE') or shutil.which('chromium'),headless=True,args=['--no-sandbox']);ctx=b.new_context(viewport={'width':1440,'height':1000},accept_downloads=True);page=ctx.new_page();errors=[];req=[]
 page.on('pageerror',lambda e:errors.append(str(e)));page.on('request',lambda r:req.append(r.url));page.on('dialog',lambda d:d.accept())
 try:
  page.set_content(html);page.wait_for_timeout(100)
  scripts=re.findall(r'<script>([\s\S]*?)</script>',html)
  record('Both inline script hashes match CSP',all(base64.b64encode(hashlib.sha256(s.encode()).digest()).decode() in html for s in scripts))
  record('Initialization without script errors',not errors,errors)
  page.locator('#fileInput').set_input_files([str(f/'bag-before.png'),str(f/'bag-after.png')]);page.wait_for_function('() => (S.items.length===2&&!S.importing)');page.wait_for_timeout(150)
  record('Existing comparison imports and renders',page.evaluate('ready() && geom.W===1600'))
  page.click('#toolboxOpen');page.wait_for_timeout(150)
  record('Full-screen toolbox opens with shared photo library',page.locator('#tbApp').is_visible() and page.locator('.tb-file').count()==2)
  record('Batch starts with no implicit selections',state(page)['checked']==[])
  record('Default sizing never stretches/upscales',page.locator('#tbOutputMeta').text_content().startswith('800 × 600'))
  record('LocalStorage unavailable shows explicit fallback','不可用' in page.locator('#tbStorageNote').text_content())
  im,geo=coreImage(page);record('Full unaltered raster keeps source dimensions',im.size==(800,600))
  page.click('[data-tb-preset="square"]');im,_=coreImage(page);record('Square canvas letterboxes instead of stretching',im.size==(1080,1080) and im.getpixel((10,10))==(255,255,255,255))
  value(page,'transparent',True);value(page,'format','png');im,_=coreImage(page);record('PNG preserves transparent margins',im.getpixel((10,10))[3]==0)
  value(page,'format','jpg');im,_=coreImage(page);record('JPG flattens transparent margins to chosen background',im.getpixel((10,10))==(255,255,255,255))
  value(page,'format','webp');value(page,'sizeMode','original');value(page,'transparent',False)
  page.click('[data-tb-tab="rotate"]');page.click('#tbRotateRight');im,_=coreImage(page)
  record('90 degree rotation swaps width and height',im.size==(600,800))
  record('Rotation preserves coloured calibration geometry',im.getpixel((570,40))[:3]==(210,30,40))
  page.click('#tbRotateLeft');page.click('[data-tb-tab="crop"]');page.select_option('#tbCropAspect','1');page.wait_for_timeout(100)
  record('Crop ratio set on source gives 600x600',state(page)['doc']['crop']['w']==.75)
  record('Crop mode is clearly labeled non-export preview','不是輸出' in page.locator('#tbViewBadge').text_content())
  page.click('#tbFinishCrop');im,_=coreImage(page);record('Crop really changes encoded geometry',im.size==(600,600))
  page.click('[data-tb-tab="crop"]');page.click('#tbCropClear');page.click('[data-tb-tab="privacy"]');page.click('#tbMaskAdd');page.wait_for_timeout(100)
  im,_=coreImage(page);d=state(page)['doc'];m=d['masks'][0];x=int((m['x']+m['w']/2)*800);y=int((m['y']+m['h']/2)*600)
  record('Solid privacy mask is 100% opaque in output',im.getpixel((x,y))==(20,25,23,255))
  maskdiff='''(type)=>{const s=EnToolbox.getState(),src=item(s.active);const d=JSON.parse(JSON.stringify(s.doc)),base=JSON.parse(JSON.stringify(s.doc));d.cfg.sizeMode=base.cfg.sizeMode='original';d.crop=base.crop=null;const m={x:.02,y:.02,w:.2,h:.15};base.masks=[];d.masks=[{...m,type,strength:20}];const a=EnToolbox.core.renderDoc(src,d,null),b=EnToolbox.core.renderDoc(src,base,null);const W=a.g.W,H=a.g.H,x0=Math.floor(m.x*W),y0=Math.floor(m.y*H),w=Math.floor(m.w*W),h=Math.floor(m.h*H);const pa=a.cv.getContext('2d').getImageData(x0,y0,w,h).data,pb=b.cv.getContext('2d').getImageData(x0,y0,w,h).data;let diff=0,n=0;for(let i=0;i<pa.length;i+=4){diff+=Math.abs(pa[i]-pb[i])+Math.abs(pa[i+1]-pb[i+1])+Math.abs(pa[i+2]-pb[i+2]);n++;}return diff/n;}'''
  record('Blur privacy mask changes the masked region',page.evaluate(maskdiff,'blur')>3,page.evaluate(maskdiff,'blur'))
  record('Mosaic privacy mask changes the masked region',page.evaluate(maskdiff,'mosaic')>3,page.evaluate(maskdiff,'mosaic'))
  record('Mask strength is defined in source pixels, independent of crop',page.evaluate('''()=>{const s=EnToolbox.getState(),src=item(s.active);const full=JSON.parse(JSON.stringify(s.doc)),cropped=JSON.parse(JSON.stringify(s.doc));const m={x:.3,y:.2,w:.2,h:.2,type:'mosaic',strength:40};full.masks=[m];full.crop=null;cropped.masks=[m];cropped.crop={x:.25,y:.1,w:.5,h:.5};cropped.cfg.sizeMode='original';full.cfg.sizeMode='original';const a=EnToolbox.core.renderDoc(src,full,null),b=EnToolbox.core.renderDoc(src,cropped,null);const run=(cv,x0,y0,w)=>{const d=cv.getContext('2d').getImageData(x0,y0,w,1).data;let changes=0;for(let i=4;i<d.length;i+=4)if(d[i]!==d[i-4]||d[i+1]!==d[i-3]||d[i+2]!==d[i-2])changes++;return changes;};const ya=Math.floor((m.y+m.h/2)*src.h),yb=Math.floor((m.y+m.h/2-cropped.crop.y)*src.h);const ca=run(a.cv,Math.floor(m.x*src.w)+2,ya,Math.floor(m.w*src.w)-4),cb=run(b.cv,Math.floor((m.x-cropped.crop.x)*src.w)+2,yb,Math.floor(m.w*src.w)-4);return Math.abs(ca-cb)<=2;}'''))
  # Pointer drag actual mask center; no container misalignment.
  bb=page.locator('#tbOverlay').bounding_box();px=bb['x']+(m['x']+m['w']/2)*bb['width'];py=bb['y']+(m['y']+m['h']/2)*bb['height']
  page.mouse.move(px,py);page.mouse.down();page.mouse.move(px+35,py+20,steps=6);page.mouse.up();page.wait_for_timeout(90)
  m2=state(page)['doc']['masks'][0];record('Pointer drag moves actual privacy region',m2['x']>m['x'] and m2['y']>m['y'])
  page.click('#tbMaskDuplicate');record('Duplicate adds independent privacy mask',len(state(page)['doc']['masks'])==2)
  page.click('#tbMaskDelete');record('Delete only affects selected mask',len(state(page)['doc']['masks'])==1)
  page.click('#tbUndo');record('Toolbox undo restores deleted mask',len(state(page)['doc']['masks'])==2)
  page.click('#tbRedo');record('Toolbox redo reapplies delete',len(state(page)['doc']['masks'])==1)
  # Switching images must not leak or lose local edits.
  ids=page.evaluate('S.items.map(i=>i.id)');page.evaluate('(id)=>EnToolbox.select(id)',ids[1]);record('Second image has its own empty masks',state(page)['doc']['masks']==[])
  page.evaluate('(id)=>EnToolbox.select(id)',ids[0]);record('First image retains its privacy edits',len(state(page)['doc']['masks'])==1)
  # Marking and logo.
  page.click('[data-tb-tab="mark"]');value(page,'textOn',True);value(page,'text','TEST MARK');value(page,'textX',0);value(page,'textY',0);value(page,'textOpacity',0)
  record('Numeric zero opacity and x/y values are respected',all(state(page)['doc']['cfg'][k]==0 for k in ['textX','textY','textOpacity']))
  value(page,'textOpacity',90);page.locator('#tbLogoInput').set_input_files(str(f/'transparent.png'));page.wait_for_function('() => (document.querySelector("#tbLogoName").textContent.includes("transparent.png"))')
  record('Logo can be loaded offline',page.locator('#tbLogoName').text_content().startswith('transparent.png'))
  # Move text to uncovered location with controls; pointer center should move without touching logo.
  value(page,'textX',70);value(page,'textY',80);page.wait_for_timeout(100)
  # Compute current text bounds from preview font (same sizing) using utility render? locate by image-space state.
  bb=page.locator('#tbOverlay').bounding_box();cfg=state(page)['doc']['cfg'];textW=page.evaluate('(()=>{let c=document.createElement("canvas").getContext("2d");c.font=\'600 28px "Microsoft JhengHei","Segoe UI",sans-serif\';return c.measureText("TEST MARK").width+12;})()')
  px=bb['x']+((800-textW)*.7+textW/2)/800*bb['width'];py=bb['y']+((600-42)*.8+21)/600*bb['height']
  page.mouse.move(px,py);page.mouse.down();page.mouse.move(px-40,py-30,steps=6);page.mouse.up();page.wait_for_timeout(100)
  record('Text watermark is draggable in final preview',state(page)['doc']['cfg']['textX']<70 and state(page)['doc']['cfg']['textY']<80)
  page.click('[data-tb-tab="draw"]');page.click('#tbDrawAdd');record('Arrow annotation added without altering source',len(state(page)['doc']['shapes'])==1)
  # Saturation 0 and constant-patch sharpening check.
  page.click('[data-tb-tab="adjust"]');value(page,'saturation',0);im,_=coreImage(page);pix=im.getpixel((400,300));record('Saturation 0 reaches grayscale',abs(pix[0]-pix[1])<=1 and abs(pix[1]-pix[2])<=1,pix)
  page.click('#tbNeutral');record('Original-look button resets tonal adjustments',state(page)['doc']['cfg']['saturation']==100 and state(page)['doc']['cfg']['sharpness']==0)
  # Import flat source for DC-preserving sharpening.
  page.locator('#tbInput').set_input_files(str(f/'flat.png'));page.wait_for_function('() => (S.items.length===3&&!S.importing)');idflat=page.evaluate('S.items[2].id');page.evaluate('(id)=>EnToolbox.select(id)',idflat)
  page.click('[data-tb-tab="adjust"]');value(page,'sharpness',80);im,_=coreImage(page);record('Sharpening preserves flat-region brightness',im.getpixel((200,150))[:3]==(120,130,140),im.getpixel((200,150)))
  # Incorrect file rejected with no DOM XSS.
  before=page.evaluate('S.items.length');page.locator('#tbInput').set_input_files({'name':'fake.png','mimeType':'image/png','buffer':b'<svg onload="window.pwned=1"/>'});page.wait_for_timeout(250)
  record('Toolbox reuses image signature validation',page.evaluate('S.items.length')==before and page.evaluate('window.pwned===undefined'))
  # File drop accepted over whole toolbox blank/library region.
  raw=base64.b64encode((f/'transparent.png').read_bytes()).decode();page.evaluate('''s=>{let dt=new DataTransfer();dt.items.add(new File([Uint8Array.from(atob(s),c=>c.charCodeAt(0))],'dropped.png',{type:'image/png'}));document.querySelector('#tbFiles').dispatchEvent(new DragEvent('drop',{dataTransfer:dt,bubbles:true,cancelable:true}));}''',raw)
  page.wait_for_function('() => (S.items.length===4&&!S.importing)');record('Whole toolbox accepts dropped files once',page.evaluate('S.items.length')==4)
  # Save and validate named presets; denied storage is explicit rather than false success.
  page.click('[data-tb-tab="presets"]');page.fill('#tbPresetName','網站單張');page.click('#tbSavePreset');record('Named preset kept in session',len(state(page)['presets'])==1)
  record('Denied persistent save explicitly asks backup','暫存' in page.locator('#tbStatus').text_content())
  old=json.dumps(state(page)['presets'],ensure_ascii=False);bad={'type':'en-toolbox-presets','presets':[{'name':'bad','cfg':{'quality':'99'}}]}
  page.locator('#tbPresetInput').set_input_files({'name':'bad.json','mimeType':'application/json','buffer':json.dumps(bad).encode()});page.wait_for_timeout(100)
  record('Invalid preset import is atomic',json.dumps(state(page)['presets'],ensure_ascii=False)==old)
  good={'type':'en-toolbox-presets','presets':[{'name':'新網站','cfg':{'width':1600,'height':900,'sizeMode':'box','quality':88,'textOn':False,'extra':'discard'}}]}
  page.locator('#tbPresetInput').set_input_files({'name':'good.json','mimeType':'application/json','buffer':json.dumps(good).encode()});page.wait_for_timeout(130)
  record('Preset import validates and drops unknown fields',state(page)['presets'][0]['name']=='新網站' and 'extra' not in state(page)['presets'][0]['cfg'])
  record('Large JSON is rejected before parse',page.evaluate("(()=>{try{parseBoundedJSON(' '.repeat(1048577));return false;}catch(e){return true;}})()"))
  record('Prototype key is rejected',page.evaluate('''(()=>{try{parseBoundedJSON('{"cfg":{"__proto__":{"x":1}}}');return false;}catch(e){return true;}})()'''))
  # Capture application downloads to bytes (not OS/browser save dialogs).
  page.evaluate('window.savedFiles=[];download=(blob,name)=>{window.savedFiles.push({blob,name});};void 0;')
  page.click('#tbExportPresets');record('Presets export genuine JSON blob',page.evaluate('savedFiles.at(-1).name')=='en_toolbox_presets_v6_2.json')
  # Export 3 real encodings through UI.
  page.click('[data-tb-tab="size"]');value(page,'sizeMode','original')
  for fmt in ['webp','png','jpg']:
   value(page,'format',fmt);num=page.evaluate('savedFiles.length');page.click('#tbExport');page.wait_for_function('(n)=>savedFiles.length>n',arg=num,timeout=20000);page.wait_for_function('() => (!EnToolbox.getState().busy)')
   result=page.evaluate('''async()=>{const f=savedFiles.at(-1);return {name:f.name,mime:f.blob.type,url:await blobDataURL(f.blob),size:f.blob.size};}''');data=base64.b64decode(result['url'].split(',',1)[1]);ii=Image.open(io.BytesIO(data));
   record('Real '+fmt.upper()+' output dimensions, magic and byte count',ii.size==(400,300) and len(data)==result['size'] and ii.format=={'jpg':'JPEG','png':'PNG','webp':'WEBP'}[fmt])
  # Batch only explicitly selected, retains independent masks and has collision-safe names.
  page.evaluate('(ids)=>{EnToolbox.select(ids[0]);}',ids);page.wait_for_timeout(100)
  page.locator(f'.tb-file[data-id="{ids[0]}"] input').check();page.locator(f'.tb-file[data-id="{ids[1]}"] input').check();page.click('[data-tb-tab="batch"]')
  value_before=state(page)['doc']['cfg'];num=page.evaluate('savedFiles.length');page.click('#tbBatchExport');page.wait_for_function('(n)=>savedFiles.length>n',arg=num,timeout=30000);page.wait_for_function('() => (!EnToolbox.getState().busy)');zinfo=page.evaluate('''async()=>{const z=savedFiles.at(-1);return {name:z.name,url:await blobDataURL(z.blob)};}''');zb=base64.b64decode(zinfo['url'].split(',',1)[1]);
  with zipfile.ZipFile(io.BytesIO(zb)) as z:
   rep=json.loads(z.read('export_report.json'))['entries'];record('Batch exports only checked images',len(rep)==2 and len(z.namelist())==3);record('Batch ZIP CRC and names valid',z.testzip() is None)
   record('Batch preserves each photo privacy masks',rep[0]['privacyRegions']==1 and rep[1]['privacyRegions']==0,rep)
   # Black pixels remain in encoded first image, second untouched.
   imz=Image.open(io.BytesIO(z.read(rep[0]['file']))).convert('RGB');record('Masked batch image has opaque redaction pixels',sum(1 for p in imz.getdata() if max(abs(p[j]-[20,25,23][j]) for j in range(3))<6)>2000)
  record('Batch processing does not switch or corrupt active photo',state(page)['active']==ids[0] and state(page)['doc']['cfg']==value_before)
  page.click('[data-tb-tab="size"]');value(page,'sizeMode','box');value(page,'width',8192);value(page,'height',8192);num=page.evaluate('savedFiles.length');page.click('#tbExport');page.wait_for_function('() => (!EnToolbox.getState().busy)');record('Oversized output rejected without download',page.evaluate('savedFiles.length')==num and '超過' in page.locator('#tbStatus').text_content())
  errs=len(errors);page.click('[data-tb-tab="presets"]');page.fill('#tbPresetName','big');page.click('#tbSavePreset');page.wait_for_timeout(80)
  record('Oversized preset save reports instead of throwing',len(errors)==errs and '超過' in page.locator('#tbStatus').text_content() and not any(x['name']=='big' for x in state(page)['presets']))
  record('Imported preset names drop control characters',page.evaluate('''()=>EnToolbox.core.cleanPresetList({type:'en-toolbox-presets',presets:[{name:'a\\nb\\u0000c',cfg:{quality:80}}]})[0].name''')=='abc')
  page.click('[data-tb-tab="size"]')
  # Return normal settings and take real UI captures (no customer photos).
  page.click('[data-tb-preset="web"]');value(page,'format','webp');page.wait_for_timeout(120);page.screenshot(path=str(w/'editor62.png'))
  page.set_viewport_size({'width':1366,'height':768});page.wait_for_timeout(140);page.screenshot(path=str(w/'layout1366.png'))
  record('1366px interface no horizontal page overflow',page.evaluate('document.querySelector("#tbApp").scrollWidth<=window.innerWidth'))
  page.click('[data-tb-tab="privacy"]');page.wait_for_timeout(100);page.screenshot(path=str(w/'privacy62.png'))
  page.click('[data-tb-tab="mark"]');page.wait_for_timeout(100);page.screenshot(path=str(w/'mark62.png'))
  page.set_viewport_size({'width':390,'height':844});page.wait_for_timeout(120);record('Mobile no horizontal overflow',page.evaluate('document.querySelector("#tbApp").scrollWidth<=window.innerWidth'))
  page.set_viewport_size({'width':1440,'height':1000});page.click('#tbBack');page.wait_for_timeout(100);record('Return to existing comparison workspace works',not page.locator('#tbApp').is_visible() and page.locator('#preview').is_visible())
  record('No runtime JS errors during workflow',not errors,errors)
  # Engines without CanvasRenderingContext2D.filter (Safari < 18): blur mask must still hide the region and tonal sliders must be disabled.
  page.evaluate('EnToolbox.core.setFilterSupport(false)');page.wait_for_timeout(60);errs=len(errors)
  record('Blur mask still masks without canvas filter support',page.evaluate(maskdiff,'blur')>3 and len(errors)==errs,page.evaluate(maskdiff,'blur'))
  record('Tonal sliders disabled without canvas filter support',page.locator('#tb-brightness').is_disabled())
  page.evaluate('EnToolbox.core.setFilterSupport(true)')
  record('No HTTP/S network requests from editor',not any(x.startswith(('https://','http://')) for x in req),req[:4])
 except Exception as e:
  page.screenshot(path=str(w/'test_failure.png'));print(traceback.format_exc(),flush=True)
  results.append({'test':'unexpected failure','passed':False,'detail':str(e)})
 finally:
  (w/'test-results.json').write_text(json.dumps({'environment':'Chromium via Playwright, page.set_content; OS download prompts not exercised.','results':results,'pageErrors':errors},ensure_ascii=False,indent=2));b.close()
print('TOTAL',len(results),'PASS',sum(x['passed'] for x in results),flush=True)
if not all(x['passed'] for x in results):raise SystemExit(1)
