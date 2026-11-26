from pathlib import Path
from playwright.sync_api import sync_playwright
from PIL import Image, ImageDraw
import json, re, base64, hashlib, io, zipfile, traceback
import tempfile,shutil,os,random
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
# Review fixtures: a photo much larger than its on-screen size, opaque lines on a transparent background, and a tall narrow noise image.
big=Image.new('RGB',(3200,2400),(200,205,198));ImageDraw.Draw(big).rectangle((400,300,1200,900),fill=(60,90,140));big.save(f/'big.png')
lines=Image.new('RGBA',(400,300),(0,0,0,0));ld=ImageDraw.Draw(lines)
for x in range(0,400,4):ld.line((x,0,x,299),fill=(0,0,0,255),width=1)
lines.save(f/'lines.png')
Image.frombytes('RGB',(300,3000),random.Random(7).randbytes(300*3000*3)).save(f/'tall.png')
print('Temporary test artifacts:',w)
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
  record('Dragging a mask moves it without selecting it',state(page)['selected'] is None)
  page.click('#tbMaskDuplicate');record('Duplicate without a selection explains instead of doing nothing',len(state(page)['doc']['masks'])==1 and '請先點選' in page.locator('#tbStatus').text_content())
  page.mouse.click(px+35,py+20);page.wait_for_timeout(80)
  record('Clicking a mask selects it and says so in the panel',state(page)['selected']=='mask:0' and '第 1 個框' in page.locator('#tbMaskScope').text_content())
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
  page.click('#toolboxOpen');page.wait_for_timeout(100);n=page.evaluate('S.items.length');page.locator('#tbFiles .tb-remove').first.focus();page.keyboard.press('Enter');page.wait_for_timeout(120)
  record('Toolbox remove button works from the keyboard and keeps a valid active photo',page.evaluate('S.items.length')==n-1 and page.evaluate('!!item(EnToolbox.getState().active)') and page.locator('#tbFiles .tb-file').count()==n-1)
  page.click('#tbBack');page.wait_for_timeout(60)
  record('No runtime JS errors during workflow',not errors,errors)
  # Engines without CanvasRenderingContext2D.filter (Safari < 18): blur mask must still hide the region and tonal sliders must be disabled.
  page.evaluate('EnToolbox.core.setFilterSupport(false)');page.wait_for_timeout(60);errs=len(errors)
  record('Blur mask still masks without canvas filter support',page.evaluate(maskdiff,'blur')>3 and len(errors)==errs,page.evaluate(maskdiff,'blur'))
  record('Tonal sliders disabled without canvas filter support',page.locator('#tb-brightness').is_disabled())
  page.evaluate('EnToolbox.core.setFilterSupport(true)')
  # ---------------------------------------------------------------- review regressions (separate page, touch-enabled context)
  ctx2=b.new_context(viewport={'width':1440,'height':1000},has_touch=True);q=ctx2.new_page();dialogs=[]
  q.on('pageerror',lambda e:errors.append(str(e)));q.on('request',lambda r:req.append(r.url));q.on('dialog',lambda d:(dialogs.append(d.message),d.accept()))
  q.set_content(html);q.wait_for_timeout(100)
  q.evaluate('window.savedFiles=[];download=(blob,name)=>{window.savedFiles.push({blob,name});};void 0;')
  def st():return q.evaluate('EnToolbox.getState()')
  def note():return q.locator('#tbStatus').text_content()
  def at(fx,fy):
   bb=q.locator('#tbOverlay').bounding_box();return bb['x']+fx*bb['width'],bb['y']+fy*bb['height']
  def drag(a,c,steps=6):
   x0,y0=at(*a);x1,y1=at(*c);q.mouse.move(x0,y0);q.mouse.down();q.mouse.move(x1,y1,steps=steps);q.mouse.up();q.wait_for_timeout(90)
  def tap(a):
   x,y=at(*a);q.mouse.click(x,y);q.wait_for_timeout(80)
  def wobble(a):
   x,y=at(*a);q.mouse.move(x,y);q.mouse.down();q.mouse.move(x+2,y+1);q.mouse.up();q.wait_for_timeout(80)
  def idle():
   q.wait_for_function('() => (!EnToolbox.getState().busy&&!S.busy&&!S.importing)');q.wait_for_timeout(60)
  def near(a,c,tol=.012):return all(abs(a[k]-c[k])<tol for k in 'xywh')
  def pick(i):
   q.evaluate('(id)=>EnToolbox.select(id)',i);q.wait_for_timeout(120)
  def saved():return q.evaluate('savedFiles.length')
  q.locator('#fileInput').set_input_files(str(f/'bag-before.png'));q.wait_for_function('() => (S.items.length===1&&!S.importing)')
  q.locator('#fileInput').set_input_files(str(f/'flat.png'));q.wait_for_function('() => (S.items.length===2&&!S.importing)');q.wait_for_timeout(120)
  A,F=q.evaluate('S.items.map(i=>i.id)')
  q.click('#toolboxOpen');q.wait_for_timeout(150)
  # Selection: drawing or dragging does not select; a click does, and the panel says what it is editing.
  q.click('[data-tb-tab="privacy"]');q.wait_for_timeout(80);drag((.10,.10),(.30,.30))
  record('A drawn mask is not left selected',len(st()['doc']['masks'])==1 and st()['selected'] is None and '之後新畫的框' in q.locator('#tbMaskScope').text_content())
  q.select_option('#tbMaskType','blur');q.wait_for_timeout(60);drag((.50,.50),(.70,.70))
  record('Choosing the type for the next mask does not convert the one just drawn',[m['type'] for m in st()['doc']['masks']]==['solid','blur'])
  tap((.20,.20))
  record('Clicking a mask loads its own type into the panel',st()['selected']=='mask:0' and q.locator('#tbMaskType').input_value()=='solid')
  q.select_option('#tbMaskType','mosaic');q.wait_for_timeout(60)
  record('With a mask selected the type control edits that mask and says so',st()['doc']['masks'][0]['type']=='mosaic' and '第 1 個遮蔽框' in note())
  q.locator('#tbMaskList .tb-layer button').first.click();q.wait_for_timeout(60)
  record('The list button takes the selection off again',st()['selected'] is None)
  q.click('#tbMaskDelete');record('Delete without a selection explains instead of doing nothing',len(st()['doc']['masks'])==2 and '請先點選' in note())
  cdp=ctx2.new_cdp_session(q)
  def touch(kind,pts):
   cdp.send('Input.dispatchTouchEvent',{'type':kind,'touchPoints':[{'x':x,'y':y,'id':i} for i,(x,y) in pts]});q.wait_for_timeout(40)
  t0=at(.75,.15);t1=at(.85,.30);touch('touchStart',[(0,t0)]);touch('touchStart',[(0,t0),(1,t1)]);touch('touchMove',[(0,(t0[0]+30,t0[1]+30)),(1,(t1[0]+30,t1[1]+30))]);touch('touchEnd',[])
  record('A second finger does not replace the drag or leave a stray mask',len(st()['doc']['masks'])==3 and all(m['w']*800>=3 and m['h']*600>=3 for m in st()['doc']['masks']),st()['doc']['masks'])
  # The toolbox notices when the photo it was editing left the list while it was closed (compare undo).
  pick(F);q.click('#tbMaskAdd');tap((.20,.20));record('A mask added with the button can be selected by a click',st()['selected']=='mask:0')
  q.click('#tbBack');q.wait_for_timeout(80);q.click('#undoBtn');q.wait_for_timeout(100);q.click('#toolboxOpen');q.wait_for_timeout(150)
  masksA=st()['doc']['masks'];q.keyboard.press('Delete');q.wait_for_timeout(60)
  record('Reopening after the edited photo was undone away resets selection and status',st()['active']==A and st()['selected'] is None and st()['doc']['masks']==masksA and len(masksA)==3 and 'flat.png' not in note(),note())
  q.click('#tbBack');q.wait_for_timeout(60);q.click('#redoBtn');q.wait_for_timeout(100);q.click('#toolboxOpen');q.wait_for_timeout(150);pick(F)
  record('Redo brings the photo back with its toolbox edits',q.evaluate('S.items.length')==2 and len(st()['doc']['masks'])==1)
  # Over-limit output size: source views keep working in their own units, the result view is blanked and takes no pointer edits.
  pick(A);q.click('[data-tb-tab="size"]');value(q,'sizeMode','box');value(q,'width',8192);value(q,'height',8192);q.wait_for_timeout(150)
  record('An over-limit size blanks the result preview instead of leaving an older picture',st()['blocked'] is True and q.evaluate("document.querySelector('#tbPreview').width")==900 and '超過' in note(),note())
  q.click('[data-tb-tab="privacy"]');q.wait_for_timeout(150)
  record('The privacy view still shows the source photo while the size is over the limit',st()['blocked'] is False and q.evaluate("(()=>{const c=document.querySelector('#tbPreview');return c.width===800&&c.height===600;})()"))
  drag((.40,.80),(.50,.90));m=st()['doc']['masks']
  record('A mask drawn while the size is over the limit lands where it was drawn and moves no other mask',m[:-1]==masksA and near(m[-1],{'x':.40,'y':.80,'w':.10,'h':.10}),m[-1])
  q.click('[data-tb-tab="draw"]');q.wait_for_timeout(150);doc0=st()['doc'];drag((.2,.2),(.6,.6))
  record('Pointer edits are ignored while nothing valid is shown',st()['blocked'] is True and st()['doc']==doc0)
  pick(F);pick(A)
  record('Switching to an over-limit photo does not keep showing the previous photo',st()['blocked'] is True and q.evaluate("document.querySelector('#tbPreview').width")==900)
  q.click('[data-tb-tab="size"]');value(q,'height',900);q.wait_for_timeout(150)
  record('Correcting the size restores the preview',st()['blocked'] is False and '8192 × 900' in q.locator('#tbOutputMeta').text_content())
  value(q,'height',8192);q.wait_for_timeout(120);shown='超過' in note();value(q,'height',900);q.wait_for_timeout(150)
  record('The size error leaves the footer once the size is valid again',shown and '超過' not in note() and '限制內' in note(),note())
  q.click('[data-tb-preset="long"]');q.wait_for_timeout(100)
  # Marker controls: creation leaves nothing selected, each control writes only its own property, one history step per edit.
  q.click('[data-tb-tab="draw"]');q.select_option('#tbDrawType','text');q.fill('#tbDrawText','污漬');q.click('#tbDrawAdd');q.fill('#tbDrawText','修復');q.locator('#tbDrawText').press('Tab');q.click('#tbDrawAdd');q.wait_for_timeout(80)
  record('Typing the text for the next label does not rewrite the previous one',[x['text'] for x in st()['doc']['shapes']]==['污漬','修復'])
  drag((.40,.32),(.40,.62))
  record('Dragging a marker moves it without selecting it',st()['selected'] is None and st()['doc']['shapes'][1]['y']>.5)
  tap((.40,.32))
  record('Clicking a marker loads its text into the panel',st()['selected']=='shape:0' and q.locator('#tbDrawText').input_value()=='污漬' and '第 1 個標記' in q.locator('#tbDrawScope').text_content())
  q.locator('#tbDrawColor').evaluate('(e)=>{e.value="#00aa00";e.dispatchEvent(new Event("input",{bubbles:true}));e.dispatchEvent(new Event("change",{bubbles:true}));}');q.wait_for_timeout(60)
  sh=st()['doc']['shapes'];record('Changing only the colour leaves the text and the other marker alone',sh[0]['color']=='#00aa00' and sh[0]['text']=='污漬' and sh[1]['text']=='修復' and sh[1]['color']!='#00aa00',sh)
  q.click('#tbUndo');record('A marker colour change is one undo step',st()['doc']['shapes'][0]['color']!='#00aa00' and len(st()['doc']['shapes'])==2)
  tap((.40,.32));on=st()['selected'];tap((.9,.9));record('Clicking empty canvas clears the selection',on=='shape:0' and st()['selected'] is None)
  # History: a burst of key presses on one slider is one step; shortcuts work while a checkbox or slider has focus.
  q.click('[data-tb-tab="rotate"]');q.locator('#tb-rotate').focus()
  for _ in range(10):q.keyboard.press('ArrowRight')
  q.wait_for_timeout(60);r10=st()['doc']['cfg']['rotate'];q.click('#tbUndo')
  record('Ten arrow-key presses on a slider are one undo step',r10==10 and st()['doc']['cfg']['rotate']==0 and len(st()['doc']['shapes'])==2,r10)
  q.locator('#tb-flipH').click();q.wait_for_timeout(40);on=st()['doc']['cfg']['flipH'];q.keyboard.press('Control+z');q.wait_for_timeout(60)
  record('Ctrl+Z works while a checkbox has focus',on is True and st()['doc']['cfg']['flipH'] is False)
  q.locator('#tb-rotate').evaluate('(e)=>{e.value=40;e.dispatchEvent(new Event("input",{bubbles:true}));e.dispatchEvent(new Event("change",{bubbles:true}));}');q.locator('#tb-rotate').focus();q.keyboard.press('Control+z');q.wait_for_timeout(60)
  record('Undo also moves a slider that has focus back',st()['doc']['cfg']['rotate']==0 and q.locator('#tb-rotate').input_value()=='0')
  q.locator('.tb-file input').first.focus();q.keyboard.press('Escape');q.wait_for_timeout(80)
  record('Escape closes the toolbox while a tick box has focus',not q.locator('#tbApp').is_visible())
  q.click('#toolboxOpen');q.wait_for_timeout(120);q.locator('.tb-file').nth(1).focus();q.keyboard.press('Enter');q.wait_for_timeout(80)
  record('Choosing a photo from the keyboard keeps focus on its row',st()['active']==F and q.evaluate("document.activeElement.classList.contains('tb-file')&&document.activeElement.dataset.id")==F)
  # Large photo: a click with a small wobble is not a box, and does not cost an existing crop.
  q.locator('#tbInput').set_input_files(str(f/'big.png'));q.wait_for_function('() => (S.items.length===3&&!S.importing)');B=q.evaluate('S.items[2].id');pick(B);q.wait_for_timeout(120)
  q.click('[data-tb-tab="privacy"]');q.wait_for_timeout(120);wobble((.5,.5))
  record('A click with a two-pixel wobble on a large photo leaves no mask',st()['doc']['masks']==[])
  q.click('[data-tb-tab="crop"]');q.wait_for_timeout(100);drag((.3,.3),(.5,.5))
  record('Dragging inside an uncropped photo does not create a full-frame crop',st()['doc']['crop'] is None and '已裁切' not in q.locator(f'.tb-file[data-id="{B}"] .tb-tag').text_content())
  q.select_option('#tbCropAspect','1');q.wait_for_timeout(100);sq=st()['doc']['crop'];wobble((.03,.5))
  record('A stray click outside the crop frame keeps the crop',sq is not None and st()['doc']['crop']==sq)
  q.select_option('#tbCropAspect','free');q.wait_for_timeout(80)
  record('Switching to the free ratio keeps the crop',st()['doc']['crop']==sq)
  drag((.05,.10),(.45,.60));hand=st()['doc']['crop'];q.select_option('#tbCropAspect','1.7777777778');q.wait_for_timeout(100)
  record('Changing the ratio reshapes the hand-made crop around its centre',near(hand,{'x':.05,'y':.10,'w':.40,'h':.50}) and near(st()['doc']['crop'],{'x':.05,'y':.20,'w':.40,'h':.30}),st()['doc']['crop'])
  q.click('#tbCropCenter');q.wait_for_timeout(80);record('The centre button still gives the centred maximum crop',near(st()['doc']['crop'],{'x':0,'y':.125,'w':1,'h':.75}))
  q.select_option('#tbCropAspect','free');q.click('#tbCropCenter');q.wait_for_timeout(80)
  record('A full-frame result is no crop at all',st()['doc']['crop'] is None and not q.evaluate('(id)=>EnToolbox.hasEdits(id)',B))
  record('A project crop on the last pixel column stays inside the photo',q.evaluate('''()=>{const s=EnToolbox.getState(),src=item(s.active),d=JSON.parse(JSON.stringify(s.doc));d.crop={x:.999999,y:.999999,w:.000001,h:.000001};const g=EnToolbox.core.outputGeometry(src,d);return g.r.x===src.w-1&&g.r.y===src.h-1&&g.r.w===1&&g.r.h===1;}'''))
  # Masks on transparency and on tall images.
  q.locator('#tbInput').set_input_files([str(f/'lines.png'),str(f/'tall.png')]);q.wait_for_function('() => (S.items.length===5&&!S.importing)');L,TALL=q.evaluate('S.items.slice(3).map(i=>i.id)')
  mos=q.evaluate('''(id)=>{const src=item(id),d={cfg:EnToolbox.core.validConfig({sizeMode:'original',format:'png',transparent:true}),crop:null,masks:[{x:.25,y:.25,w:.5,h:.5,type:'mosaic',strength:20}],shapes:[]};
   const cv=EnToolbox.core.renderDoc(src,d,null).cv,px=cv.getContext('2d').getImageData(100,75,200,150).data;let clear=0,black=0;for(let i=0;i<px.length;i+=4){if(px[i+3]!==255)clear++;if(px[i]===0&&px[i+1]===0&&px[i+2]===0)black++;}
   return {clear,black,outside:cv.getContext('2d').getImageData(21,20,1,1).data[3]};}''',L)
  record('Mosaic over a transparent source is opaque and leaves no original pixel',mos['clear']==0 and mos['black']==0 and mos['outside']==0,mos)
  run=q.evaluate('''(id)=>{const src=item(id),d={cfg:EnToolbox.core.validConfig({sizeMode:'original',format:'png'}),crop:null,masks:[{x:0,y:.4,w:1,h:.2,type:'mosaic',strength:4}],shapes:[]};
   const cv=EnToolbox.core.renderDoc(src,d,null).cv,row=cv.getContext('2d').getImageData(0,1500,300,1).data,len=[];let n=1;for(let i=4;i<row.length;i+=4){if(row[i]===row[i-4]&&row[i+1]===row[i-3]&&row[i+2]===row[i-2])n++;else{len.push(n);n=1;}}len.push(n);len.sort((a,b)=>a-b);return len[len.length>>1];}''',TALL)
  record('On a tall image the weakest mosaic is as coarse in the export as the editor shows it',run>=4,run)
  # Presets: no rotation, clean names, free default names, legacy logo flag.
  pick(A);q.click('[data-tb-tab="rotate"]');q.click('#tbRotateRight');q.click('[data-tb-tab="presets"]');q.fill('#tbPresetName','A\tB');q.click('#tbSavePreset');q.wait_for_timeout(60)
  pr=st()['presets'];record('A preset stores neither rotation nor control characters in its name',pr[0]['name']=='AB' and pr[0]['cfg']['rotate']==0 and st()['doc']['cfg']['rotate']==90,pr[0]['name'])
  pick(F);q.click('[data-tb-tab="rotate"]');q.click('#tbRotateLeft');q.click('[data-tb-tab="presets"]');q.locator('#tbPresetList .tb-preset-row button').first.click();q.wait_for_timeout(60)
  record('Applying a preset keeps the rotation of the photo',st()['doc']['cfg']['rotate']==-90 and '旋轉' in note(),note())
  q.fill('#tbPresetName','');q.click('#tbSavePreset');q.click('#tbSavePreset');q.wait_for_timeout(60)
  q.locator('#tbPresetList .tb-preset-row').first.locator('button').nth(1).click();q.wait_for_timeout(60);dialogs.clear();q.click('#tbSavePreset');q.wait_for_timeout(60)
  record('The default preset name is the first free one and never overwrites',[x['name'] for x in st()['presets']]==['工具箱版型 1','工具箱版型 2','工具箱版型 3'] and not any('覆寫' in x for x in dialogs),[x['name'] for x in st()['presets']])
  legacy=q.evaluate("EnToolbox.core.cleanPresetList({type:'en-toolbox-presets',version:'6.2',presets:[{name:'old',cfg:{logoOn:true,quality:80,rotate:90}}]})[0].cfg")
  current=q.evaluate("EnToolbox.core.cleanPresetList({type:'en-toolbox-presets',version:'6.2.1',presets:[{name:'new',cfg:{logoOn:true,quality:80}}]})[0].cfg")
  record('Presets from before 6.2.1 no longer switch the logo on',legacy['logoOn'] is False and legacy['rotate']==0 and current['logoOn'] is True)
  record('The stored preset list skips a bad entry instead of dropping every preset',q.evaluate("EnToolbox.core.cleanPresetList({type:'en-toolbox-presets',version:'6.2.1',presets:[{name:'ok',cfg:{quality:80}},{name:'ok',cfg:{quality:70}},{name:'bad',cfg:{quality:'x'}}]},true).map(x=>x.name).join()")=='ok')
  # Batch: library order, folder names for same-named photos, honest report.
  raw=base64.b64encode((f/'flat.png').read_bytes()).decode()
  q.evaluate('''async s=>{const b=Uint8Array.from(atob(s),c=>c.charCodeAt(0));await addFiles([{file:new File([b],'before.png',{type:'image/png',lastModified:1}),path:'cases/caseA/before.png'},{file:new File([b],'Before.PNG',{type:'image/png',lastModified:2}),path:'cases/caseB/Before.PNG'}]);}''',raw);idle()
  CA,CB=q.evaluate('S.items.slice(5).map(i=>i.id)')
  q.click('#tbSelectNone');q.locator(f'.tb-file[data-id="{CB}"] input').check();q.locator(f'.tb-file[data-id="{CA}"] input').check()
  pick(CA);q.click('[data-tb-tab="size"]');value(q,'quality',77);value(q,'format','png')
  q.click('[data-tb-tab="batch"]');q.fill('#tbBatchPrefix','...');n=saved();q.click('#tbBatchExport');q.wait_for_function('(n)=>savedFiles.length>n',arg=n,timeout=30000);idle()
  zb=base64.b64decode(q.evaluate('async()=>await blobDataURL(savedFiles.at(-1).blob)').split(',',1)[1])
  with zipfile.ZipFile(io.BytesIO(zb)) as zz:
   names=zz.namelist();rows=json.loads(zz.read('export_report.json'))['entries']
  record('Same-named photos from different folders get the folder in the name, in library order',names[:2]==['caseA_before.png','caseB_Before.webp'],names)
  record('The report tells same-named sources apart and reports no quality for PNG',rows[0]['sourcePath']=='cases/caseA/before.png' and rows[1]['sourcePath']=='cases/caseB/Before.PNG' and rows[0]['quality'] is None and rows[1]['quality']==88,rows)
  record('A prefix that cleans to nothing adds nothing',not any(x.startswith('compare') for x in names))
  # Warnings are all reported, with their own text.
  pick(A);q.click('[data-tb-tab="adjust"]');value(q,'brightness',120);q.click('[data-tb-tab="size"]');value(q,'format','jpg');value(q,'targetKB',1)
  q.evaluate('EnToolbox.core.setFilterSupport(false)');q.wait_for_timeout(60);q.click('#tbMeasure');idle()
  record('Two warnings on one export are both reported',('調色' in note()) and ('容量目標' in note()),note())
  q.click('#tbSelectNone');q.locator(f'.tb-file[data-id="{A}"] input').check();q.click('[data-tb-tab="batch"]');q.fill('#tbBatchPrefix','');n=saved();q.click('#tbBatchExport');q.wait_for_function('(n)=>savedFiles.length>n',arg=n,timeout=30000);idle()
  rpt=q.locator('#tbBatchReport').text_content();record('The batch list shows the real warning text',('調色' in rpt) and ('超過目標容量' not in rpt),rpt)
  q.evaluate('EnToolbox.core.setFilterSupport(true)');q.click('[data-tb-tab="size"]');value(q,'targetKB',0);q.click('[data-tb-tab="adjust"]');q.click('#tbNeutral')
  # The copy handed to the comparison is what the preview shows.
  pick(F);q.click('[data-tb-tab="size"]');value(q,'format','png');value(q,'transparent',True);value(q,'format','jpg');q.click('[data-tb-preset="square"]');n=q.evaluate('S.items.length');q.click('#tbToCompare');q.wait_for_function('(n)=>S.items.length>n&&!S.importing',arg=n);idle()
  record('The copy added to the comparison keeps the background the preview shows',q.evaluate('''()=>{const i=S.items.at(-1),c=document.createElement('canvas');c.width=i.w;c.height=i.h;const x=c.getContext('2d');x.drawImage(i.img,0,0);return i.w===1080?x.getImageData(4,4,1,1).data[3]:-1;}''')==255)
  # Browsers without canvas WebP encoding.
  q.evaluate('EnToolbox.core.setWebpSupport(false)');q.wait_for_timeout(60);pick(TALL);q.click('[data-tb-tab="size"]');q.wait_for_timeout(60)
  record('Without WebP encoding new photos default to JPG and the option is disabled',st()['doc']['cfg']['format']=='jpg' and q.locator('#tb-format option[value="webp"]').is_disabled() and q.locator('#batchFormat').input_value()=='png')
  pick(CB);n=saved();q.click('#tbExport');q.wait_for_function('(n)=>savedFiles.length>n',arg=n,timeout=20000);idle()
  record('A photo still set to WEBP is exported as JPG with a note',q.evaluate('savedFiles.at(-1).name').endswith('.jpg') and '改用 JPG' in note(),note())
  q.evaluate('EnToolbox.core.setWebpSupport(true)');q.wait_for_timeout(60)
  # Stop button: in the footer for every job; a stopped batch does not look finished.
  q.evaluate("window.__cb=canvasBlob;canvasBlob=(...a)=>new Promise(r=>setTimeout(r,300)).then(()=>window.__cb(...a));void 0;")
  pick(A);q.click('[data-tb-tab="adjust"]');value(q,'sharpness',5);q.click('#tbMeasure');q.wait_for_timeout(80)
  seen=q.locator('#tbCancel').is_visible() and q.locator('#tbCancel').text_content()=='停止';q.keyboard.press('Escape');q.wait_for_timeout(40);hint=note();q.click('#tbCancel');idle()
  record('The stop button is in the footer, reachable from any tab during a single export',seen and '停止' in hint and '已取消' in note() and q.evaluate('S.cancel') is False and not q.locator('#tbCancel').is_visible(),(hint,note()))
  q.click('#tbSelectNone');q.locator(f'.tb-file[data-id="{A}"] input').check();q.locator(f'.tb-file[data-id="{F}"] input').check();q.click('[data-tb-tab="batch"]');n=saved();q.click('#tbBatchExport');q.wait_for_timeout(450);q.click('#tbCancel');idle()
  rpt=q.locator('#tbBatchReport').text_content()
  record('A stopped batch downloads nothing and its list does not look finished',saved()==n and '✓' not in rpt and '已停止' in note() and (rpt=='' or rpt.startswith('已停止')),rpt)
  q.evaluate('canvasBlob=window.__cb;void 0;')
  q.click('[data-tb-tab="adjust"]');value(q,'sharpness',6);n=saved();q.evaluate("document.querySelector('#tbExport').click();document.querySelector('#tbCancel').click();void 0;");idle()
  record('Stop pressed right after starting an export cancels it',saved()==n and '已取消' in note(),note())
  # Small things: one-decimal positions, drop banner, messages while importing, logo note.
  pick(B);q.click('[data-tb-tab="mark"]');value(q,'textOn',True);value(q,'text','TEST');value(q,'textX',50);value(q,'textY',50);q.wait_for_timeout(100);drag((.5,.5),(.37,.41));c=st()['doc']['cfg']
  record('Dragging the watermark leaves one-decimal positions',c['textX']<50 and all(abs(v*10-round(v*10))<1e-6 for v in (c['textX'],c['textY'])),(c['textX'],c['textY']))
  q.evaluate('''()=>{const dt=new DataTransfer();dt.items.add(new File(['x'],'a.png',{type:'image/png'}));document.querySelector('#tbFiles').dispatchEvent(new DragEvent('dragenter',{dataTransfer:dt,bubbles:true,cancelable:true}));}''')
  shown=q.evaluate("document.querySelector('#tbApp').classList.contains('tb-dropping')");q.wait_for_timeout(1150)
  record('The drop banner goes away by itself when the drag ends without a drop',shown and not q.evaluate("document.querySelector('#tbApp').classList.contains('tb-dropping')"))
  q.evaluate('S.importing=true;void 0;');q.click('#tbExport');m1=note();q.click('#tbSaveProject');m2=note();q.evaluate('S.importing=false;void 0;')
  record('Buttons that cannot act during an import say so',('正在讀取照片' in m1) and ('正在讀取照片' in m2),(m1,m2))
  pick(L);q.locator('#tbLogoInput').set_input_files(str(f/'transparent.png'));q.wait_for_function('() => (document.querySelector("#tbLogoName").textContent.includes("transparent.png"))');msg=note()
  record('Loading a logo says that it is shown on the current photo only',st()['doc']['cfg']['logoOn'] is True and '目前這張' in msg and q.evaluate('(id)=>{EnToolbox.select(id);return EnToolbox.getState().doc.cfg.logoOn;}',TALL) is False,msg)
  q.click('[data-tb-tab="privacy"]');q.wait_for_timeout(120)
  q.evaluate('''()=>{const ov=document.querySelector('#tbOverlay'),r=ov.getBoundingClientRect(),real=ov.setPointerCapture;ov.setPointerCapture=()=>{};ov.dispatchEvent(new PointerEvent('pointerdown',{pointerId:77,button:0,clientX:r.x+r.width*.9,clientY:r.y+r.height*.9,bubbles:true}));ov.setPointerCapture=real;}''')
  stuck=len(st()['doc']['masks']);drag((.2,.2),(.6,.4))
  record('A drag that never got its end event does not block the next one',stuck==1 and len(st()['doc']['masks'])==1 and near(st()['doc']['masks'][0],{'x':.2,'y':.2,'w':.4,'h':.2}),st()['doc']['masks'])
  record('No runtime JS errors during the review checks',not errors,errors)
  record('No HTTP/S network requests from editor',not any(x.startswith(('https://','http://')) for x in req),req[:4])
 except Exception as e:
  page.screenshot(path=str(w/'test_failure.png'));print(traceback.format_exc(),flush=True)
  results.append({'test':'unexpected failure','passed':False,'detail':str(e)})
 finally:
  (w/'test-results.json').write_text(json.dumps({'environment':'Chromium via Playwright, page.set_content; OS download prompts not exercised.','results':results,'pageErrors':errors},ensure_ascii=False,indent=2));b.close()
print('TOTAL',len(results),'PASS',sum(x['passed'] for x in results),flush=True)
if not all(x['passed'] for x in results):raise SystemExit(1)
