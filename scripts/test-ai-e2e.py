"""Explicit live subscription integration check against a short source-video excerpt."""
import json
import subprocess
import sys
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from drumscore.video import ffmpeg_path
from ai_score.providers import Client
from ai_score.pipeline import extract

folder = ROOT/'output/ai-live-e2e'
folder.mkdir(exist_ok=True)
clip = folder/'ado-excerpt.mp4'
if not clip.exists():
    video = Path.home()/'AppData/Roaming/Video Sheet to PDF/output/cache/wpme40lu_XE-av.mp4'
    subprocess.run([ffmpeg_path(), '-v', 'error', '-ss', '186', '-i', str(video), '-t', '12',
                    '-an', '-c:v', 'libx264', '-preset', 'fast', '-crf', '18', str(clip)], check=True,
                   creationflags=subprocess.CREATE_NO_WINDOW)
client = Client('Codex', 'gpt-6-astra', '', folder/'responses', log=lambda msg: print(msg, flush=True), max_requests=20)
result = extract(client, str(clip), 'bass', folder, instructions='Title Ado | Bass TAB only on the first page. No subtitle, footer or metadata. Combine whole-rest bars 116 and 117 into one two-measure rest if both are present. Four bars per line.')
print(json.dumps({'project': str(result[0]), 'pdf': str(result[1]), 'bars': [b['number'] for b in result[2]['bars']], 'review': result[2]['review'], 'usage': client.usage}), flush=True)
