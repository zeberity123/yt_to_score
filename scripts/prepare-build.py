"""Prepare the app icon and dependency notices for the Windows release."""
from importlib.metadata import distributions
from pathlib import Path
import shutil
import sys
import subprocess
from urllib.request import urlretrieve

from PIL import Image, ImageDraw

root = Path(__file__).resolve().parent.parent
assets = root / 'build/assets'
licenses = root / 'build/licenses'
assets.mkdir(parents=True, exist_ok=True)
licenses.mkdir(parents=True, exist_ok=True)

# Draw the same staff and note motif as web/icon.svg at icon resolution.
icon = Image.new('RGBA', (256, 256))
draw = ImageDraw.Draw(icon)
draw.rounded_rectangle((0, 0, 255, 255), radius=72, fill='#234a46')
for y in (92, 120, 148, 176):
    draw.line((48, y, 208, y), fill='#69a49a', width=8)
draw.ellipse((80, 154, 142, 198), fill='#d8f7ef')
draw.rectangle((132, 60, 144, 176), fill='#d8f7ef')
icon.save(assets/'app.ico', sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])

excluded = {'pip','setuptools','pytest','pymupdf','pyinstaller','pyinstaller-hooks-contrib',
            'altgraph','pefile','pywin32-ctypes','iniconfig','pluggy','pygments'}
manifest = []
for dist in distributions():
    name = dist.metadata['Name']
    if name.lower() in excluded:
        continue
    manifest.append(f'{name}=={dist.version}')
    for item in dist.files or []:
        if any(word in item.name.lower() for word in ('license', 'copying', 'notice')):
            source = Path(dist.locate_file(item))
            if source.is_file():
                target = licenses/name/str(item)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
(licenses/'python-packages.txt').write_text('\n'.join(sorted(manifest))+'\n', encoding='utf-8')
python_license = Path(sys.base_prefix)/'LICENSE.txt'
if python_license.exists():
    shutil.copy2(python_license, licenses/'Python-LICENSE.txt')

import imageio_ffmpeg
ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
version = subprocess.check_output([ffmpeg, '-version'], creationflags=subprocess.CREATE_NO_WINDOW)
(licenses/'FFmpeg-build.txt').write_bytes(version)
urlretrieve('https://raw.githubusercontent.com/FFmpeg/FFmpeg/n7.1/COPYING.GPLv3', licenses/'FFmpeg-GPLv3.txt')
