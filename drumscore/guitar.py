"""Conservative overlap removal for horizontally advancing TAB panels."""
import cv2
import numpy as np

from .vision import difference, runs, staffs, tab_signature


def barlines(image):
    groups = staffs(image, 6)
    if len(groups) != 1:
        return []
    first, last, spacing = groups[0]
    band = image[first+2:last-1] < 150
    return [int(np.round(run.mean())) for run in runs(np.flatnonzero(band.mean(axis=0) > .94))]


def overlap_cut(previous, following):
    """Return matching barlines only when the shared notation verifies the match.

    Whole original panels remain available through the crop editor. Ambiguous
    matches leave both captures intact rather than guessing which notes to omit.
    """
    for left, right in ((.8,.2),(.65,.35),(.4,.6)):
        result = _overlap_cut(previous, following, left, right)
        if result:
            return result
    return None


def _overlap_cut(previous, following, left, right):
    if previous.shape[1] != following.shape[1] or min(previous.shape[1], following.shape[1]) < 150:
        return None
    width = previous.shape[1]
    sift = cv2.SIFT_create(nfeatures=3000)
    mask_a, mask_b = np.zeros_like(previous), np.zeros_like(following)
    mask_a[:, int(width*left):] = 255
    mask_b[:, :int(width*right)] = 255
    points_a, descriptors_a = sift.detectAndCompute(previous, mask_a)
    points_b, descriptors_b = sift.detectAndCompute(following, mask_b)
    if descriptors_a is None or descriptors_b is None or min(len(points_a),len(points_b)) < 10:
        return None
    matches = cv2.BFMatcher().knnMatch(descriptors_b, descriptors_a, k=2)
    good = [pair[0] for pair in matches if len(pair) == 2 and pair[0].distance < .7*pair[1].distance]
    if len(good) < 10:
        return None
    source = np.float32([points_b[m.queryIdx].pt for m in good])
    target = np.float32([points_a[m.trainIdx].pt for m in good])
    matrix, inliers = cv2.estimateAffinePartial2D(source, target, method=cv2.RANSAC, ransacReprojThreshold=2)
    if matrix is None or inliers.sum() < 10 or np.ptp(source[inliers.ravel()>0,0]) < width*.07:
        return None
    if abs(matrix[0,0]-1) > .005 or abs(matrix[1,0]) > .003:
        return None
    dx, dy = round(matrix[0,2]), round(matrix[1,2])
    if not width*.4 < dx < width*.96 or abs(dy) > 100:
        return None
    ay, by = max(0,dy), max(0,-dy)
    height = min(previous.shape[0]-ay, following.shape[0]-by)
    a = previous[ay:ay+height, dx:]
    b = following[by:by+height, :width-dx]
    if difference(tab_signature(a), tab_signature(b)) > .10:
        return None
    bars_b = barlines(following)
    for x in reversed(barlines(previous)):
        bx = x-dx
        if x < width-5 and bx > 5 and any(abs(other-bx) <= 3 for other in bars_b):
            return x, min(bars_b, key=lambda other:abs(other-bx))
    return None
