"""Consecutive-view matching with optional evidence of whole-panel motion."""
import cv2
import numpy as np

from .vision import difference, runs, staffs


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
    error=difference(left,right,fine=fine,stable=stable)
    if anchors is not None and not fine:
        # A newly introduced alignment must not hide small notehead or flag
        # changes that the coarser stationary-view comparison could overlook.
        error=max(error,difference(left,right,fine=True))
    return min(direct,error)
