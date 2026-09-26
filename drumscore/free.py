"""Capture outlined chord/lyric overlays without relying on staff rules or OCR."""
from pathlib import Path
import uuid

import cv2
import numpy as np
from PIL import Image

from .video import check_cancel, frames, metadata
from .vision import runs


def text_mask(frame, outline_pad=0):
    """Select outlined glyph interiors: 128 for blue, 255 for white, 0 otherwise."""
    h, w = frame.shape[:2]
    b, g, r = cv2.split(frame)
    blue = (b > 140) & (b.astype(int)-r > 75) & (g > 55)
    white = (frame.min(axis=2) > 200) & (frame.max(axis=2)-frame.min(axis=2) < 45)
    dark = frame.max(axis=2) < 85
    mask = np.zeros((h, w), np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats((blue | white).astype(np.uint8))
    for label in range(1, count):
        x, y, cw, ch, area = stats[label]
        if area < max(3, w*w*.000002) or ch > w*.12 or cw > w*.25:
            continue
        if ch < 2 or cw < 2 or area > h*w*.1:
            continue
        pad = max(2, outline_pad, round(min(cw, ch)*.15))
        x0, y0, x1, y1 = max(0, x-pad), max(0, y-pad), min(w, x+cw+pad), min(h, y+ch+pad)
        component = (labels[y0:y1, x0:x1] == label).astype(np.uint8)
        ring = cv2.dilate(component, np.ones((pad*2+1, pad*2+1), np.uint8)) > component
        # The black stroke surrounds overlay glyphs even over bright clothing.
        if ring.any() and np.mean(dark[y0:y1, x0:x1][ring]) >= .50:
            pixels = component > 0
            mask[y0:y1, x0:x1][pixels] = np.where(blue[y0:y1, x0:x1][pixels], 128, 255)
    return mask


def text_rows(mask):
    """Find any number of text rows; keep the crop width for chord alignment."""
    h, w = mask.shape
    counts = np.count_nonzero(mask, axis=1)
    active = (counts >= max(3, counts.max()*.06)).astype(np.uint8)
    active = cv2.morphologyEx(active[:, None], cv2.MORPH_CLOSE,
                             np.ones((max(3, round(w*.003)), 1), np.uint8))[:, 0]
    bands = [band for band in runs(np.flatnonzero(active)) if len(band) >= max(6, w*.008)]
    bounds = []
    for i, band in enumerate(bands):
        pad = max(4, round(len(band)*.30))
        top, bottom = max(0, int(band[0])-pad), min(h, int(band[-1])+pad+1)
        if i:
            top = max(top, (int(bands[i-1][-1])+int(band[0]))//2+1)
        if i+1 < len(bands):
            bottom = min(bottom, (int(band[-1])+int(bands[i+1][0]))//2+1)
        bounds.append((0, top, w, bottom))
    return bounds


def row_signature(mask, bounds):
    x0, y0, x1, y1 = bounds
    row = mask[y0:y1, x0:x1]
    # Chord rows are blue; white shirt/guitar highlights inside their band are
    # unrelated to the chord text. Lyric rows retain their white glyphs.
    if np.count_nonzero(row == 128) > np.count_nonzero(row)*.5:
        row = np.where(row == 128, 255, 0).astype(np.uint8)
    # Isolated highlights just above a lyric must not rescale the entire row.
    counts = np.count_nonzero(row, axis=1)
    occupied = np.flatnonzero(counts >= max(3, counts.max()*.08))
    if not len(occupied):
        return np.zeros((64, min(1024, row.shape[1])), dtype=bool)
    row = row[occupied[0]:occupied[-1]+1]
    return cv2.resize(row, (min(1024, row.shape[1]), 64), interpolation=cv2.INTER_AREA) > 100


def text_difference(a, b):
    """Compare glyphs, with one-pixel tolerance for compression and antialiasing."""
    kernel = np.ones((3, 3), np.uint8)
    unmatched = (a & ~cv2.dilate(b.astype(np.uint8), kernel).astype(bool)) | (b & ~cv2.dilate(a.astype(np.uint8), kernel).astype(bool))
    ink = a | b
    # Local comparisons retain a changed chord in an otherwise long text row.
    return max((np.count_nonzero(unmatched[:, x:x+128]) / np.count_nonzero(ink[:, x:x+128])
                for x in range(0, a.shape[1], 64)
                if np.count_nonzero(ink[:, x:x+128]) >= 200), default=0)


def extract_free(path, destination, title="Sheet music", source="", region=None,
                 interval=.5, threshold=.035, start=0, end=None,
                 progress=lambda *args: None, cancel=None, remove_overlap=True):
    from .extract import Extraction, ScoreLine

    if region is None:
        raise ValueError("Draw a rectangle around the chords and lyrics before using Chord mode.")
    if not np.isfinite(interval) or interval <= 0:
        raise ValueError("Sample interval must be greater than zero.")
    if not 0 < threshold < 1:
        raise ValueError("Change threshold must be between 0 and 1.")
    _, _, duration = metadata(path)
    end = duration if end is None else min(end, duration)
    if not 0 <= start < end:
        raise ValueError("Invalid start/end time.")
    directory = Path(destination) / ("free_"+uuid.uuid4().hex[:10])
    directory.mkdir(parents=True)
    project = Extraction(directory, title, source or str(path), region, [], [], 'free')
    current = None
    previous = []
    views = rejected = overlaps = 0

    def same(a, b):
        return len(a) == len(b) and all(text_difference(x, y) <= threshold for x, y in zip(a, b))

    def flush():
        nonlocal current, previous, views, rejected, overlaps
        if current is None:
            return
        if current['count'] < 2:
            rejected += 1
            current = None
            return
        signatures = current['signatures']
        overlap = 0
        if remove_overlap:
            for size in range(min(len(previous), len(signatures)), 0, -1):
                if same(previous[-size:], signatures[:size]):
                    overlap = size
                    break
        overlaps += overlap
        previous = signatures
        if overlap < len(signatures):
            views += 1
            frame = current['frame']
            fh, fw = frame.shape[:2]
            rx, ry = int(region.left*fw), int(region.top*fh)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            source_name = f'source_{views:04d}.png'
            Image.fromarray(rgb).save(directory/source_name)
            for x0, y0, x1, y1 in current['bounds'][overlap:]:
                name = f'line_{len(project.lines)+1:04d}.png'
                Image.fromarray(rgb[ry+y0:ry+y1, rx+x0:rx+x1]).save(directory/name)
                crop = [(rx+x0)/fw, (ry+y0)/fh, (rx+x1)/fw, (ry+y1)/fh]
                project.lines.append(ScoreLine(name, current['time'], views, source_path=source_name,
                                              crop=crop, original_path=name, original_crop=crop.copy()))
        current = None

    iterator = frames(path, interval, start, end, cancel)
    try:
        for t, frame in iterator:
            check_cancel(cancel)
            mask = text_mask(region.crop(frame))
            bounds = text_rows(mask)
            signatures = [row_signature(mask, box) for box in bounds]
            if current is not None and same(current['signatures'], signatures):
                current['count'] += 1
            else:
                flush()
                if signatures:
                    current = dict(signatures=signatures, bounds=bounds, count=1, time=t, frame=frame.copy())
                else:
                    # A blank interval separates intentional repeats.
                    previous = []
            progress(f"Scanning {t:.1f}s / {end:.1f}s · {len(project.lines)} lines", (t-start)/(end-start))
        check_cancel(cancel)
        flush()
    finally:
        iterator.close()
    if not project.lines:
        raise ValueError("No stable text rows found. Select outlined blue chords and white lyrics, or use Manual mode.")
    if rejected:
        project.warnings.append(f"Skipped {rejected} unstable sampled views (transitions or views shorter than two samples). Review for missing lines; use a smaller sample interval if needed.")
    if overlaps:
        project.warnings.append(f"Removed {overlaps} matching lines at consecutive page boundaries. Disable page-overlap removal if these are intentional repeats.")
    project.warnings.append("Review chord and lyric rows before printing. Use Background cleanup to choose White, Black, or Original. Moving or unoutlined text may need Manual mode.")
    project.save()
    progress(f"Ready: {len(project.lines)} lines from {views} score views", 1)
    return project
