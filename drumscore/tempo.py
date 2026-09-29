"""Audio pulse estimates and conservative, opt-in timing hints for static TAB."""
import copy
import math
import os
import subprocess
import uuid

import cv2
import numpy as np
from PIL import Image

from .video import check_cancel, ffmpeg_path, metadata
from .vision import staffs, runs


def validate_timing(bpm, beats):
    try:
        bpm, beats = float(bpm), float(beats)
    except (TypeError, ValueError):
        raise ValueError('Enter BPM from 30 to 300 and quarter-note beats per bar from 1 to 16.') from None
    if not (math.isfinite(bpm) and 30 <= bpm <= 300 and math.isfinite(beats) and 1 <= beats <= 16):
        raise ValueError('Enter BPM from 30 to 300 and quarter-note beats per bar from 1 to 16.')
    return bpm, beats


def pulse_scores(audio, rate=11025):
    """Positive log spectral flux, followed by normalized onset autocorrelation."""
    hop, size = 128, 1024
    if len(audio) < rate * 4 or np.std(audio) < 1e-5:
        return None
    windows = np.lib.stride_tricks.sliding_window_view(audio, size)[::hop]
    spectrum = np.abs(np.fft.rfft(windows * np.hanning(size), axis=1))
    spectrum = np.log1p(spectrum[:, 4:372] * 10)
    onset = np.maximum(0, np.diff(spectrum, axis=0)).mean(axis=1)
    onset = np.maximum(0, onset - np.convolve(onset, np.ones(21)/21, mode='same'))
    onset -= onset.mean()
    energy = np.dot(onset, onset)
    if energy < 1e-8:
        return None
    ac = np.correlate(onset, onset, mode='full')[len(onset)-1:] / energy
    # Correct the smaller number of overlapping samples at long lags.
    ac *= len(onset) / np.maximum(1, len(onset)-np.arange(len(onset)))
    tempos = np.arange(60., 200.05, .1)
    lag = 60 * rate / (hop * tempos)
    def interpolate(points):
        center = np.rint(points).astype(int)
        delta = points-center
        return (ac[center] + delta*(ac[center+1]-ac[center-1])/2
                + delta**2*(ac[center+1]-2*ac[center]+ac[center-1])/2)
    scores = sum(weight*interpolate(lag*multiple)
                 for multiple, weight in ((1, 1), (2, .5), (3, .25)))
    # A broad tempo preference resolves some octave ties, not all of them.
    # The UI always exposes half/double alternatives and a manual override.
    scores *= np.exp(-.5*(np.log(tempos/120)/.75)**2)
    return tempos, scores


def detect_tempo(path, progress=lambda *args: None, cancel=None):
    _, _, duration = metadata(path)
    length = min(30., duration)
    starts = sorted(set(round(max(0, min(duration-length, duration*f-length/2)), 2)
                        for f in (.25, .5, .75)))
    results = []
    for index, start in enumerate(starts):
        check_cancel(cancel)
        progress('Estimating BPM from audio', index/len(starts))
        process = subprocess.Popen([ffmpeg_path(), '-v', 'error', '-ss', str(start), '-i', str(path),
            '-t', str(length), '-vn', '-ac', '1', '-ar', '11025', '-f', 'f32le', 'pipe:1'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        try:
            while True:
                check_cancel(cancel)
                try:
                    output, _ = process.communicate(timeout=.2)
                    break
                except subprocess.TimeoutExpired:
                    pass
            if process.returncode:
                raise ValueError('Could not read audio for BPM detection.')
        finally:
            if process.poll() is None:
                process.kill()
            process.communicate()
        result = pulse_scores(np.frombuffer(output, dtype='<f4'))
        if result is not None:
            results.append(result)
    if not results:
        raise ValueError('No steady audio pulse found. Enter BPM manually.')
    tempos = results[0][0]
    scores = np.mean([result[1] for result in results], axis=0)
    best = int(np.argmax(scores))
    if scores[best] < .08:
        raise ValueError('No steady audio pulse found. Enter BPM manually.')
    bpm = round(float(tempos[best]), 1)
    agreement = sum(abs(float(t[np.argmax(s)])-bpm)/bpm < .04 for t, s in results)
    return {'bpm': bpm, 'consistent': agreement == len(results),
            'alternatives': [round(bpm/2, 1), round(bpm*2, 1)]}


def complete_bars(image, rules):
    gray = np.array(image.convert('L'))
    padded = np.pad(gray, ((100, 100), (0, 0)), constant_values=255)
    groups = staffs(padded, rules)
    if len(groups) != 1:
        return None
    top, bottom, spacing = groups[0]
    if any(other[1] < top or other[0] > bottom for other in staffs(padded, 5)):
        return None
    top, bottom = top-100, bottom-100
    if top < 0 or bottom >= len(gray):
        return None
    band = gray[top+2:bottom-1] < 150
    boundaries = []
    for run in runs(np.flatnonzero(band.mean(axis=0) > .94)):
        x = int(run[-1])
        if boundaries and x-boundaries[-1] < spacing*.75:
            boundaries[-1] = x
        else:
            boundaries.append(x)
    if len(boundaries) < 2 or boundaries[0] > gray.shape[1]*.15:
        return None
    if any(b-a < spacing*2 for a, b in zip(boundaries, boundaries[1:])):
        return None
    # Staff lines can continue past the closing bar; notes cannot.
    tail = (gray[max(0,top-2):, min(gray.shape[1], boundaries[-1]+4):] < 150).astype('uint8')
    if tail.size:
        horizontal = cv2.morphologyEx(tail, cv2.MORPH_OPEN, np.ones((1, max(8, int(spacing))), 'uint8'))
        if np.count_nonzero(tail-horizontal) > spacing:
            return None
        # Even an empty partial bar must not be counted as a complete line.
        if np.count_nonzero(horizontal.any(axis=0)) > spacing*3:
            return None
    return len(boundaries)-1


def complete_system_bars(image, notation):
    """Require a complete system and agreement between its component staffs."""
    if notation in ('staff','guitar'):
        return complete_bars(image, 5 if notation == 'staff' else 6)
    from .notation import system_groups
    gray = np.array(image.convert('L'))
    padded = np.pad(gray, ((100,100),(0,0)), constant_values=255)
    systems = system_groups(padded, notation)
    if len(systems) != 1:
        return None
    ordinary = staffs(padded,5)
    components = [(g,5) for g in ordinary]
    if notation == 'bass':
        components += [(g,4) for g in staffs(padded,4) if not any(
            g[0] >= s[0]-2 and g[1] <= s[1]+2 for s in ordinary)]
    components.sort()
    if len(components) not in ((1,2) if notation == 'bass' else (2,)):
        return None
    counts = []
    for i,(group,rules) in enumerate(components):
        top = 0 if i == 0 else int((components[i-1][0][1]+group[0])/2)
        bottom = len(padded) if i == len(components)-1 else int((group[1]+components[i+1][0][0])/2)
        counts.append(complete_bars(Image.fromarray(padded[top:bottom]),rules))
    return counts[0] if counts[0] and all(n == counts[0] for n in counts) else None


def recover_timed_repeats(project, bpm, beats=4, interval=.5):
    """Require observed boundaries and nearby single passes consistent with BPM.

    This is a timing inference, not proof of a repeat. Never infer from the first
    or last view, moving/multiple systems, or an interval ending in a long gap.
    """
    bpm, beats = validate_timing(bpm, beats)
    lines = project.lines
    durations, expected = [], []
    for i, line in enumerate(lines):
        with Image.open(project.directory/line.path) as image:
            bars = complete_system_bars(image, project.notation)
        expected.append(bars*beats*60/bpm if bars else None)
        gap = lines[i+1].time-line.time if i+1 < len(lines) else None
        # A source view must remain visible until the following score change.
        durations.append(gap if gap and line.visible_until is not None
                         and abs(line.visible_until-lines[i+1].time) <= max(.15, interval*1.1) else None)
    added = 0
    output = []
    for i, line in enumerate(lines):
        output.append(line)
        duration, period = durations[i], expected[i]
        if i == 0 or i == len(lines)-1 or not duration or not period:
            continue
        passes = round(duration/period)
        tolerance = max(interval*1.25, period*.06)
        if not (2 <= passes <= 4 and abs(duration-passes*period) <= tolerance):
            continue
        neighbors = range(max(1, i-3), min(len(lines)-1, i+4))
        supported = [j for j in neighbors if j != i and expected[j] and durations[j]
                     and abs(durations[j]-expected[j]) <= max(interval*1.25, expected[j]*.06)]
        if len(supported) < 3 or not any(j < i for j in supported) or not any(j > i for j in supported):
            continue
        for repeat in range(1, passes):
            duplicate = copy.deepcopy(line)
            name = f'timed_{uuid.uuid4().hex[:12]}.png'
            (project.directory/name).write_bytes((project.directory/line.path).read_bytes())
            duplicate.path = duplicate.original_path = name
            duplicate.time = round(line.time + duration*repeat/passes, 3)
            duplicate.visible_until = round(line.time + duration*(repeat+1)/passes, 3)
            output.append(duplicate)
            added += 1
        line.visible_until = round(line.time + duration/passes, 3)
        project.warnings.append(f'Timing inferred {passes-1} repeat(s) after line {i+1} at {line.time:.1f}s. Review against the audio; a held score or pause can look the same.')
    project.lines = output
    project.warnings.append(f'Timing recovery at {bpm:g} BPM, {beats:g} quarter-note beats per bar: added {added} inferred line(s). Check tempo, meter, pauses, and written repeats before printing.')
    return added
