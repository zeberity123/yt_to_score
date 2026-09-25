"""Arrange captured TAB measures without modifying the captured images."""
from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image

from .editing import project_file
from .vision import staffs, runs


@dataclass
class PrintRow:
    image: Image.Image
    height_scale: float = 1.0
    bars: int | None = None
    # Short final rows retain the same notation size as the complete rows.
    width_fraction: float = 1.0


def validate_bars(value):
    try:
        number = float(value)
    except (ValueError, TypeError):
        raise ValueError('Bars per line must be 4-16, or 0 for captured lines.') from None
    if number != 0 and not (4 <= number <= 16 and number.is_integer()):
        raise ValueError('Bars per line must be 4-16, or 0 for captured lines.')
    return int(number)


def tab_measures(image, rules):
    """Return a complete column partition, or decline an uncertain/mixed panel."""
    gray = np.array(image.convert('L'))
    # Captured strips can be too tight for the extraction detector's margin
    # assumptions. Padding affects detection only, never the printed pixels.
    padded = np.pad(gray,((100,100),(0,0)),constant_values=255)
    groups = staffs(padded,rules)
    if len(groups) != 1:
        return None
    first,last,spacing = groups[0]
    # The ordinary detector can see five of six TAB strings as a staff. Only
    # a separate staff makes this a combined panel that must remain intact.
    if any(other[1] < first or other[0] > last for other in staffs(padded,5)):
        return None
    first,last = first-100,last-100
    if first < 0 or last >= len(gray):
        return None
    # Match the extraction joiner's dark barlines; gray editor/playback borders
    # can span the strings too and must not create a spurious tiny measure.
    band = gray[first+2:last-1] < 150
    bars = [int(run[-1])+1 for run in runs(np.flatnonzero(band.mean(axis=0) > .94))]
    # Double/repeat barlines form one boundary, not a tiny extra measure.
    boundaries=[]
    for x in bars:
        if boundaries and x-boundaries[-1] < spacing*.75:
            boundaries[-1]=x
        else:
            boundaries.append(x)
    if not boundaries:
        return None
    # Preserve the TAB clef/time-signature prefix with the first measure.
    starts_at_bar=boundaries[0] <= max(spacing*6,image.width*.10)
    ends_at_bar=boundaries[-1] >= image.width-max(4,spacing*.25)
    if starts_at_bar:
        boundaries=boundaries[1:]
    cuts=[0]+[x for x in boundaries if x < image.width-max(4,spacing*.25)]+[image.width]
    if (len(cuts)==2 and not (starts_at_bar and ends_at_bar)) or any(b-a < spacing*2 for a,b in zip(cuts,cuts[1:])):
        return None
    return list(zip(cuts,cuts[1:])), first, spacing


def print_rows(project,bars_per_line=None):
    target=validate_bars(project.bars_per_line if bars_per_line is None else bars_per_line)
    if target and project.notation not in ('guitar','bass'):
        raise ValueError('Bar layout is available for guitar and bass TAB.')
    rows, pending, notes = [], [], []
    pending_scale=1.0
    def flush():
        if not pending:
            return
        above=max(anchor for _,anchor in pending)
        below=max(image.height-anchor for image,anchor in pending)
        result=Image.new('RGB',(sum(image.width for image,_ in pending),above+below),'white')
        x=0
        for image,anchor in pending:
            result.paste(image,(x,above-anchor))
            x+=image.width
        rows.append(PrintRow(result,pending_scale,len(pending)))
        pending.clear()
    for index,line in enumerate(project.lines):
        if not line.included:
            continue
        scale=float(line.height_scale)
        if not .25 <= scale <= 2:
            raise ValueError('Line height must be 25-200%.')
        with Image.open(project_file(project,line.path)) as source:
            image=source.convert('RGB')
        measures=tab_measures(image,6 if project.notation=='guitar' else 4) if target else None
        if not measures:
            flush()
            rows.append(PrintRow(image,scale))
            if target:
                notes.append(f'Line {index+1} kept intact: bar boundaries could not be confirmed.')
            continue
        cuts,first,spacing=measures
        if pending and scale != pending_scale:
            flush()
        pending_scale=scale
        # Normalize source resolutions uniformly in both axes. Height correction
        # stays separate so it is neither lost nor compounded by a second edit.
        factor=24/spacing
        for left,right in cuts:
            part=image.crop((left,0,right,image.height))
            size=(max(1,round(part.width*factor)),max(1,round(part.height*factor)))
            if size != part.size:
                part=part.resize(size,Image.Resampling.LANCZOS)
            pending.append((part,round(first*factor)))
            if len(pending)==target:
                flush()
    flush()
    complete=[row.image.width for row in rows if row.bars == target]
    reference=float(np.median(complete)) if complete else max((row.image.width for row in rows if row.bars),default=1)
    for row in rows:
        if row.bars and row.bars < target:
            row.width_fraction=min(1,row.image.width/reference)
    return rows,notes
