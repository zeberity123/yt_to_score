"""Plain-language edits of a finished transcription: page layout, printed marks, targeted re-reads.

Notes are never rewritten from text. A request about wrong notes becomes a re-read of those
bars from the video through the same targeted review used during extraction.
"""
import json
from pathlib import Path

import cv2

from .contracts import EDIT, FORMAT, default_format, whole_rest
from .prompts import EDIT_PROMPT
from .accelerate import expand_result, review_windows
from .review import schema as review_schema, prompt as review_prompt, apply_result
from .providers import check_cancel

FORMAT_FIELDS = tuple(FORMAT['properties'])


def bars_summary(score):
    instrument, strings = score['meta']['instrument'], score['meta'].get('strings', 0)
    return [{'number': b['number'], 'tempo_bpm': b.get('tempo_bpm', 0), 'rehearsal': b.get('rehearsal', ''),
             'words': sorted({e['marks'] for e in b['events'] if e.get('marks')}),
             'whole_rest': whole_rest(b, instrument, strings)} for b in score['bars']]


def edit_score(client, score, text):
    """One text-only request describing the current layout and marks; returns the EDIT decision."""
    layout = {**default_format(), **score['layout']}
    summary = bars_summary(score)
    payload = {'current_layout': {k: layout[k] for k in FORMAT_FIELDS},
               'available_bars': [b['number'] for b in summary],
               'verified_whole_rests': [b['number'] for b in summary if b['whole_rest']],
               'bars': summary, 'user_request': text}
    return client.request(EDIT_PROMPT+'\n'+json.dumps(payload, separators=(',', ':'), ensure_ascii=False), EDIT)


def apply_marks(score, set_marks):
    """Set tempo/rehearsal and drop printed words per bar; returns the bar numbers that changed."""
    by_number = {b['number']: b for b in score['bars']}
    changed = []
    for item in set_marks:
        bar = by_number.get(item['bar'])
        if bar is None:
            raise ValueError(f"Bar {item['bar']} is not in this score.")
        if not 0 <= item['tempo_bpm'] <= 400:
            raise ValueError('A tempo must be between 0 and 400 beats per minute.')
        if len(item['rehearsal']) > 16:
            raise ValueError('A rehearsal label is at most 16 characters.')
        before = (bar.get('tempo_bpm', 0), bar.get('rehearsal', ''), [e['marks'] for e in bar['events']])
        bar['tempo_bpm'] = item['tempo_bpm']
        bar['rehearsal'] = item['rehearsal'].strip()
        remove = set(item['remove_words'])
        for event in bar['events']:
            if event['marks'] in remove:
                event['marks'] = ''
        if before != (bar['tempo_bpm'], bar['rehearsal'], [e['marks'] for e in bar['events']]):
            changed.append(bar['number'])
    return changed


def job_origin(score):
    folder, video = score.get('job_folder'), score.get('video_path')
    if not folder or not Path(folder).is_dir():
        raise ValueError('Re-reading bars needs the original AI job folder on this machine.')
    if not video or not Path(video).is_file():
        raise ValueError('Re-reading bars needs the original video file on this machine.')
    return Path(folder), Path(video)


def reread_bars(client, score, numbers):
    """Re-read the requested measures from video frames in place; returns review observations."""
    from drumscore.video import metadata
    from .pipeline import frame_at, reading_instructions, report_stage, video_identity
    folder, video = job_origin(score)
    meta = score['meta']
    bars = {b['number']: b for b in score['bars']}
    numbers = sorted({int(n) for n in numbers if int(n) in bars})
    if not numbers:
        return []
    crop = score.get('selected_crop')
    identity = video_identity(video, crop)
    frame_folder = folder/'frames'/identity[:16]
    frame_folder.mkdir(parents=True, exist_ok=True)
    _, _, duration = metadata(video)
    prompt = review_prompt(reading_instructions(True))
    reviews = list(review_windows(numbers, bars, duration))
    conflicts, observations = set(), []
    capture = cv2.VideoCapture(str(video))
    try:
        for index, (group, review_times) in enumerate(reviews, 1):
            check_cancel(client.cancel)
            report_stage(client, 'Re-reading bars from the video', index-1, len(reviews))
            # Three broad observations plus each requested bar's clearest moment, as in extraction.
            centers = [bars[n]['timestamp'] for n in group if n in bars]
            selected = sorted(set([review_times[0], review_times[len(review_times)//2], review_times[-1]]+centers))
            images = [frame_at(capture, t, frame_folder, crop) for t in selected]
            context = {'source_id': identity, 'meta': meta, 'frame_seconds': selected, 'review_only_bars': group,
                       'previous_observations': [bars.get(n) for n in group],
                       'reason': 'The user asked for these measures to be read again. Re-read from the images; do not merely repeat the prior answer.'}
            result = client.request(prompt+'\n'+json.dumps(context, separators=(',', ':')),
                                    review_schema(meta['instrument'], group, True), images)
            apply_result(result, group, bars, conflicts, observations, meta, expand_result)
    finally:
        capture.release()
    report_stage(client, 'Re-reading bars from the video', len(reviews), len(reviews))
    score['bars'] = [bars[n] for n in sorted(bars)]
    return observations
