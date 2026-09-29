"""AI-assisted frame capture: the video's own score images are kept.

The AI only locates the score, checks printed bar order and duplicates across the captured
rows, flags broken rows, and engraves single rows when asked. Nothing is re-drawn by default.
"""
import json
from pathlib import Path

import cv2
from PIL import Image

from .contracts import LINE_CHECK, LINE_EDIT, bar_issues, default_format, normalize_score
from .prompts import LINE_CHECK_PROMPT, LINE_EDIT_PROMPT
from .accelerate import compact_schema, expand_result, windows
from .providers import Cancelled, check_cancel

CAPTURE_NOTATION = {'drums': 'staff', 'chord': 'free'}
INSTRUMENT_OF = {'staff': 'drums', 'free': 'chord'}


def capture_region(meta, selected_crop):
    from drumscore.vision import Region
    from .pipeline import expand_crop
    crop = selected_crop or expand_crop(meta.get('crop'))
    return Region(*crop) if crop else Region()


def extract_images(client, video, instrument, job_folder, title, source, output_dir, selected_crop=None, options=None):
    """Capture score rows with the frame extractor, guided and then checked by the AI."""
    from drumscore.extract import extract as capture_rows
    from drumscore.video import download, metadata
    from .pipeline import recon, report_stage, validate_crop, video_identity
    options = options or {}
    selected_crop = validate_crop(selected_crop)
    folder = Path(job_folder)
    folder.mkdir(parents=True, exist_ok=True)
    path, video_title = download(video, folder.parent/'video-cache', lambda msg, *_: client.log(msg), client.cancel)
    title = (title or '').strip() or video_title
    _, _, duration = metadata(path)
    if duration <= 0 or duration > 7200:
        raise ValueError('Use a video between 1 second and 2 hours.')
    identity = video_identity(path, selected_crop)
    frame_folder = folder/'frames'/identity[:16]
    frame_folder.mkdir(parents=True, exist_ok=True)
    capture = cv2.VideoCapture(str(path))
    try:
        meta = recon(client, capture, path, title, instrument, duration, frame_folder, identity, selected_crop)
    finally:
        capture.release()
    region = capture_region(meta, selected_crop)
    report_stage(client, 'Capturing score lines from the video')
    end = options.get('end')
    try:
        project = capture_rows(path, output_dir, title, source, region, mode='free' if instrument == 'chord' else 'auto',
                               interval=float(options.get('interval') or .5), threshold=float(options.get('threshold') or .035),
                               start=float(options.get('start') or 0), end=float(end) if end not in ('', None) else None,
                               remove_overlap=bool(options.get('overlap', True)),
                               progress=lambda text, fraction=None: report_stage(client, text), cancel=client.cancel,
                               notation=CAPTURE_NOTATION.get(instrument, instrument))
    except ValueError as error:
        if 'No stable score lines' in str(error) and not selected_crop:
            raise ValueError(f'{error} Or enable Select score area and mark the score yourself.') from error
        raise
    project.ai_check = {'method': 'images', 'meta': meta, 'lines': {}, 'observations': [], 'usage': dict(client.usage),
                        'job_folder': str(folder), 'frame_identity': identity[:16], 'source_id': identity,
                        'selected_crop': selected_crop}
    project.save()
    check_lines(client, project)
    project.ai_check['usage'] = dict(client.usage)
    project.save()
    return project


def check_lines(client, project):
    """Ask the AI, in batches of row images, for printed ranges, duplicates and problems."""
    from drumscore.video import Cancelled as CaptureCancelled
    from .pipeline import report_stage
    check = project.ai_check
    meta = check['meta']
    batches = list(windows(list(enumerate(project.lines, 1)), 8, 1))
    results, observations = {}, []
    total, done = len(batches), 0
    report_stage(client, 'Checking captured lines with AI', 0, total)
    try:
        for batch in batches:
            check_cancel(client.cancel)
            images = [project.directory/line.path for _, line in batch]
            context = {'source_id': check['source_id'],
                       'meta': {k: meta.get(k) for k in ('instrument', 'numbered', 'first_bar', 'last_bar', 'source_bars_per_line', 'meter')},
                       'lines': [{'index': index, 'time': line.time, 'view': line.view} for index, line in batch],
                       'previous_lines': [results[i] for i in sorted(results)][-6:]}
            result = client.request(LINE_CHECK_PROMPT+'\n'+json.dumps(context, separators=(',', ':')), LINE_CHECK, images)
            indices = {index for index, _ in batch}
            for item in result['lines']:
                if item['index'] not in indices or item['first_bar'] < 0 or item['last_bar'] < 0 or (
                        item['last_bar'] and item['last_bar'] < item['first_bar']):
                    raise ValueError('AI line check referred to a line outside its batch.')
                if item['duplicate_of'] and not 0 < item['duplicate_of'] < item['index']:
                    raise ValueError('AI line check named an invalid duplicate.')
                results.setdefault(item['index'], item)  # the first reading of an overlap line wins
            observations.extend(result['observations'])
            done += 1
            flagged = sum(1 for r in results.values() if r['problems'] or r['duplicate_of'] or not r['complete'])
            report_stage(client, 'Checking captured lines with AI', done, total, flagged)
    except (Cancelled, CaptureCancelled):
        project.warnings.append(f'AI line check cancelled after {done}/{total} batches; remaining lines are unchecked.')
    apply_line_check(project, results, observations)


def apply_line_check(project, results, observations):
    """Record findings per line, hide duplicates, and reorder only on confident printed numbering."""
    check = project.ai_check
    lines = project.lines
    for index, item in results.items():
        line = lines[index-1]
        line.notes = list(item['problems'])
        if not item['complete']:
            line.notes.append('Incomplete or obscured row; compare with the video.')
        check['lines'][line.path] = {k: item[k] for k in ('first_bar', 'last_bar', 'complete', 'duplicate_of', 'order_confidence')}
    excluded = 0
    for index in sorted(results):
        item, line = results[index], lines[index-1]
        target = item['duplicate_of']
        if not target or not line.included or not lines[target-1].included:
            continue
        origin = results.get(target)
        same_range = not origin or not item['first_bar'] or (item['first_bar'], item['last_bar']) == (origin['first_bar'], origin['last_bar'])
        if same_range:
            line.included = False  # never deleted: Undo brings it back
            line.notes.append(f'Duplicate of line {target}')
            excluded += 1
    included = [index for index, line in enumerate(lines, 1) if line.included]
    known = [results.get(index) for index in included]
    if check['meta'].get('numbered') and known and all(r and r['first_bar'] > 0 and r['order_confidence'] >= .8 for r in known):
        spans = sorted((r['first_bar'], r['last_bar'] or r['first_bar']) for r in known)
        if all(a[1] < b[0] for a, b in zip(spans, spans[1:])):
            order = sorted(included, key=lambda index: (results[index]['first_bar'], lines[index-1].time))
            if order != included:
                project.lines = [lines[index-1] for index in order]+[line for line in lines if not line.included]
                project.warnings.append('AI check reordered the captured lines by their printed bar numbers.')
        else:
            project.warnings.append('AI check found overlapping printed bar ranges; verify the line order against the video.')
    else:
        for previous, current in zip(known, known[1:]):
            if previous and current and previous['first_bar'] and current['first_bar'] and current['first_bar'] < previous['first_bar']:
                lines[included[known.index(current)]-1].notes.append('Printed bar numbers go backwards here; check the order.')
    flagged = sum(1 for line in project.lines if line.notes)
    check['observations'] = list(dict.fromkeys(observations))
    project.warnings.append(f'AI check: {excluded} duplicate lines excluded, {flagged} lines flagged.')
    project.warnings = list(dict.fromkeys(project.warnings+check['observations']))


def transcribe_line(client, project, index):
    """Engrave one captured row with the AI; the captured image stays as the line's original."""
    from drumscore.background import line_image
    from drumscore.ai_workspace import render_row, row_layout
    from .pipeline import reading_instructions, report_stage
    check = project.ai_check or {}
    meta = dict(check.get('meta') or {})
    instrument = meta.get('instrument') or INSTRUMENT_OF.get(project.notation, project.notation)
    if instrument == 'chord':
        raise ValueError('Chord and lyric rows cannot be engraved as notation.')
    if not 0 <= index < len(project.lines):
        raise ValueError('Select a score line first.')
    line = project.lines[index]
    folder = Path(check.get('job_folder') or project.directory)/'line-transcribe'
    folder.mkdir(parents=True, exist_ok=True)
    captured = line.original_path or line.path
    stem = Path(captured).stem
    raw_path, clean_path = folder/f'{stem}-raw.jpg', folder/f'{stem}-clean.jpg'
    line_image(project, line, 'original').convert('RGB').save(raw_path, quality=94)
    with Image.open(project.directory/captured) as image:
        image.convert('RGB').save(clean_path, quality=94)
    info = check.get('lines', {}).get(line.path) or check.get('lines', {}).get(captured) or {}
    prompt = reading_instructions(True).replace(
        'Transcribe every complete readable measure in this time window.',
        'Transcribe every complete readable measure in the attached score row: image 1 shows the captured colors, image 2 the cleaned strip of the same row.')
    context = {'source_id': check.get('source_id', ''), 'meta': meta, 'line_index': index+1, 'timestamp': line.time,
               'expected_bars': [info.get('first_bar', 0), info.get('last_bar', 0)], 'user_reading_guidance': ''}
    report_stage(client, f'Transcribing line {index+1} with AI')
    result = expand_result(client.request(prompt+'\n'+json.dumps(context, separators=(',', ':')), compact_schema(instrument), [raw_path, clean_path]))
    bars = sorted(result['bars'], key=lambda b: b['number'])
    if not bars:
        raise ValueError('The AI could not read any complete measure in this line.')
    numbers = [b['number'] for b in bars]
    if len(set(numbers)) != len(numbers):
        raise ValueError('AI returned duplicate measure numbers for this line.')
    strings = meta.get('strings') or {'guitar': 6, 'bass': 4}.get(instrument, 0)
    score = normalize_score({'version': 1, 'meta': {**meta, 'instrument': instrument, 'strings': strings, 'title': project.title,
                             'meter': meta.get('meter') or bars[0]['meter'], 'bpm': meta.get('bpm', 0),
                             'key_fifths': meta.get('key_fifths', 0)}, 'bars': bars, 'layout': default_format('', 0)})
    name = render_row(score, row_layout(score), numbers, project.directory)
    issues = [f"Bar {b['number']}: {issue}" for b in bars for issue in bar_issues(b, instrument, strings)]+list(result['observations'])
    line.path, line.ai_bar_ids = name, numbers
    line.notes = list(dict.fromkeys((line.notes or [])+issues))
    check.setdefault('transcribed', {})[name] = score['bars']
    check['usage'] = dict(client.usage)
    project.save()
    return line


def edit_lines(client, project, text):
    """Plain-language line-list edits for an AI-checked capture; returns notes for the review panel."""
    from .pipeline import report_stage
    check = project.ai_check
    payload = {'lines': [{'index': index, 'time': line.time, 'included': line.included, 'engraved': bool(line.ai_bar_ids),
                          'notes': line.notes or [], **{k: check['lines'].get(line.path, {}).get(k, 0) for k in ('first_bar', 'last_bar')}}
                         for index, line in enumerate(project.lines, 1)], 'user_request': text}
    report_stage(client, 'Applying AI edit')
    result = client.request(LINE_EDIT_PROMPT+'\n'+json.dumps(payload, separators=(',', ':'), ensure_ascii=False), LINE_EDIT)
    originals = list(project.lines)
    def at(index):
        if not 1 <= index <= len(originals):
            raise ValueError(f'Line {index} is not in this project.')
        return originals[index-1]
    engraved = result['retranscribe_lines'][:8]
    for index in engraved:
        transcribe_line(client, project, originals.index(at(index)))
    for index in result['exclude_lines']:
        at(index).included = False
    lines = list(originals)
    for move in result['move_line']:
        item = at(move['line'])
        lines.remove(item)
        if move['before']:
            lines.insert(lines.index(at(move['before'])), item)
        else:
            lines.append(item)
    project.lines = lines
    notes = list(result['notes'])
    if result['exclude_lines']:
        notes.append('Excluded lines '+', '.join(map(str, result['exclude_lines'])))
    if engraved:
        notes.append('Engraved lines '+', '.join(map(str, engraved)))
    unsupported = result['unsupported_requests']
    check.setdefault('edits', []).append({'request': text, 'exclude': result['exclude_lines'], 'move': result['move_line'],
                                          'retranscribe': engraved, 'unsupported': unsupported})
    check['usage'] = dict(client.usage)
    project.warnings = list(dict.fromkeys(project.warnings+notes+[f'Not applied: {item}' for item in unsupported]))
    project.save()
    return {'request': text, 'marks': [], 'reread': [], 'unsupported': unsupported, 'observations': notes}
