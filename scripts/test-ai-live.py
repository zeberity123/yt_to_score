"""Small real subscription request; run explicitly, never in ordinary unit tests."""
import json
import sys
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ai_score.providers import Client, write_json
from ai_score.contracts import TRANSCRIPTION
from ai_score.prompts import TRANSCRIBE_PROMPT

client = Client('Codex', 'gpt-6-astra', '', ROOT/'output/ai-live-smoke', log=lambda text: print(text, flush=True))
prompt = TRANSCRIBE_PROMPT + '\nThe attached image is a cropped bass TAB source frame. Read only measures 116 and 117 if visible, with four strings. The frame time is 188 seconds. Return any complete visible bars if 116/117 are not in this frame.'
image = ROOT/'independent_score/detail_188.jpg'
if not image.exists():
    import cv2
    video = Path.home()/'AppData/Roaming/Video Sheet to PDF/output/cache/wpme40lu_XE-av.mp4'
    cap = cv2.VideoCapture(str(video))
    cap.set(cv2.CAP_PROP_POS_MSEC, 188000)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise RuntimeError('Test video not available')
    cv2.imwrite(str(image), frame[740:1050], [cv2.IMWRITE_JPEG_QUALITY, 95])
result = client.request(prompt, TRANSCRIPTION, [image])
write_json(ROOT/'output/ai-live-smoke/result.json', result)
print(json.dumps({'bars': [b['number'] for b in result['bars']], 'usage': client.usage}))
