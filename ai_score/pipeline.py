"""Overlapping visual observations, bar identity reconciliation, and targeted review."""
import copy
import hashlib
import json
import math
import time
import threading
import uuid
from pathlib import Path

import cv2

from .contracts import (RECON, TRANSCRIPTION, FORMAT, default_format, bar_issues,
                        validate_score, printed_slots)
from .prompts import RECON_PROMPT, TRANSCRIBE_PROMPT, FORMAT_PROMPT
from .providers import check_cancel, write_json
from .render import render
from .accelerate import compact_schema, expand_result, prepare_frames, windows, review_windows, parallel_batches, pattern_schema, expand_patterns


def report_stage(client, phase, completed=0, total=0, saved=0):
    if getattr(client, 'gate', None):
        client.gate.wait(client.cancel)
    callback = getattr(client, 'progress', None)
    if callback:
        callback(phase, completed, total, saved)


def validate_crop(crop):
    if crop is None:
        return None
    if (not isinstance(crop, (list, tuple)) or len(crop) != 4 or
            not all(isinstance(x, (int, float)) and math.isfinite(x) for x in crop) or
            not 0 <= crop[0] < crop[2] <= 1 or not 0 <= crop[1] < crop[3] <= 1):
        raise ValueError('Select a valid score area inside the video.')
    return list(crop)


def cancelled_draft(client, bars_per_line=0):
    """Only this run's completed observations; never load a stale disk checkpoint."""
    score = copy.deepcopy(getattr(client, 'partial_score', None))
    if not score or not (score.get('bars') or score.get('lead_lines')):
        return None
    warning = ('Incomplete draft: extraction was cancelled. Only completed batches are included; '
               'missing bars and conflicting readings have not all been reviewed. '
               'Additional instructions have not necessarily been applied. Retry extraction with '
               'the same settings to reuse completed AI responses.')
    issues = validate_score(score) if score['meta']['instrument'] != 'chord' else []
    score['review'] = list(dict.fromkeys([warning] + issues + score.get('review', []) +
        score.get('observations', []) +
        [f'Bar {n}: conflicting readings remain unresolved' for n in score.get('conflicts', [])]))
    score['partial'] = True
    score['layout'] = default_format(score['meta']['title'], bars_per_line)
    score['layout']['subtitle'] = 'INCOMPLETE DRAFT — extraction cancelled'
    score['usage'] = dict(client.usage)
    return score


def video_identity(path, selected_crop=None):
    """Stable request identity for one source file (and user crop), shared by every stage."""
    path = Path(path)
    parts = [str(path.resolve()), path.stat().st_size, path.stat().st_mtime_ns]
    if selected_crop:
        parts.append(selected_crop)
    return hashlib.sha256(json.dumps(parts).encode()).hexdigest()


def reading_instructions(optimize=True):
    """The transcription prompt, trimmed for the compact wire schema when optimizing."""
    prompt = TRANSCRIBE_PROMPT
    if optimize:
        prompt = prompt.replace("All notes include all fields: irrelevant string=0,fret='',step='',alter=0,octave=0,drum=''.", '')
        prompt += '\nReturn only fields in the attached schema. Irrelevant note fields are filled locally. Some images are score-only vertical crops; their full horizontal content and original timestamps are preserved.'
    return prompt


def expand_crop(region):
    """The model's score rectangle with a safety margin; None when it is unusable."""
    if not region or len(region) != 4 or not (0 <= region[0] < region[2] <= 1 and 0 <= region[1] < region[3] <= 1):
        return None
    return [max(0, region[0]-.035), max(0, region[1]-.075), min(1, region[2]+.035), min(1, region[3]+.075)]


def recon(client, capture, path, title, instrument, duration, frame_folder, identity, selected_crop=None):
    """One overview request on frames spread across the video: title, numbering, meter, crop."""
    times = sorted(set([min(.2, duration/2), min(3, duration/2), duration*.25,
                        duration*.5, duration*.75, max(0, duration-3), max(0, duration-.2)]))
    images = [frame_at(capture, t, frame_folder, selected_crop) for t in times]
    report_stage(client, 'Inspecting notation and numbering')
    client.log('Inspecting notation, score position and numbering')
    meta = client.request(RECON_PROMPT+'\n'+json.dumps({'instrument': instrument, 'video_title': title,
                           'frame_seconds': times, 'source_id': identity}), RECON, images)
    meta['instrument'] = instrument
    if title:
        meta['title'] = title
    if instrument in ('bass', 'guitar') and not 4 <= meta['strings'] <= 7:
        meta['strings'] = 6 if instrument == 'guitar' else 4
    if len(meta['meter']) not in (0, 2) or not -7 <= meta['key_fifths'] <= 7:
        raise ValueError('AI could not identify valid score metadata')
    return meta


def frame_at(capture, seconds, folder, crop=None):
    identity = hashlib.sha256(json.dumps([round(seconds, 3), crop]).encode()).hexdigest()[:16]
    path = Path(folder)/f'frame_{seconds:09.3f}_{identity}.jpg'
    if path.exists():
        return path
    capture.set(cv2.CAP_PROP_POS_MSEC, seconds*1000)
    ok, frame = capture.read()
    if not ok:
        raise ValueError(f'Cannot decode video at {seconds:.2f}s')
    if crop:
        height, width = frame.shape[:2]
        left, top, right, bottom = crop
        frame = frame[int(top*height):max(int(bottom*height), int(top*height)+1),
                      int(left*width):max(int(right*width), int(left*width)+1)]
    if frame.shape[1] > 1920:
        scale = 1920/frame.shape[1]
        frame = cv2.resize(frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    temporary = path.with_name(path.stem+'-'+uuid.uuid4().hex+'.jpg')
    try:
        if not cv2.imwrite(str(temporary), frame, [cv2.IMWRITE_JPEG_QUALITY, 94]):
            raise OSError('Could not save a source frame')
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def signature(bar):
    return json.dumps({'meter': bar['meter'], 'events': bar['events'], 'pickup': bar['pickup']}, sort_keys=True)


def merge_observations(current, incoming, meta, conflicts):
    for candidate in incoming:
        number = candidate['number']
        if not 0 <= number <= 10000:
            raise ValueError('AI returned an invalid measure number')
        old = current.get(number)
        if old and signature(old) != signature(candidate):
            conflicts.add(number)
        quality = lambda b: (len(bar_issues(b, meta['instrument'], meta['strings'])), -b['confidence'])
        if old is None or quality(candidate) < quality(old):
            current[number] = candidate


def format_score(client, score, instructions, bars_per_line, existing=None):
    layout = {**default_format(score['meta']['title'], bars_per_line), **copy.deepcopy(existing or {})}
    layout['bars_per_line'] = bars_per_line
    if instructions.strip():
        rests = [b['number'] for b in score['bars'] if b['events'] and not any(e['notes'] for e in b['events'])
                 and not bar_issues(b, score['meta']['instrument'], score['meta']['strings'])]
        payload = {'current_layout': layout, 'requested_bars_per_line': bars_per_line,
                   'available_bars': [b['number'] for b in score['bars']], 'verified_whole_rests': rests,
                   'user_request': instructions}
        layout = client.request(FORMAT_PROMPT+'\n'+json.dumps(payload), FORMAT)
    printed_slots(score, layout)  # Reject unsafe/invalid edits before changing any saved project.
    return layout


def extract(client, source, instrument, job_folder, bars_per_line=4, instructions='',
            interval=2., frames_per_request=6, full_frames=True, draft=True, optimize=True, selected_crop=None,
            title=None):
    from drumscore.video import download, metadata
    selected_crop = validate_crop(selected_crop)
    client.partial_score = None
    if instrument == 'chord':
        from .lead import extract_lead
        return extract_lead(client, source, job_folder, instructions, interval, frames_per_request,
                            optimize=optimize, selected_crop=selected_crop, title=title)
    started = time.monotonic()
    folder = Path(job_folder)
    folder.mkdir(parents=True, exist_ok=True)
    frame_folder = folder/'frames'
    frame_folder.mkdir(exist_ok=True)
    progress = client.log
    path, video_title = download(source, folder.parent/'video-cache', lambda msg, *_: progress(msg), client.cancel)
    # A cached local file only yields its stem; the caller supplies the real video title.
    title = (title or '').strip() or video_title
    width, height, duration = metadata(path)
    if duration <= 0 or duration > 7200:
        raise ValueError('Use a video between 1 second and 2 hours.')
    if not .5 <= interval <= 5 or not 3 <= frames_per_request <= 10:
        raise ValueError('Use 0.5–5 seconds per sample and 3–10 frames per request.')
    # Include source identity in every request to avoid conflating images from different jobs.
    identity = video_identity(path, selected_crop)
    frame_folder = folder/'frames'/identity[:16]
    frame_folder.mkdir(parents=True, exist_ok=True)
    project_path = folder/'score.aiscore.json'
    capture = cv2.VideoCapture(str(path))
    try:
        meta = recon(client, capture, path, title, instrument, duration, frame_folder, identity, selected_crop)
        crop = selected_crop
        if not full_frames and not selected_crop:
            crop = expand_crop(meta['crop']) or crop
        safe_end = max(0, duration-.2)
        sample_times = [float(t)*interval for t in range(math.ceil(duration/interval)) if float(t)*interval < safe_end]
        sample_times.append(safe_end)
        preparation = {}
        # Version 3: bars carry tempo_bpm/rehearsal/multirest; older journals must not resume.
        run_key = hashlib.sha256(json.dumps([identity, client.provider, client.model, instrument,
            instructions, interval, frames_per_request, full_frames, optimize, 3]).encode()).hexdigest()[:20]
        # Where later edits can find this job's frames again without re-transcribing.
        origin = {'job_folder': str(folder), 'frame_identity': identity[:16], 'selected_crop': selected_crop}
        resume_path = folder/f'resume-{run_key}.json'
        journal = {'transcription': {}, 'order': {}, 'reviews': {}, 'legacy_done': []}
        journal_lock = threading.RLock()
        def save_journal():
            with journal_lock:
                write_json(resume_path, journal)
        if resume_path.exists():
            journal.update(json.loads(resume_path.read_text(encoding='utf-8')))
        restored_frames = journal.get('frames')
        if optimize:
            report_stage(client, 'Preparing score images locally')
            def preparation_progress(message):
                progress(message)
                report_stage(client, message)
            if restored_frames and all(Path(r['path']).is_file() for r in restored_frames):
                records, preparation = restored_frames, journal['preparation']
            else:
                records, preparation = prepare_frames(capture, sample_times, frame_folder, instrument,
                                                       meta['numbered'], client.cancel, preparation_progress, selected_crop=selected_crop)
            journal['frames'] = [{**r, 'path': str(r['path'])} for r in records]
            journal['preparation'] = preparation
            batches = list(windows(records, max(8, frames_per_request), 1))
        else:
            records = [{'time': t} for t in sample_times]
            batches = list(windows(records, frames_per_request, 2))
        schema = compact_schema(instrument) if optimize else TRANSCRIPTION
        reading_prompt = reading_instructions(optimize)
        bars, conflicts, observations = {}, set(), list(meta['observations'])
        total = len(batches)
        preparation['transcription_requests'] = total
        concurrent = (optimize and meta['numbered'] and total > 1 and
                      client.max_requests is None and client.budget is None)
        preparation['parallel_workers'] = 2 if concurrent else 1
        report_stage(client, 'Transcribing score', 0, total)
        def read_window(batch, records, worker):
            check_cancel(client.cancel)
            if str(batch) in journal['transcription']:
                if worker.gate:
                    worker.gate.wait(client.cancel)
                worker.usage['cache_hits'] += 1
                return journal['transcription'][str(batch)]
            window = [r['time'] for r in records]
            progress(f'Transcribing window {batch}/{total}: {window[0]:.1f}–{window[-1]:.1f}s ({len(bars)} bars saved)')
            images = [r['path'] for r in records] if optimize else [frame_at(capture, t, frame_folder, crop) for t in window]
            context = {'source_id': identity, 'meta': meta, 'frame_seconds': window,
                       'previous_measures': [] if concurrent else [bars[n] for n in sorted(bars)[-6:]],
                       'user_reading_guidance': instructions}
            request_prompt = reading_prompt+'\n'+json.dumps(context, separators=(',', ':'))
            # Reuse existing paid responses before changing the wire format.
            result = worker.cached_request(request_prompt, schema, images) if optimize and meta['numbered'] else None
            if result is None and optimize and meta['numbered']:
                pattern_prompt = request_prompt + '''\nFor exactly identical musical bars in this numbered window,
write the full bar once in bars, then use repeats for the other printed occurrences.
repeat_of refers to a full bar in THIS response (or a resolvable repeat of it).
Only reuse when meter, pickup, every note, rhythm, technique and event marking are
identical. A changed note, rest, technique, meter or direction requires a full bar.
Every occurrence keeps its own printed number, timestamp, confidence, system_end
and issues. Never omit a numbered repeat. Use repeats=[] if none are certain.
Event marks contain only directions actually printed in the score, never explanations
of your transcription or rest numbering. Grace notes for piano/drums use duration=0
and event marks such as 'slashed grace eighth'.'''
                wire_schema = pattern_schema(instrument)
                result = expand_patterns(worker.request(pattern_prompt, wire_schema, images))
                cached = worker.cache_path(pattern_prompt, wire_schema, images)
            elif result is None:
                result = worker.request(request_prompt, schema, images)
                cached = worker.cache_path(request_prompt, schema, images)
            else:
                cached = worker.cache_path(request_prompt, schema, images)
            with journal_lock:
                journal['order'][str(batch)] = cached.stat().st_mtime if cached.exists() else time.time()
            return result
        results = (parallel_batches(client, batches, read_window) if concurrent else
                   ((number, read_window(number, records, client)) for number, records in enumerate(batches, 1)))
        completed = 0
        for batch, result in results:
            # Merge successful in-flight results even when another worker has
            # already acknowledged cancellation. Never lose a completed batch.
            journal['transcription'][str(batch)] = result
            # Merge in source-window order, independent of worker completion time.
            # Equal-confidence disagreements used to choose different candidates
            # on each restart, invalidating later review response caches.
            bars, conflicts, observations = {}, set(), list(meta['observations'])
            for key in sorted(journal['transcription'], key=int):
                saved = journal['transcription'][key]
                saved = expand_result(saved) if optimize else saved
                merge_observations(bars, saved['bars'], meta, conflicts)
                observations.extend(saved['observations'])
            completed += 1
            progress(f'Transcribed {completed}/{total} score batches ({len(bars)} bars saved)')
            client.partial_score = {'version': 1, 'source': source, 'video_path': str(path), **origin,
                       'meta': meta, 'preparation': preparation, 'bars': [bars[n] for n in sorted(bars)],
                       'conflicts': sorted(conflicts), 'observations': observations,
                       'completed_batches': completed, 'total_batches': total,
                       'seconds': batches[batch-1][-1]['time']}
            write_json(folder/'checkpoint.json', client.partial_score)
            save_journal()
            report_stage(client, 'Transcribing score', completed, total, len(bars))
        score = {'version': 1, 'source': source, 'video_path': str(path), **origin, 'meta': meta,
                 'preparation': preparation, 'bars': [bars[n] for n in sorted(bars)], 'observations': observations}
        from .review import music_signature, needs_visual_review, schema as review_schema, prompt as review_prompt, apply_result
        variants = {}
        for result in journal['transcription'].values():
            expanded = expand_result(result) if optimize else result
            for bar in expanded['bars']:
                variants.setdefault(bar['number'], set()).add(music_signature(bar))
        music_conflicts = {n for n, readings in variants.items() if len(readings) > 1}
        annotation_conflicts = conflicts-music_conflicts
        if annotation_conflicts:
            observations.append('Differing annotation wording retained for manual review in bars: '+
                                ', '.join(map(str, sorted(annotation_conflicts))))
        # Compatibility: replay only EXACT old request cache matches, without
        # ever sending the old broad review prompt for a fresh inference.
        if not journal.get('legacy_checked') and hasattr(client, 'cached_request'):
            report_stage(client, 'Restoring completed reviews from the response cache')
            legacy_bars, legacy_conflicts = {}, set()
            for key in sorted(journal['transcription'], key=lambda k: journal['order'].get(k, int(k))):
                result = journal['transcription'][key]
                result = expand_result(result) if optimize else result
                merge_observations(legacy_bars, result['bars'], meta, legacy_conflicts)
            legacy_last = meta['last_bar'] or max(legacy_bars, default=0)
            legacy_missing = set(range(meta['first_bar'], legacy_last+1))-set(legacy_bars)
            legacy_targets = sorted(legacy_conflicts | legacy_missing | {n for n, b in legacy_bars.items()
                if bar_issues(b, instrument, meta['strings'])})
            for numbers, review_times in review_windows(legacy_targets, legacy_bars, duration):
                images = [frame_at(capture, t, frame_folder, selected_crop) for t in review_times]
                context = {'source_id': identity, 'meta': meta, 'frame_seconds': review_times,
                           'review_only_bars': numbers, 'previous_observations': [legacy_bars.get(n) for n in numbers],
                           'reason': 'Conflicting visual readings, missing measure, or rhythm validation issue. Re-read from images; do not merely repeat the prior answer.'}
                result = client.cached_request(reading_prompt+'\n'+json.dumps(context, separators=(',', ':')), schema, images)
                if result is None:
                    continue
                result = expand_result(result) if optimize else result
                # A completed review may legitimately find no readable bar.
                # Retain its warning instead of paying to ask the same thing again.
                journal['legacy_done'].extend(numbers)
                for number in numbers:
                    found = next((b for b in result['bars'] if b['number'] == number), None)
                    if found:
                        legacy_bars[number] = bars[number] = found
                        journal.setdefault('legacy_bars', {})[str(number)] = found
                    else:
                        journal.setdefault('legacy_observations', []).append(
                            f'Bar {number}: the completed review could not recover this measure; verify manually.')
                observations.extend(result['observations'])
                journal.setdefault('legacy_observations', []).extend(result['observations'])
                save_journal()
            journal['legacy_checked'] = True
        for number, bar in journal.get('legacy_bars', {}).items():
            bars[int(number)] = bar
        observations.extend(journal.get('legacy_observations', []))
        conflicts = music_conflicts
        for number in journal['legacy_done']:
            if number in bars and not needs_visual_review(bars[number], meta):
                conflicts.discard(number)
        # Review actual visual/rhythmic problems, not unsupported engraving or
        # differently worded annotation prose. Every remaining limitation stays
        # in the exported score's review notes.
        last = meta['last_bar'] or max(bars, default=0)
        first = meta['first_bar']
        if not 0 <= first <= last <= 10000:
            raise ValueError('Inconsistent first/last measure numbers; inspect checkpoint.json')
        missing = set(range(first, last+1))-set(bars)
        targets = sorted((conflicts | missing | {n for n, b in bars.items() if needs_visual_review(b, meta)})
                         - set(journal['legacy_done']))
        progress(f'Reviewing {len(targets)} ambiguous or missing bars')
        if 'review_plan' not in journal:
            journal['review_plan'] = list(review_windows(targets, bars, duration))
            journal['review_base'] = copy.deepcopy(bars)
        reviews = journal['review_plan']
        review_base = {int(n): b for n, b in journal['review_base'].items()}
        save_journal()
        preparation['review_requests'] = len(reviews)
        preparation['restored_review_bars'] = len(set(journal['legacy_done']))
        score['bars'] = [bars[n] for n in sorted(bars)]
        score['conflicts'] = sorted(conflicts)
        client.partial_score = score
        write_json(folder/'checkpoint.json', score)
        report_stage(client, 'Reviewing uncertain bars', 0, len(reviews), len(bars))
        def read_review(index, review, worker):
            check_cancel(client.cancel)
            if str(index) in journal['reviews']:
                if worker.gate:
                    worker.gate.wait(client.cancel)
                worker.usage['cache_hits'] += 1
                return journal['reviews'][str(index)]
            numbers, review_times = review
            # Three broad observations plus each requested bar's clearest moment.
            # Keep denser old evidence only for legacy cache compatibility above.
            centers = [review_base[n]['timestamp'] for n in numbers if n in review_base]
            selected_times = sorted(set([review_times[0], review_times[len(review_times)//2], review_times[-1]]+centers))
            # Each worker owns its decoder; OpenCV captures are not thread-safe.
            local_capture = cv2.VideoCapture(str(path))
            try:
                images = [frame_at(local_capture, t, frame_folder, selected_crop) for t in selected_times]
            finally:
                local_capture.release()
            context = {'source_id': identity, 'meta': meta, 'frame_seconds': selected_times,
                       'review_only_bars': numbers, 'previous_observations': [review_base.get(n) for n in numbers],
                       'reason': 'Conflicting visual readings, missing measure, or rhythm validation issue. Re-read from images; do not merely repeat the prior answer.'}
            return worker.request(review_prompt(reading_prompt)+'\n'+json.dumps(context, separators=(',', ':')),
                                  review_schema(instrument, numbers, optimize), images)
        review_results = (parallel_batches(client, reviews, read_review, namespace='targeted-reviews') if concurrent else
                          ((index, read_review(index, review, client)) for index, review in enumerate(reviews, 1)))
        for completed, (review_index, result) in enumerate(review_results, 1):
            numbers, _ = reviews[review_index-1]
            apply_result(result, numbers, bars, conflicts, observations, meta, expand_result if optimize else None)
            journal['reviews'][str(review_index)] = result
            save_journal()
            score['bars'] = [bars[n] for n in sorted(bars)]
            score['conflicts'] = sorted(conflicts)
            client.partial_score = score
            write_json(folder/'checkpoint.json', score)
            report_stage(client, 'Reviewing uncertain bars', completed, len(reviews), len(bars))
        score['bars'] = [bars[n] for n in sorted(bars)]
        if not meta['meter'] and bars:
            meta['meter'] = score['bars'][0]['meter']
            observations.append('Time signature was not visible in the overview; the first transcribed measure supplies the display meter. Verify it against the source.')
        issues = validate_score(score)
        if not bars_per_line and not any(b.get('system_end') for b in score['bars']) and not meta.get('source_bars_per_line'):
            issues.append('Source row breaks could not be identified; using four bars per row. Enable the bars-per-line override to change this.')
        issues += [f'Bar {n}: conflicting readings remain unresolved' for n in sorted(conflicts)]
        if not meta['numbered']:
            issues.append('Unnumbered score: verify occurrence order and identical repeats against the video.')
        if not meta['last_bar']:
            issues.append('Final measure number was not visible: verify the ending against the video.')
        issues += list(dict.fromkeys(observations))
        score['review'] = list(dict.fromkeys(issues))
        score['layout'] = default_format(meta['title'], bars_per_line)
        client.partial_score = score
        write_json(project_path, score)  # Musical work survives formatting/provider failures.
        progress('Applying page instructions')
        report_stage(client, 'Applying page instructions')
        score['layout'] = format_score(client, score, instructions, bars_per_line)
        score['instructions'] = instructions
        score['review'].extend(score['layout']['unsupported_requests'])
        score['usage'] = client.usage
        score['elapsed_seconds'] = round(time.monotonic()-started, 1)
        write_json(project_path, score)
        pdf = folder/'score.pdf'
        if not score['review'] or draft:
            progress('Engraving vector PDF')
            report_stage(client, 'Engraving vector PDF')
            render(score, score['layout'], pdf)
        write_json(folder/'review.json', {'issues': score['review'], 'usage': client.usage,
                                        'elapsed_seconds': score['elapsed_seconds']})
        return project_path, pdf if pdf.exists() else None, score
    finally:
        capture.release()


def reformat(client, project, instructions, bars_per_line):
    path = Path(project)
    score = json.loads(path.read_text(encoding='utf-8'))
    layout = format_score(client, score, instructions, bars_per_line, score.get('layout'))
    # Render first; don't overwrite a valid project if the new layout is too dense.
    pdf = path.parent/'score-reformatted.pdf'
    render(score, layout, pdf)
    score['layout'] = layout
    score['instructions'] = instructions
    score['last_format_usage'] = client.usage
    updated = path.parent/'score-reformatted.aiscore.json'
    write_json(updated, score)
    return updated, pdf, score
