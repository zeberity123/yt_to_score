"""Offline smoke check for frozen builds, including notation fonts and FFmpeg."""
import json
import subprocess
from pathlib import Path
from .contracts import default_format, validate_score
from .render import render
from .providers import write_json


def run(folder):
    from drumscore.video import ffmpeg_path
    import os
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    results = {}
    for instrument in ('bass', 'guitar', 'drums', 'piano'):
        bars = []
        for number in range(1, 9):
            events = []
            for staff in (1, 2) if instrument == 'piano' else (1,):
                notes = [] if number in (2, 3) else [dict(string=1, fret='5', step='C', alter=0,
                    octave=5 if staff == 1 else 3, drum='snare', marks='')]
                events.append(dict(onset=0, duration=4, voice=1, staff=staff, notes=notes, marks=''))
            bars.append(dict(number=number, meter=[4, 4], pickup=False, events=events,
                             confidence=1., timestamp=number*2, issues=[]))
        score = {'meta': dict(title='AI Score '+instrument, instrument=instrument, meter=[4, 4],
                              strings=6 if instrument == 'guitar' else 4, first_bar=1, last_bar=8,
                              key_fifths=0, bpm=120), 'bars': bars}
        assert not validate_score(score), validate_score(score)
        layout = default_format('AI Score '+instrument)
        layout['merge_rests'] = [[2, 3]]
        output = folder/(instrument+'.pdf')
        render(score, layout, output)
        assert output.stat().st_size > 1000
        results[instrument] = output.stat().st_size
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    ffmpeg = subprocess.run([ffmpeg_path(), '-version'], capture_output=True, timeout=20, creationflags=flags)
    assert ffmpeg.returncode == 0
    results['ffmpeg'] = ffmpeg.stdout.decode('utf-8').splitlines()[0]
    write_json(folder/'self-test.json', results)
