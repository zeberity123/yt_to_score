"""Check actual portable executables without account access or AI calls."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
output = ROOT/'output/ai-packaged-check'
output.mkdir(parents=True, exist_ok=True)
editions = sys.argv[1:] or ['Personal', 'API']
for edition in editions:
    exe = ROOT/f'dist/ai/AI-Score-{edition}-0.1.0.exe'
    folder = output/edition.lower()
    folder.mkdir(exist_ok=True)
    subprocess.run([str(exe), '--self-test', str(folder)], check=True, timeout=90,
                   creationflags=subprocess.CREATE_NO_WINDOW)
    details = json.loads((folder/'self-test.json').read_text(encoding='utf-8'))
    for instrument in ('bass', 'guitar', 'drums', 'piano'):
        document = pymupdf.open(str(folder/(instrument+'.pdf')))
        assert document.page_count > 0
        assert all(not page.get_images() for page in document)
        document[0].get_pixmap().save(str(folder/(instrument+'.png')))
    subprocess.run([str(exe), '--smoke-test'], check=True, timeout=60,
                   creationflags=subprocess.CREATE_NO_WINDOW)
    details.update(sha256=hashlib.sha256(exe.read_bytes()).hexdigest(), size=exe.stat().st_size,
                   gui_smoke='passed', vector_pdf_smoke='all four instruments passed')
    (folder/'result.json').write_text(json.dumps(details, indent=2), encoding='utf-8')
    print(edition, json.dumps(details), flush=True)
