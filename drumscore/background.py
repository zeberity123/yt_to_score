"""Reversible background rendering shared by review images and PDF printing."""
import cv2
import numpy as np
from PIL import Image


def validate_background(value):
    if value not in ('white', 'black', 'original'):
        raise ValueError('Choose White, Black, or Original background.')
    return value


def render_background(image, notation, background='white'):
    validate_background(background)
    rgb = np.array(image.convert('RGB'))
    if background == 'original':
        return Image.fromarray(rgb)
    if notation in ('free', 'chord'):
        from .free import text_mask, text_rows
        mask = text_mask(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), outline_pad=max(3,round(rgb.shape[1]/260)))
        bands = text_rows(mask)
        selected = np.zeros(mask.shape, bool)
        for x0,y0,x1,y1 in bands:
            row = mask[y0:y1,x0:x1]
            if np.count_nonzero(row == 128) > np.count_nonzero(row)*.5:
                row[row == 255] = 0
            selected[y0:y1,x0:x1] = True
        mask[~selected] = 0
        # Discard isolated compression specks, preserving small Japanese marks.
        n, labels, stats, _ = cv2.connectedComponentsWithStats((mask > 0).astype(np.uint8))
        keep = stats[:, cv2.CC_STAT_AREA] >= max(3, rgb.shape[1]*.003)
        keep[0] = False
        mask[~keep[labels]] = 0
        result = np.full_like(rgb, 255 if background == 'white' else 0)
        result[mask == 255] = 0 if background == 'white' else 255
        result[mask == 128] = (0, 110, 200) if background == 'white' else (0, 165, 255)
        return Image.fromarray(result)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    if np.mean(gray == 255) > .60:
        result = rgb.copy()
    elif np.mean(gray > 225) > .60:
        # Existing cleaned captures already contain the full notation. Preserve
        # faint string rules and antialiasing; only clear nearly white paper.
        result = rgb.copy()
        result[gray > 235] = 255
    else:
        from .notation import clean_notation
        cleaned = clean_notation(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), notation)
        result = cv2.cvtColor(cleaned, cv2.COLOR_GRAY2RGB)
        result[cleaned > 235] = 255
    return Image.fromarray(255-result if background == 'black' else result)
