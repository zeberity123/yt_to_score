"""Visual chord/lyric rows, with aligned text and explicit occurrence ordering."""
import json
import time
from pathlib import Path
import cv2
from .contracts import LEAD_TRANSCRIPTION, FORMAT, default_format
from .prompts import LEAD_PROMPT, FORMAT_PROMPT
from .providers import check_cancel, write_json


def extract_lead(client, source, folder, instructions='', interval=2., frames_per_request=6, optimize=True, selected_crop=None, title=None):
    from drumscore.video import download, metadata
    from .pipeline import frame_at, report_stage
    from .render import render
    started = time.monotonic()
    folder = Path(folder)
    frames = folder/'frames'
    frames.mkdir(parents=True, exist_ok=True)
    path, video_title = download(source, folder.parent/'video-cache', lambda msg, *_: client.log(msg), client.cancel)
    title = (title or '').strip() or video_title
    _, _, duration = metadata(path)
    if not 0 < duration <= 7200 or not .5 <= interval <= 5 or not 3 <= frames_per_request <= 10:
        raise ValueError('Invalid video length or sampling settings.')
    import hashlib
    identity = hashlib.sha256(f'{path.resolve()}:{path.stat().st_size}:{path.stat().st_mtime_ns}'.encode()).hexdigest()[:16]
    if selected_crop:
        identity = hashlib.sha256((identity+json.dumps(selected_crop)).encode()).hexdigest()[:16]
    frames = frames/identity
    frames.mkdir(exist_ok=True)
    times = [n*interval for n in range(int(duration/interval)+1) if n*interval < max(0, duration-.2)]
    times.append(max(0, duration-.2))
    cap = cv2.VideoCapture(str(path))
    lines, issues = {}, []
    try:
        from .accelerate import windows
        batches = list(windows(times, max(8, frames_per_request) if optimize else frames_per_request, 1 if optimize else 2))
        report_stage(client, 'Reading chords and lyrics', 0, len(batches))
        for batch, window in enumerate(batches, 1):
            check_cancel(client.cancel)
            client.log(f'Reading chord and lyric rows at {window[0]:.1f}–{window[-1]:.1f}s')
            images = [frame_at(cap, second, frames, selected_crop) for second in window]
            prompt = LEAD_PROMPT+'\n'+json.dumps({'frame_seconds': window, 'source_id': identity,
                      'previous_lines': [lines[n] for n in sorted(lines)[-6:]], 'user_instructions': instructions})
            result = client.request(prompt, LEAD_TRANSCRIPTION, images)
            for line in result['lines']:
                n = line['number']
                if not 1 <= n <= 10000 or not line['segments']:
                    raise ValueError('AI returned an invalid lyric row.')
                old = lines.get(n)
                if old and old['segments'] != line['segments']:
                    issues.append(f'Chord/lyric row {n}: conflicting readings; compare with the video.')
                if old is None or line['confidence'] > old['confidence']:
                    lines[n] = line
            issues.extend(result['observations'])
            client.partial_score = {'version': 1, 'source': source,
                'meta': {'title': title, 'instrument': 'chord', 'strings': 0, 'meter': [], 'bpm': 0},
                'bars': [], 'lead_lines': [lines[n] for n in sorted(lines)], 'review': issues}
            write_json(folder/'checkpoint.json', client.partial_score)
            report_stage(client, 'Reading chords and lyrics', batch, len(batches), len(lines))
    finally:
        cap.release()
    if not lines:
        raise ValueError('No readable chord or lyric rows found.')
    ordered = [lines[n] for n in sorted(lines)]
    for line in ordered:
        issues.extend(f"Row {line['number']}: {issue}" for issue in line['issues'])
        if line['confidence'] < .85:
            issues.append(f"Row {line['number']}: low-confidence reading.")
    gaps = sorted(set(range(1, max(lines)+1))-set(lines))
    if gaps:
        issues.append('Missing text rows: '+', '.join(map(str, gaps)))
    layout = default_format(title, 0)
    if instructions.strip():
        report_stage(client, 'Applying page instructions')
        layout = client.request(FORMAT_PROMPT+'\n'+json.dumps({'current_layout': layout,
                    'user_request': instructions, 'instrument': 'chord/lyrics',
                    'note': 'No measure counts are known; retain text rows and never merge numbered rests.'}), FORMAT)
        layout['merge_rests'] = []
        layout['bars_per_line'] = 0
    score = {'version': 1, 'source': source, 'meta': {'title': title, 'instrument': 'chord', 'strings': 0,
             'meter': [], 'bpm': 0}, 'bars': [], 'lead_lines': ordered, 'layout': layout,
             'review': list(dict.fromkeys(issues+layout['unsupported_requests'])), 'usage': client.usage,
             'elapsed_seconds': round(time.monotonic()-started, 1)}
    project, pdf = folder/'score.aiscore.json', folder/'score.pdf'
    write_json(project, score)
    report_stage(client, 'Engraving chord and lyric PDF')
    render(score, layout, pdf)
    return project, pdf, score


def draw_lead(c, score, layout, page_header, width, height, left, right):
    from .render import text_font
    from reportlab.pdfbase.pdfmetrics import stringWidth
    lines = score['lead_lines']
    # Wrap between lyric/chord segments while keeping each chord over its fragment.
    rows = []
    for line in lines:
        current, used = [], 0
        for segment in line['segments']:
            chord, lyric = segment['chord'], segment['lyric']
            font = text_font(lyric)
            size = 11
            sw = max(stringWidth(lyric or ' ', font, size), stringWidth(chord or ' ', text_font(chord, True), 10))+10
            if sw > right-left:
                # Long unsegmented lyrics wrap by character, preserving every character.
                pieces, piece = [], ''
                for char in lyric:
                    if piece and stringWidth(piece+char, font, size) > right-left-10:
                        pieces.append(piece); piece = ''
                    piece += char
                if piece:
                    pieces.append(piece)
                if current:
                    rows.append((line['section'], current)); current, used = [], 0
                for i, text in enumerate(pieces or ['']):
                    rows.append((line['section'] if i == 0 else '', [(chord if i == 0 else '', text, right-left)]))
                continue
            if current and used+sw > right-left:
                rows.append((line['section'], current)); current, used = [], 0
            current.append((chord, lyric, sw)); used += sw
        if current:
            rows.append((line['section'], current))
    per_page = max(1, int((height-170)/56))
    pages = (len(rows)+per_page-1)//per_page
    for page in range(pages):
        page_header(c, layout, score['meta'], page, pages)
        previous_section = ''
        for i, (section, segments) in enumerate(rows[page*per_page:(page+1)*per_page]):
            y = height-120-i*56
            if section and section != previous_section:
                c.setFont(text_font(section, True), 8)
                c.drawString(left, y+18, section)
            previous_section = section
            x = left
            for chord, lyric, advance in segments:
                c.setFont(text_font(chord, True), 10)
                c.drawString(x, y, chord)
                c.setFont(text_font(lyric), 11)
                c.drawString(x, y-17, lyric)
                x += advance
        c.showPage()
