"""Explicit live Astra check; consumes subscription allowance on a 12-second clip."""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8')
from ai_score.pipeline import extract
from ai_score.providers import Client, write_json

folder = ROOT/'output/ai-optimized-live'
client = Client('Codex', 'gpt-6-astra', '', folder/'responses', max_requests=12,
                log=lambda message: print(message, flush=True))
start = time.monotonic()
_, pdf, score = extract(client, str(ROOT/'output/ai-live-e2e/ado-excerpt.mp4'), 'bass',
                        folder, bars_per_line=4, instructions='')
baseline = json.loads((ROOT/'independent_score/ai_example/Ado.aiscore.json').read_text(encoding='utf-8'))
reference = {b['number']: b for b in baseline['bars']}
def music(bar):
    return [(e['onset'], e['duration'], [(n['string'], n['fret']) for n in e['notes']]) for e in bar['events']]
summary = {'elapsed_seconds': round(time.monotonic()-start, 1), 'usage': client.usage,
           'bars': [b['number'] for b in score['bars']], 'preparation': score['preparation'],
           'matches': {b['number']: music(b) == music(reference[b['number']]) for b in score['bars'] if b['number'] in reference},
           'review': score['review'], 'pdf': str(pdf)}
write_json(folder/'summary.json', summary)
print(json.dumps(summary), flush=True)
