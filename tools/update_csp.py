"""Maintainer utility: rehash inline scripts, preserve the offline single-file application."""
from pathlib import Path
import base64
import hashlib
import re
root=Path(__file__).resolve().parents[1]
p=root/'index.html'
h=p.read_text(encoding='utf-8')
scripts=re.findall(r'<script>([\s\S]*?)</script>',h)
if not scripts: raise SystemExit('No inline scripts found; nothing was changed.')
hashes=["'sha256-"+base64.b64encode(hashlib.sha256(s.encode('utf-8')).digest()).decode('ascii')+"'" for s in scripts]
h,n=re.subn(r'script-src [^;]+;', 'script-src '+' '.join(hashes)+';', h, count=1)
if n!=1: raise SystemExit('CSP not found; nothing was changed.')
p.write_text(h,encoding='utf-8',newline='\n')
(root/'en_compare_manager_v6_2_toolbox.html').write_text(h,encoding='utf-8',newline='\n')
print(f'Updated {len(hashes)} script hashes and synchronized both v6.2 entry files.')
print('Re-run tests and update SHA256SUMS.txt before publishing a new release.')
