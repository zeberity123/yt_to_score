from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class Region:
    """Normalized coordinates, independent of video resolution."""
    left: float = 0
    top: float = 0
    right: float = 1
    bottom: float = 1

    def __post_init__(self):
        if not (0 <= self.left < self.right <= 1 and 0 <= self.top < self.bottom <= 1):
            raise ValueError("Crop must satisfy 0 <= left < right <= 1 and 0 <= top < bottom <= 1.")

    def crop(self, frame):
        h, w = frame.shape[:2]
        return frame[int(self.top*h):max(int(self.bottom*h), int(self.top*h)+1),
                     int(self.left*w):max(int(self.right*w), int(self.left*w)+1)]


def clean_score(frame, flatten=True):
    # Preserve saturated noteheads (red/blue/green), while suppressing light washes.
    if frame.ndim == 3:
        b, g, r = cv2.split(frame)
        bright, dark = cv2.max(cv2.max(b, g), r), cv2.min(cv2.min(b, g), r)
        colored_ink = (dark < 50) & (cv2.subtract(bright, dark) > 65)
        gray = np.where(colored_ink, dark, bright).astype(np.uint8)
    else:
        gray = frame
    # Translucent score panels have a gray, moving background behind dark notation.
    # Normalize only those regions; faint rules on white pages stay intact.
    if flatten and np.mean(gray > 225) < .60:
        # Estimate the paper behind the ink locally. A fixed white threshold can
        # erase faint staff rules when a bright part of the footage passes behind.
        background = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, np.ones((51, 51), np.uint8))
        gray = cv2.divide(gray, np.maximum(background, 1), scale=255)
    return np.clip((gray.astype(np.float32)-25) * 255/205, 0, 255).astype(np.uint8)


def runs(indices):
    if len(indices) == 0:
        return []
    return np.split(indices, np.where(np.diff(indices) > 1)[0]+1)


def _staffs_at(gray, threshold):
    """Find groups of five long, equally spaced horizontal staff rules."""
    h, w = gray.shape
    if w < 50 or h < 15:
        return []
    ink = (gray < threshold).astype(np.uint8)
    horizontal = cv2.morphologyEx(ink, cv2.MORPH_OPEN,
                                 np.ones((1, max(20, w//7)), np.uint8))
    centers = [int(np.round(r.mean())) for r in runs(np.flatnonzero(horizontal.sum(axis=1) > w*.30))]
    found = []
    i = 0
    while i+4 < len(centers):
        lines = centers[i:i+5]
        gaps = np.diff(lines)
        spacing = float(np.median(gaps))
        if 2 <= spacing <= min(35, h/8) and np.max(np.abs(gaps-spacing)) <= max(1.5, spacing*.22):
            found.append((lines[0], lines[-1], spacing))
            i += 5
        else:
            i += 1
    return found


def staffs(gray):
    found = _staffs_at(gray, 235)
    for group in _staffs_at(gray, 185):
        if not any(abs(group[0]-other[0]) < max(3, group[2]*2) for other in found):
            found.append(group)
    return sorted(found)


def auto_region(frame, mode="auto"):
    h, w = frame.shape[:2]
    gray = clean_score(frame, flatten=False)
    groups = staffs(gray)
    if mode == "page":
        return Region()
    if mode == "auto" and len(groups) >= 2 and np.mean(gray > 225) > .7:
        return Region()
    lower = [g for g in groups if g[0] > h*.48]
    if not lower:
        return Region(0, .70, 1, 1) if mode == "bottom" else Region()
    first = lower[0][0]
    # Locate the white panel above the bottom staff, without including the video.
    # Follow staff extents to exclude picture-in-picture panels beside the score.
    ink = (gray < 185).astype(np.uint8)
    horizontal = cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((1, max(20, w//7)), np.uint8))
    band = horizontal[lower[0][0]:lower[0][1]+1]
    segments = runs(np.flatnonzero(band.sum(axis=0) >= 3))
    cols = max(segments, key=len) if segments else []
    x0, x1 = (int(cols[0]), int(cols[-1])+1) if len(cols) else (0, w)
    spacing = lower[0][2]
    left_margin = spacing*(2 if x0 > w*.15 else 3)
    left, right = max(0, int(x0-left_margin)), min(w, int(x1+spacing*2))
    white = (gray[:, x0:x1] > 225).mean(axis=1)
    top = first
    while top > 0 and white[top-1] > .76:
        top -= 1
    # Leave room for tempo, section labels and accents even with translucent panels.
    top = min(top, max(0, int(first-spacing*7)))
    return Region(left/w, top/h, right/w, 1)


def signature(gray):
    scale = min(1, 900/gray.shape[1])
    small = cv2.resize(gray, (round(gray.shape[1]*scale), max(1, round(gray.shape[0]*scale))),
                       interpolation=cv2.INTER_AREA)
    ink = (small < 150).astype(np.uint8)
    ink[:3] = ink[-3:] = 0
    ink[:, :3] = ink[:, -3:] = 0
    return ink


def difference(a, b):
    """Ink-relative error; one-pixel compression jitter is tolerated."""
    if a.shape != b.shape:
        return 1.0
    kernel = np.ones((3, 3), np.uint8)
    da, db = cv2.dilate(a, kernel), cv2.dilate(b, kernel)
    changed = (a & (1-db)) | (b & (1-da))
    # Thin compression noise on stems must not create a new score view.
    changed = cv2.morphologyEx(changed, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8),
                             borderType=cv2.BORDER_CONSTANT, borderValue=0)
    score = float(changed.sum()) / max(1, int(a.sum())+int(b.sum()))
    # A single changed note matters even when the rest of a large page is identical.
    for y in range(0, a.shape[0], 100):
        for x in range(0, a.shape[1], 150):
            area = np.s_[y:y+100, x:x+150]
            count = int(a[area].sum())+int(b[area].sum())
            if count >= 100:
                score = max(score, float(changed[area].sum())/count)
    return score


def split_systems(gray, padding=2):
    """Assign connected notation to each staff without slicing through symbols."""
    groups = staffs(gray)
    if not groups:
        return []
    h, w = gray.shape
    ink = (gray < 235).astype(np.uint8)
    # Group letters/section boxes before assigning: individual glyph heights vary.
    spacing = float(np.median([g[2] for g in groups]))
    joined = cv2.dilate(ink, np.ones((3, max(3, int(spacing))), np.uint8))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(joined)
    assignments = np.full(count, -1, dtype=int)
    for label in range(1, count):
        x, y, cw, ch, area = stats[label]
        bottom = y+ch-1
        # Thin video-panel borders are not notation. Retain taller edge symbols.
        if y <= 2 and ch <= groups[0][2]*2 and bottom < groups[0][0]-groups[0][2]*2:
            continue
        if bottom >= h-3 and ch <= groups[-1][2]*2 and y > groups[-1][1]+groups[-1][2]*2:
            continue
        costs = []
        for first, last, spacing in groups:
            if bottom < first:
                cost = (first-bottom)/spacing
            elif y > last:
                cost = (y-last)*2.5/spacing
            else:
                cost = -min(bottom, last)+max(y, first)
            costs.append(cost)
        best = int(np.argmin(costs))
        if costs[best] <= 9:
            assignments[label] = best
    result = []
    for index, (first, last, spacing) in enumerate(groups):
        # Scrolling pages often show a clipped staff at a screen edge.
        if len(groups) > 1 and (first < spacing*2 or h-last < spacing*2):
            continue
        mask = (assignments[labels] == index).astype(np.uint8)
        mask = cv2.dilate(mask, np.ones((3, 3), np.uint8))
        rows = np.flatnonzero(mask.any(axis=1))
        if len(rows):
            y0, y1 = max(0, rows[0]-padding), min(h, rows[-1]+padding+1)
            result.append(np.where(mask[y0:y1], gray[y0:y1], 255).astype(np.uint8))
    return result


def system_signature(image):
    """Align on the first staff so overlapping page crops can be compared."""
    groups = staffs(image)
    if len(groups) != 1:
        return None
    scale = 900/image.shape[1]
    resized = cv2.resize(image, (900, max(1, round(len(image)*scale))), interpolation=cv2.INTER_AREA)
    target = np.full((220, 900), 255, np.uint8)
    offset = 90-round(groups[0][0]*scale)
    source_top = max(0, -offset)
    target_top = max(0, offset)
    length = min(len(resized)-source_top, len(target)-target_top)
    if length <= 0:
        return None
    target[target_top:target_top+length] = resized[source_top:source_top+length]
    return signature(target)
