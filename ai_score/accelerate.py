"""Conservative local image preparation and compact AI wire contracts."""
import copy
import math
import time
from pathlib import Path

import cv2
import numpy as np

from .contracts import TRANSCRIPTION, NOTE, BAR_DEFAULTS, validate_schema
from .providers import check_cancel, write_json


def compact_schema(instrument):
    schema = copy.deepcopy(TRANSCRIPTION)
    note = schema['properties']['bars']['items']['properties']['events']['items']['properties']['notes']['items']
    fields = {'string', 'fret', 'marks'} if instrument in ('bass', 'guitar') else (
        {'step', 'alter', 'octave', 'marks'} if instrument == 'piano' else {'step', 'octave', 'drum', 'marks'})
    note['properties'] = {k: v for k, v in note['properties'].items() if k in fields}
    note['required'] = list(note['properties'])
    return schema


def expand_result(result):
    result = copy.deepcopy(result)
    defaults = {k: '' if v['type'] == 'string' else 0 for k, v in NOTE['properties'].items()}
    for bar in result['bars']:
        # Journals written before tempo/rehearsal/multirest existed stay readable.
        for key, value in BAR_DEFAULTS.items():
            bar.setdefault(key, value)
        for event in bar['events']:
            event['notes'] = [{**defaults, **note} for note in event['notes']]
    validate_schema(result, TRANSCRIPTION)
    return result


def pattern_schema(instrument):
    """Wire-only compression: each printed occurrence still has its own number."""
    from .contracts import obj, arr, I, N, B, S
    schema = compact_schema(instrument)
    schema['properties']['repeats'] = arr(obj({'number': I, 'repeat_of': I, 'timestamp': N,
        'confidence': N, 'system_end': B, 'issues': arr(S), 'tempo_bpm': N, 'rehearsal': S, 'multirest': I}))
    schema['required'].append('repeats')
    return schema


def expand_patterns(result):
    bars = {bar['number']: copy.deepcopy(bar) for bar in result['bars']}
    numbers = [b['number'] for b in result['bars']]+[b['number'] for b in result['repeats']]
    if len(set(numbers)) != len(numbers):
        raise ValueError('AI pattern response repeated a measure number.')
    pending = list(result['repeats'])
    while pending:
        resolved = []
        for repeat in pending:
            if repeat['repeat_of'] not in bars:
                continue
            base = copy.deepcopy(bars[repeat['repeat_of']])
            # A repeated picture never inherits the first occurrence's section label or tempo.
            base.update({**BAR_DEFAULTS, **{key: value for key, value in repeat.items() if key != 'repeat_of'}})
            bars[repeat['number']] = base
            resolved.append(repeat)
        if not resolved:
            raise ValueError('AI pattern response has an unknown or circular measure reference.')
        pending = [repeat for repeat in pending if repeat not in resolved]
    return {'bars': [bars[n] for n in sorted(bars)], 'observations': result['observations']}


def windows(items, size=8, overlap=1):
    """No final request containing only observations from the previous request."""
    if not 0 <= overlap < size:
        raise ValueError('Invalid window overlap')
    for offset in range(0, len(items), size-overlap):
        yield items[offset:offset+size]
        if offset+size >= len(items):
            break


def parallel_batches(client, batches, reader, namespace='windows'):
    """Two independent numbered windows; separate caches and usage per worker.

    Only used by the integrated unlimited client. Bounded/API budget clients stay
    sequential so an estimate cannot be multiplied across concurrent workers.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from .providers import Client
    workers = []
    pool = ThreadPoolExecutor(max_workers=2)
    recorded = set()
    def collect(index):
        if index in recorded:
            return
        recorded.add(index)
        for key in ('requests', 'cache_hits', 'input_tokens', 'cached_input_tokens', 'output_tokens', 'estimated_usd'):
            client.usage[key] += workers[index].usage[key]
        write_json(client.folder/'usage-latest.json', client.usage)
    try:
        futures = {}
        for number, batch in enumerate(batches, 1):
            worker = Client(client.provider, client.model, client.key, client.folder/namespace/f'{number:04d}',
                            client.cancel, client.log, max_requests=None, max_output=client.max_output, budget=None)
            worker.auth_checked = client.auth_checked
            worker.gate = client.gate
            workers.append(worker)
            futures[pool.submit(reader, number, batch, worker)] = number
        failure = None
        for future in as_completed(futures):
            number = futures[future]
            if future.cancelled():
                continue
            try:
                result = future.result()
            except Exception as exc:
                if failure is None:
                    failure = exc
                client.cancel.set()
                for pending in futures:
                    pending.cancel()
                continue
            collect(number-1)
            yield number, result
        if failure is not None:
            raise failure
    except BaseException:
        client.cancel.set()
        raise
    finally:
        pool.shutdown(wait=True, cancel_futures=True)
        for index in range(len(workers)):
            collect(index)


def score_band(frame, instrument):
    """Reuse staff detection, retaining every detected staff and generous labels.

    Only vertical whitespace is removed; horizontal context is untouched. Unknown
    text layouts and frames with no reliable staff detection keep the full image.
    """
    if instrument == 'chord':
        return 0, frame.shape[0], None
    from drumscore.notation import clean_notation
    from drumscore.vision import staffs
    h, w = frame.shape[:2]
    scale = min(1., 960/w)
    small = cv2.resize(frame, (round(w*scale), round(h*scale)), interpolation=cv2.INTER_AREA)
    notation = 'staff' if instrument == 'drums' else instrument
    groups = []
    sh = len(small)
    # Separate panels avoid choosing polarity from the performer's background.
    for top, bottom in ((0, sh), (0, sh//2), (sh//2, sh)):
        gray = clean_notation(small[top:bottom], notation)
        rules = (4, 5) if instrument == 'bass' else ((5, 6) if instrument == 'guitar' else (5,))
        for count in rules:
            for first, last, spacing in staffs(gray, count):
                groups.append((first+top, last+top, spacing))
    if not groups:
        return 0, h, None
    margin = max(28, max(g[2] for g in groups)*7)
    top = max(0, math.floor((min(g[0] for g in groups)-margin)/scale))
    bottom = min(h, math.ceil((max(g[1] for g in groups)+margin)/scale)+1)
    if bottom-top > h*.88:
        return 0, h, None
    # Number labels remain in this comparison, as do dynamics and annotations.
    gray = clean_notation(small[round(top*scale):max(round(bottom*scale), round(top*scale)+1)], notation)
    fingerprint = (gray < 160).astype(np.uint8)
    return top, bottom, fingerprint


def prepare_frames(capture, times, folder, instrument, numbered, cancel, progress, selected_crop=None):
    started = time.monotonic()
    folder = Path(folder)/'prepared-v1'
    folder.mkdir(parents=True, exist_ok=True)
    records, previous = [], None
    pending = None
    pixels_in = pixels_out = cropped = 0
    for index, second in enumerate(times):
        check_cancel(cancel)
        capture.set(cv2.CAP_PROP_POS_MSEC, second*1000)
        ok, frame = capture.read()
        if not ok:
            raise ValueError(f'Cannot decode video at {second:.2f}s')
        if selected_crop:
            h, w = frame.shape[:2]
            l, t, r, b = selected_crop
            image = frame[int(t*h):max(int(b*h), int(t*h)+1), int(l*w):max(int(r*w), int(l*w)+1)]
            top, bottom, fingerprint = 0, len(image), None
            # Respect the user's full selection, including text beyond the staff.
        else:
            top, bottom, fingerprint = score_band(frame, instrument)
            image = frame[top:bottom]
        path = folder/f'frame-{second:010.3f}.jpg'
        if not cv2.imwrite(str(path), image, [cv2.IMWRITE_JPEG_QUALITY, 94]):
            raise OSError('Could not save a prepared frame')
        pixels_in += frame.shape[0]*frame.shape[1]
        pixels_out += image.shape[0]*image.shape[1]
        cropped += image.shape[:2] != frame.shape[:2]
        record = {'time': second, 'path': path, 'crop': selected_crop or [0, top/len(frame), 1, bottom/len(frame)]}
        identical = (numbered and fingerprint is not None and previous is not None and
                     fingerprint.shape == previous.shape and np.array_equal(fingerprint, previous))
        # Never deduplicate across time globally; preserve unnumbered repeats,
        # both ends of a hold, and at least one observation every six seconds.
        if identical and records and second-records[-1]['time'] < 6 and index < len(times)-1:
            pending = record
        else:
            if pending is not None:
                records.append(pending)
                pending = None
            records.append(record)
        previous = fingerprint
        if index % 10 == 0 or index == len(times)-1:
            progress(f'Preparing score images locally: {index+1}/{len(times)}')
    stats = {'sampled_frames': len(times), 'selected_frames': len(records), 'cropped_frames': cropped,
             'source_pixels': pixels_in, 'prepared_pixels': pixels_out,
             'local_seconds': round(time.monotonic()-started, 2)}
    write_json(folder/'plan.json', {'frames': [{**r, 'path': str(r['path'])} for r in records], **stats})
    return records, stats


def review_windows(targets, bars, duration):
    centers = []
    for number in targets:
        if number in bars:
            center = bars[number]['timestamp']
        else:
            before = max((n for n in bars if n < number), default=None)
            after = min((n for n in bars if n > number), default=None)
            center = ((bars[before]['timestamp']+bars[after]['timestamp'])/2 if before is not None and after is not None
                      else (0 if before is None else duration-3))
        centers.append((max(0, min(duration-.2, center)), number))
    groups = []
    for center, number in sorted(centers):
        if not groups or center-groups[-1][0][0] > 3 or len(groups[-1]) >= 3:
            groups.append([])
        groups[-1].append((center, number))
    for group in groups:
        middle = sum(c for c, _ in group)/len(group)
        times = sorted({max(0, min(duration-.12, c)) for c in
                        [middle+d for d in (-3, -1.5, -.5, 0, .5, 1.5, 3)]+[c for c, _ in group]})
        yield [n for _, n in group], times
