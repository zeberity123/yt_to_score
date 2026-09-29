"""Explicit live CLI connection checks; these consume the signed-in plans' allowances."""
import json
import sys
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ai_score.providers import Client, write_json
from ai_score.contracts import TRANSCRIPTION
from ai_score.prompts import TRANSCRIBE_PROMPT

provider = sys.argv[1]
model = 'gpt-6-luna' if provider == 'Codex' else 'haiku'
client = Client(provider, model, '', ROOT/'output/ai-connections'/provider, log=lambda msg: print(msg, flush=True))
if provider == 'Codex':
    # Identical six source frames to the earlier Astra extraction, no reference notes.
    folders = list((ROOT/'output/ai-live-e2e/frames').glob('*'))
    images = []
    for second in (0, 2, 4, 6, 8, 10):
        candidates = list((ROOT/'output/ai-live-e2e/frames').rglob(f'frame_{second:09.3f}_*.jpg'))
        images.append(candidates[0])
    prompt = TRANSCRIBE_PROMPT+'\nFour-string bass TAB; 4/4. Frames at 0,2,4,6,8,10 seconds of an excerpt. Read complete printed bars only.'
else:
    images = [ROOT/'independent_score/detail_188.jpg']
    prompt = TRANSCRIBE_PROMPT+'\nFour-string bass TAB, 4/4. Read only bars 116 and 117 in this image at 188 seconds.'
result = client.request(prompt, TRANSCRIPTION, images)
write_json(ROOT/'output/ai-connections'/provider/'result.json', result)
summary = {'provider': provider, 'model': model, 'bars': [b['number'] for b in result['bars']], 'usage': client.usage}
if provider == 'Codex':
    baseline = json.loads((ROOT/'independent_score/ai_example/Ado.aiscore.json').read_text(encoding='utf-8'))
    by_number = {b['number']: b for b in baseline['bars']}
    def music(b):
        return [(e['onset'], e['duration'], [(n['string'], n['fret']) for n in e['notes']]) for e in b['events']]
    summary['matches'] = {b['number']: music(b) == music(by_number[b['number']]) for b in result['bars'] if b['number'] in by_number}
write_json(ROOT/'output/ai-connections'/provider/'summary.json', summary)
print(json.dumps(summary), flush=True)
