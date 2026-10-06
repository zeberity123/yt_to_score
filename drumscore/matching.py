"""Consecutive-view matching with optional evidence of whole-panel motion."""
import cv2
import numpy as np
from functools import lru_cache
from PIL import Image, ImageDraw, ImageFont

from .vision import difference, runs, staffs


@lru_cache(maxsize=1)
def _row_digits():
    from .numbered import _glyph
    fonts = [ImageFont.load_default(size=28)]
    for name in ('times.ttf', 'arial.ttf', 'segoeui.ttf', 'calibri.ttf'):
        try:
            fonts.append(ImageFont.truetype(name, 28))
        except OSError:
            pass
    templates = []
    for font in fonts:
        for number in range(10):
            image = Image.new('L', (50, 50))
            ImageDraw.Draw(image).text((5, 0), str(number), font=font, fill=255)
            templates.append((number, _glyph(np.array(image) > 20)))
    for scale in (.6, .8, 1.0):
        for thickness in (1, 2):
            for number in range(10):
                image = np.zeros((50, 50), np.uint8)
                cv2.putText(image, str(number), (5, 35), cv2.FONT_HERSHEY_SIMPLEX,
                            scale, 255, thickness)
                templates.append((number, _glyph(image > 100)))
    return np.array([n for n, _ in templates]), np.stack([t for _, t in templates])


def row_number(image):
    """Read only a confident printed label near the left end of a staff row.

    Unknown characters or ambiguous glyphs yield None; they never establish a
    different occurrence. This is optional evidence alongside musical matching.
    """
    from .numbered import _glyph
    groups = staffs(image)
    if len(groups) != 1:
        return None
    first, _, spacing = groups[0]
    rule = (image[max(0, first-1):first+2] < 185).any(axis=0).astype(np.uint8)
    rule = cv2.morphologyEx(rule.reshape(1, -1), cv2.MORPH_CLOSE,
                            np.ones((1, max(3, round(spacing*2))), np.uint8)).ravel()
    long = [r for r in runs(np.flatnonzero(rule)) if len(r) > image.shape[1]*.3]
    if not long:
        return None
    start = int(long[0][0])
    top, bottom = max(0, round(first-spacing*4)), max(0, round(first-spacing*.5))
    right = min(image.shape[1], round(start+spacing*4))
    roi = image[top:bottom, :right]
    if min(roi.shape, default=0) < 5:
        return None
    mask = cv2.morphologyEx((roi < 235).astype(np.uint8), cv2.MORPH_CLOSE, np.ones((3, 1), np.uint8))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    numbers, templates = _row_digits()
    pieces = [[i] for i in range(1, count) if stats[i, cv2.CC_STAT_AREA] >= 3]
    def bounds(piece):
        boxes = stats[piece]
        x, y = boxes[:, :2].min(axis=0)
        right, bottom = (boxes[:, :2]+boxes[:, 2:4]).max(axis=0)
        return x, y, right-x, bottom-y
    # Thin serif diagonals can break into two components after video compression.
    # Combine vertically adjacent fragments of one character, never neighbouring digits.
    merged = True
    while merged:
        merged = False
        for i in range(len(pieces)):
            ax, ay, aw, ah = bounds(pieces[i])
            for j in range(i+1, len(pieces)):
                bx, by, bw, bh = bounds(pieces[j])
                overlap = min(ax+aw, bx+bw)-max(ax, bx)
                gap = max(ay, by)-min(ay+ah, by+bh)
                _, _, width, height = bounds(pieces[i]+pieces[j])
                if overlap >= min(aw, bw)*.5 and gap <= spacing*.5 and width <= spacing*1.7 and height <= spacing*2:
                    pieces[i] += pieces.pop(j)
                    merged = True
                    break
            if merged:
                break
    characters = []
    for piece in pieces:
        x, y, width, height = bounds(piece)
        area = stats[piece, cv2.CC_STAT_AREA].sum()
        if not (spacing*.5 <= height <= spacing*2 and 1 <= width <= spacing*1.7 and area >= 6):
            continue
        sample = _glyph(np.isin(labels, piece))
        scores = np.ones(10)
        np.minimum.at(scores, numbers, np.mean(np.abs(templates-sample), axis=(1, 2)))
        order = np.argsort(scores)
        number = int(order[0]) if scores[order[0]] < .25 and scores[order[1]]-scores[order[0]] > .04 else None
        characters.append((x, x+width, y, height, number))
    clusters = []
    for character in sorted(characters):
        if (clusters and character[0]-clusters[-1][-1][1] < spacing*.9
                and abs((character[2]+character[3])-(clusters[-1][-1][2]+clusters[-1][-1][3])) < spacing*.4):
            clusters[-1].append(character)
        else:
            clusters.append([character])
    for cluster in clusters:
        if abs(cluster[0][0]-start) > spacing*2 or not 1 <= len(cluster) <= 3:
            continue
        if any(c[4] is None for c in cluster):
            return None
        number = int(''.join(str(c[4]) for c in cluster))
        return number if 0 < number < 1000 else None
    return None


def measure_anchors(image, *, rules=5, paired=False):
    """Barlines common to every staff; noteheads alone cannot establish a shift."""
    groups = staffs(image, rules)
    if paired and rules == 4:
        groups += staffs(image)
    if not groups:
        return []
    bands = [(image[first+2:last-1] < 185).mean(axis=0) > .9
             for first, last, _ in groups if last-first > 4]
    if len(bands) != len(groups):
        return []
    return [float(run.mean())/image.shape[1]
            for run in runs(np.flatnonzero(np.logical_and.reduce(bands)))]


def _anchors_follow_shift(anchors, dx, width):
    a, b = [np.asarray(values)*width for values in anchors]
    # Match both ways within the shared interior, with at least two widely
    # separated barlines. Fixed barlines reject a changed note's apparent motion.
    a = a[(a > 4) & (a < width-4) & (a+dx > 4) & (a+dx < width-4)]
    b = b[(b > 4) & (b < width-4) & (b-dx > 4) & (b-dx < width-4)]
    if min(len(a),len(b)) < 2 or min(np.ptp(a),np.ptp(b)) < width*.25:
        return False
    distances = np.abs(a[:,None]+dx-b[None,:])
    return bool(np.all(distances.min(axis=0) <= 2) and np.all(distances.min(axis=1) <= 2))


def aligned_difference(a, b, *, fine=False, stable=False, anchors=None):
    """Compare interior notation after a small, confidently established shift.

    Guitar retains its existing phase-correlation policy. Other instruments
    supply barline anchors and permit only horizontal movement after staff
    normalization, so changing a pitch or moving one hand cannot align away.
    """
    direct = difference(a,b,fine=fine,stable=stable)
    if direct <= .035 or a.shape != b.shape or min(a.shape) < 20:
        return direct
    shift, confidence = cv2.phaseCorrelate(a.astype(np.float32),b.astype(np.float32))
    dx,dy = (round(value) for value in shift)
    if confidence < .5 or abs(dx) > a.shape[1]*.03 or abs(dy) > 4:
        return direct
    if anchors is not None:
        if abs(dy) > 1 or not _anchors_follow_shift(anchors,dx,a.shape[1]):
            return direct
        dy = 0
    ax,bx=max(0,-dx),max(0,dx)
    ay,by=max(0,-dy),max(0,dy)
    height,width=a.shape[0]-abs(dy),a.shape[1]-abs(dx)
    if anchors is not None and dx:
        # A shift may reveal new notes at an edge. Ignore plain staff rules,
        # but retain the capture if either unmatched edge contains other ink.
        for ink,start in ((a,ax),(b,bx)):
            rules=cv2.morphologyEx(ink,cv2.MORPH_OPEN,np.ones((1,50),np.uint8))
            detail=ink & (1-rules)
            if int(detail[:,:start].sum())+int(detail[:,start+width:].sum()) > 12:
                return direct
    # Guitar can contain clipped digits at panel edges. Other instruments keep
    # all shared pixels, including edge accidentals and drum noteheads.
    edge=max(3,round(a.shape[1]*.01)) if anchors is None else 0
    left=a[ay:ay+height,ax+edge:ax+width-edge]
    right=b[by:by+height,bx+edge:bx+width-edge]
    if min(int(left.sum()),int(right.sum())) < 100:
        return direct
    aligned_error=difference(left,right,fine=fine,stable=stable)
    if anchors is not None and not fine:
        # A newly introduced alignment must not hide small notehead or flag
        # changes that the coarser stationary-view comparison could overlook.
        aligned_error=max(aligned_error,difference(left,right,fine=True))
    return min(direct,aligned_error)
