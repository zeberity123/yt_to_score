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


def _staffs_at(gray, threshold, rules=5):
    """Find long, equally spaced staff or six-string TAB rules."""
    h, w = gray.shape
    if w < 50 or h < 15:
        return []
    ink = (gray < threshold).astype(np.uint8)
    if rules in (4, 6):
        # Fret digits interrupt the string rules, unlike ordinary noteheads.
        ink = cv2.morphologyEx(ink, cv2.MORPH_CLOSE, np.ones((1, max(5, w//160)), np.uint8))
    horizontal = cv2.morphologyEx(ink, cv2.MORPH_OPEN,
                                 np.ones((1, max(20, w//50 if rules in (4, 6) else w//7)), np.uint8))
    centers = [int(np.round(r.mean())) for r in runs(np.flatnonzero(horizontal.sum(axis=1) > w*.30))]
    found = []
    i = 0
    while i+rules-1 < len(centers):
        if rules in (4, 6):
            # Additional beam/bend rows must not break an otherwise regular grid.
            match = None
            for last in centers[i+rules-1:]:
                spacing = (last-centers[i])/(rules-1)
                # A tightly cropped four-string TAB needs only three gaps.
                # Requiring extra blank margins prevents recognizing it after
                # system splitting, so valid barlines cannot be joined.
                height_gaps = rules-1 if rules == 4 else rules+2
                if not 3 <= spacing <= min(35, h/height_gaps):
                    continue
                targets = [min(centers, key=lambda y: abs(y-(centers[i]+n*spacing))) for n in range(rules)]
                if all(abs(y-(centers[i]+n*spacing)) <= max(1.5, spacing*.12) for n,y in enumerate(targets)):
                    if rules == 4 and any(abs(y-end) <= max(1.5, spacing*.12)
                            for y in centers for end in (targets[0]-spacing, targets[-1]+spacing)):
                        continue  # Never mistake four of a five-line staff for TAB.
                    match = targets
                    break
            if match:
                if rules == 6:
                    # Dense fret/annotation rows can resemble a seventh string.
                    # Prefer the six-rule window with stronger continuous lines.
                    while True:
                        spacing=(match[-1]-match[0])/5
                        following=[y for y in centers if abs(y-match[-1]-spacing)<=max(1.5,spacing*.12)]
                        if not following:
                            break
                        next_row=min(following,key=lambda y:abs(y-match[-1]-spacing))
                        if horizontal[next_row].sum() <= horizontal[match[0]].sum()*1.1:
                            break
                        match=match[1:]+[next_row]
                found.append((match[0], match[-1], (match[-1]-match[0])/(rules-1)))
                i = centers.index(match[-1])+1
            else:
                i += 1
            continue
        lines = centers[i:i+rules]
        gaps = np.diff(lines)
        spacing = float(np.median(gaps))
        if 2 <= spacing <= min(35, h/8) and np.max(np.abs(gaps-spacing)) <= max(1.5, spacing*.22):
            found.append((lines[0], lines[-1], spacing))
            i += rules
        else:
            i += 1
    return found


def staffs(gray, rules=5):
    found = _staffs_at(gray, 235, rules)
    for group in _staffs_at(gray, 185, rules):
        if not any(abs(group[0]-other[0]) < max(3, group[2]*2) for other in found):
            found.append(group)
    return sorted(found)


def clean_tab(frame, rules=6):
    """Normalize both dark TAB on paper and white TAB over dark footage."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
    if np.mean(gray > 200) > .55:
        # Keep faint string rules and colored active fret numbers.
        return frame.min(axis=2) if frame.ndim == 3 else frame.copy()
    # Bright thin glyphs survive the opening; broad objects in the footage do not.
    white = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, np.ones((15, 15), np.uint8))
    ink = (white > 30) & (gray > 145)
    result = np.where(ink, 0, 255).astype(np.uint8)
    # The string rules can be much fainter than the digits. Detect their contrast
    # against adjacent rows, then retain them as gray rules in the printable image.
    thin = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, np.ones((7, 1), np.uint8))
    rules_image = np.where(thin > 12, 0, 255).astype(np.uint8)
    for first, last, spacing in staffs(rules_image, rules):
        for y in np.linspace(first, last, rules).round().astype(int):
            result[y] = np.minimum(result[y], 185)
    return result


def auto_region(frame, mode="auto", notation="staff"):
    if notation in ('guitar', 'bass', 'piano'):
        from .notation import detect_region
        return detect_region(frame, notation, mode)
    h, w = frame.shape[:2]
    gray = clean_score(frame, flatten=False)
    rules = 6 if notation == 'guitar' else 5
    if notation == 'guitar':
        # Inspect the lower panel separately so performance footage does not
        # determine the polarity of a white score strip.
        if np.mean(frame > 200) > .55:
            gray = clean_tab(frame)
        else:
            boundary = int(h*.70)
            gray[boundary:] = clean_tab(frame[boundary:])
    groups = staffs(gray, rules)
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
    if notation == 'guitar':
        light_panel = np.mean(frame[first:lower[0][1]+1] > 200) > .55
        top = top if light_panel and top > 0 else max(0, int(first-spacing*4))
        return Region(left/w, top/h, right/w, 1)
    # Leave room for tempo, section labels and accents even with translucent panels.
    top = min(top, max(0, int(first-spacing*7)))
    return Region(left/w, top/h, right/w, 1)


def signature(gray, max_width=900):
    scale = min(1, max_width/gray.shape[1])
    small = cv2.resize(gray, (round(gray.shape[1]*scale), max(1, round(gray.shape[0]*scale))),
                       interpolation=cv2.INTER_AREA)
    ink = (small < 150).astype(np.uint8)
    ink[:3] = ink[-3:] = 0
    ink[:, :3] = ink[:, -3:] = 0
    return ink


def tab_signature(gray, rules=6):
    """Compare fret numbers without the moving playback box or playhead."""
    ink = (gray < 150).astype(np.uint8)
    groups = staffs(gray, rules)
    spacing = groups[0][2] if groups else max(5, gray.shape[0]/14)
    if groups and rules == 6:
        ink[:max(0,int(groups[0][0]-spacing*5))]=0
    # A cursor/selection box spans the staff. Shorter rhythm stems must remain:
    # filtering at their length makes one-pixel compression changes toggle whole
    # stems on/off and creates false score changes.
    vertical_length = spacing*(6 if rules == 6 else 4)
    vertical = cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((max(12, int(vertical_length)), 1), np.uint8))
    horizontal = cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((1, max(30, gray.shape[1]//20)), np.uint8))
    ink[(vertical | horizontal) > 0] = 0
    if rules in (4,6):
        # Mask rules after detecting cursors, so the mask does not break a
        # continuous playback box into short fragments that escape removal.
        for first,last,_ in groups:
            for row in np.linspace(first,last,rules).round().astype(int):
                ink[max(0,row-1):min(len(ink),row+2)]=0
    return signature(255-ink*255, max_width=1600)


def difference(a, b, *, fine=False, stable=False):
    """Ink-relative error; one-pixel compression jitter is tolerated."""
    if a.shape != b.shape:
        return 1.0
    kernel = np.ones((3, 3), np.uint8)
    da, db = cv2.dilate(a, kernel), cv2.dilate(b, kernel)
    changed = (a & (1-db)) | (b & (1-da))
    # Thin compression noise on stems must not create a new score view.
    if fine and not stable:
        count, labels, stats, _ = cv2.connectedComponentsWithStats(changed)
        keep = stats[:, cv2.CC_STAT_AREA] >= 3
        keep[0] = False
        changed = keep[labels].astype(np.uint8)
    else:
        changed = cv2.morphologyEx(changed, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8),
                                 borderType=cv2.BORDER_CONSTANT, borderValue=0)
    score = float(changed.sum()) / max(1, int(a.sum())+int(b.sum()))
    # A single changed note matters even when the rest of a large page is identical.
    tile_width = 100 if fine else 150
    for y in range(0, a.shape[0], 100):
        for x in range(0, a.shape[1], tile_width):
            area = np.s_[y:y+100, x:x+tile_width]
            count = int(a[area].sum())+int(b[area].sum())
            if count >= 100:
                score = max(score, float(changed[area].sum())/count)
    # TAB digits have fewer pixels than noteheads; measure the fraction of one
    # frame's ink so a small fret-number change is not averaged away.
    return min(1.0, score*2) if fine else score


def split_systems(gray, padding=2, *, with_bounds=False, rules=5, groups=None):
    """Assign connected notation to each staff without slicing through symbols."""
    groups = staffs(gray, rules) if groups is None else groups
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
            strip = np.where(mask[y0:y1], gray[y0:y1], 255).astype(np.uint8)
            result.append((strip, (0, int(y0), w, int(y1))) if with_bounds else strip)
    return result


def system_signature(image, rules=5):
    """Align on the first staff so overlapping page crops can be compared."""
    groups = staffs(image, rules)
    if len(groups) != 1:
        return None
    width = 1600 if rules == 6 else 900
    scale = width/image.shape[1]
    resized = cv2.resize(image, (width, max(1, round(len(image)*scale))), interpolation=cv2.INTER_AREA)
    target = np.full((round(220*width/900), width), 255, np.uint8)
    offset = round(90*width/900)-round(groups[0][0]*scale)
    source_top = max(0, -offset)
    target_top = max(0, offset)
    length = min(len(resized)-source_top, len(target)-target_top)
    if length <= 0:
        return None
    target[target_top:target_top+length] = resized[source_top:source_top+length]
    return tab_signature(target, rules) if rules in (4, 6) else signature(target)
