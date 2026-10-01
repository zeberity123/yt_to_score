"""Instrument-aware grouping for bass notation/TAB and piano grand staffs."""
import cv2
import numpy as np

from .vision import Region, clean_score, clean_tab, staffs, signature, tab_signature, split_systems

NOTATIONS = ('staff', 'guitar', 'bass', 'piano')


def clean_notation(frame, notation):
    if notation == 'bass':
        if frame.ndim == 3:
            bright,dark=frame.max(axis=2),frame.min(axis=2)
            light=np.where((dark<50)&(bright.astype(int)-dark>65),dark,bright).astype(np.uint8)
        else:
            light=frame.copy()
        light[light>238]=255
        light_groups=staffs(light,4)
        on_paper=any(np.mean(light[first:last+1]>200)>.60 for first,last,_ in light_groups)
        gray=light if on_paper or np.mean(light>200)>.55 else clean_tab(frame,4)
    elif notation == 'guitar':
        gray = clean_tab(frame)
    else:
        gray = clean_score(frame)
    if frame.ndim == 3:
        # Remove thin saturated playback cursors, preserving colored noteheads.
        bright, dark = frame.max(axis=2), frame.min(axis=2)
        color = ((bright.astype(int)-dark > 80) & (bright > 160)).astype(np.uint8)
        count, labels, stats, _ = cv2.connectedComponentsWithStats(color)
        for label in range(1, count):
            x,y,w,h,area = stats[label]
            if h > max(35,frame.shape[0]*.12) and w < max(8,frame.shape[1]*.012) and h > w*8:
                gray[labels == label] = 255
    return gray


def _pair_tabs(tabs, ordinary):
    """Join each TAB with the staff printed directly above it; a lone TAB stays as it is."""
    result = []
    used = set()
    for tab in tabs:
        above = [(i,g) for i,g in enumerate(ordinary) if i not in used and g[1] < tab[0]
                 and tab[0]-g[1] < max(g[2],tab[2])*16]
        if above:
            i, staff = max(above,key=lambda item:item[1][0])
            # Only attach the immediately preceding staff, never across another TAB.
            if not any(staff[1] < other[0] < tab[0] for other in tabs):
                used.add(i)
                result.append((staff[0],tab[1],min(staff[2],tab[2])))
                continue
        result.append(tab)
    return sorted(result)


def _thin_rule(gray, y, spacing):
    """How many columns of row y carry a thin rule. Noteheads, beams and digits are thicker."""
    reach = max(2, int(min(4, spacing/2.5)))
    ink = gray < 235
    best = 0
    # The six-rule fit can sit a few pixels off the printed string; look around it.
    for row in range(int(y)-max(1, round(spacing*.2)), int(y)+max(1, round(spacing*.2))+1):
        if 0 <= row < len(gray):
            thin = ink[row] & ~ink[max(0, row-reach)] & ~ink[min(len(gray)-1, row+reach)]
            best = max(best, int(thin.sum()))
    return best


def guitar_groups(gray):
    """Six-string TAB systems, each joined with a five-line staff printed directly above it."""
    tabs, ordinary = staffs(gray, 6), staffs(gray)
    for tab in list(tabs):
        for staff in list(ordinary):
            # The same rules can read both ways: five of six strings look like a staff, and
            # a staff with a row of ledger notes one space away looks like six strings.
            if staff[0] < tab[0]-2 or staff[1] > tab[1]+2 or abs(staff[2]-tab[2]) > tab[2]*.2:
                continue
            extra = tab[1] if abs(staff[0]-tab[0]) <= abs(staff[1]-tab[1]) else tab[0]
            typical = np.median([_thin_rule(gray, y, tab[2]) for y in np.linspace(staff[0], staff[1], 5).round()])
            if _thin_rule(gray, extra, tab[2]) >= typical*.4:
                ordinary.remove(staff)  # a real sixth string, even where digits interrupt it
            else:
                tabs.remove(tab)  # the sixth row is noteheads on ledger lines: this is the staff
                break
    return _pair_tabs(tabs, ordinary)


def system_groups(gray, notation):
    if notation == 'guitar':
        return guitar_groups(gray)
    ordinary = staffs(gray)
    if notation == 'bass':
        # A faint fifth rule may disappear at the darker detection threshold.
        # Never let that four-rule subset compete with its complete staff.
        tabs = [tab for tab in staffs(gray, 4) if not any(
            tab[0] >= staff[0]-2 and tab[1] <= staff[1]+2
            for staff in ordinary)]
        return _pair_tabs(tabs, ordinary)
    # Piano: pair adjacent five-line staffs. An unusually close incomplete staff
    # at a scrolling page edge must not consume the next complete grand staff.
    result=[]
    index=0
    connected=[]
    for upper,lower in zip(ordinary,ordinary[1:]):
        gap=gray[upper[1]+2:lower[0]-1]
        connected.append(bool(len(gap) and np.any((gap<185).mean(axis=0)>.8)))
    while index+1 < len(ordinary):
        upper,lower=ordinary[index:index+2]
        spacing=min(upper[2],lower[2])
        gap=lower[0]-upper[1]
        linked=connected[index]
        if not any(connected):
            # For brace-only scores, compare the spacing to the next system.
            linked=index+2>=len(ordinary) or gap <= ordinary[index+2][0]-lower[1]
        if linked and .65 < upper[2]/lower[2] < 1.55 and spacing*1.5 < gap < spacing*22:
            result.append((upper[0],lower[1],spacing))
            index+=2
        else:
            index+=1
    return result


def split_notation(gray, notation, with_bounds=False):
    return split_systems(gray, with_bounds=with_bounds, groups=system_groups(gray,notation))


def follow_region(frame, region, notation):
    """Follow one complete system near the selected area; leave pages alone.

    Only a local band is inspected at the ordinary sampling rate. The original
    selection remains the anchor so transitions cannot accumulate crop drift.
    """
    h, w = frame.shape[:2]
    search = Region(max(0, region.left-.04), max(0, region.top-.16),
                    min(1, region.right+.04), min(1, region.bottom+.16))
    gray = clean_notation(search.crop(frame), notation)
    groups = system_groups(gray, notation) if notation in ('bass','piano','guitar') else staffs(gray, 5)
    sx, sy = int(search.left*w), int(search.top*h)
    inside = [g for g in groups if g[0]+sy >= region.top*h and g[1]+sy <= region.bottom*h]
    if len(inside) > 1 or not groups:
        return region
    center = (region.top+region.bottom)*h/2-sy
    candidates = [g for g in groups if g[1]+sy > region.top*h and g[0]+sy < region.bottom*h]
    if not candidates:
        return region
    first,last,spacing = min(candidates, key=lambda g: abs((g[0]+g[1])/2-center))
    top, bottom = max(0, int(first-spacing*5)), min(len(gray), int(last+spacing*5)+1)
    raw = search.crop(frame)
    panel_top = None
    if np.mean(raw[first:last+1] > 200) > .55:
        white = (raw.max(axis=2) > 200).mean(axis=1)
        smooth = cv2.blur(white.reshape(-1,1),(1,max(3,int(spacing*2)))).ravel()
        # On a white panel its edge bounds the annotations: section boxes and chord names
        # can sit well above a small staff. Without an edge nearby this is a page; keep
        # the fixed margin there.
        limit = max(0, int(first-spacing*14))
        edge = first
        while edge > limit and smooth[edge-1] > .70:
            edge -= 1
        top = edge if edge > limit else max(top, edge)
        panel_top = edge if edge > limit else None
        # The same below: a panel that ends just under the system must not let the moving
        # footage beneath it into the crop.
        limit = min(len(gray), int(last+spacing*14))
        edge = last
        while edge < limit-1 and smooth[edge+1] > .70:
            edge += 1
        if edge < limit-1 or limit == len(gray):
            bottom = edge+1
    # A neighboring staff can be incomplete as a system (e.g. the next TAB is
    # offscreen), but still tells us where this system's annotations must stop.
    neighbors = staffs(gray,5) + staffs(gray,4 if notation == 'bass' else 6)
    for a,b,s in neighbors:
        # Guitar strings, frets or shelves in the footage can pass for a tiny staff. Only
        # rules of a comparable size, inside the panel, are neighbouring systems.
        if not spacing*.6 <= s <= spacing*2.5 or (panel_top is not None and b < panel_top):
            continue
        if b < first-spacing:
            top = max(top, int((b+first)/2))
        if a > last+spacing:
            bottom = min(bottom, int((last+a)/2))
    # Use long rules, not the changing notes, to keep the horizontal crop stable.
    band = (gray[first:last+1] < 235).astype(np.uint8)
    horizontal = cv2.morphologyEx(band, cv2.MORPH_OPEN, np.ones((1,max(20,w//7)),np.uint8))
    cols = np.flatnonzero(horizontal.sum(axis=0) >= 3)
    left, right = 0, gray.shape[1]
    if len(cols):
        left = max(0,int(cols[0]-spacing*3))
        right = min(gray.shape[1],int(cols[-1]+spacing*2)+1)
        # Never narrower than the selected area: a short system keeps the scale of the
        # full-width ones when each line is later fitted to the page width.
        left = min(left, max(0, int(region.left*w)-sx))
        right = max(right, min(gray.shape[1], int(np.ceil(region.right*w))-sx))
    return Region((sx+left+.01)/w, (sy+top+.01)/h,
                  min(1,(sx+right+.01)/w), min(1,(sy+bottom+.01)/h))


def panel_moves(frames, region, notation):
    """True when the followed system's top edge wanders between sampled frames.

    A strip that resizes to each line's content needs following; a fixed crop would
    clip the taller lines or let footage into the shorter ones.
    """
    tops = []
    for frame in frames:
        followed = follow_region(frame, region, notation)
        # Only a white panel has an edge to follow; notation drawn over footage keeps its fixed area.
        if followed != region and np.mean(followed.crop(frame) > 200) > .55:
            tops.append(followed.top*frame.shape[0])
    return len(tops) >= 3 and max(tops)-min(tops) > max(8, frames[0].shape[0]*.015)


def system_fingerprint(gray, notation):
    groups=system_groups(gray,notation)
    if len(groups) != 1:
        return None
    width=1600 if notation == 'bass' and not staffs(gray) else 900
    scale=width/gray.shape[1]
    resized=cv2.resize(gray,(width,max(1,round(len(gray)*scale))),interpolation=cv2.INTER_AREA)
    target=np.full((round(600*width/900),width),255,np.uint8)
    offset=round(110*width/900)-round(groups[0][0]*scale)
    source_top,target_top=max(0,-offset),max(0,offset)
    length=min(len(resized)-source_top,len(target)-target_top)
    if length <= 0:return None
    target[target_top:target_top+length]=resized[source_top:source_top+length]
    return notation_signature(target, notation)


def notation_signature(gray, notation):
    # A standalone TAB panel has no pitched noteheads to preserve. Ignore its
    # moving playback box, while comparing both staffs in combined notation.
    if notation == 'bass' and not staffs(gray):
        comparison=gray.copy()
        groups=staffs(gray,4)
        if groups:
            # A title/tempo badge can disappear during an otherwise unchanged
            # panel. Keep nearby chords and rhythm marks in the comparison.
            comparison[:max(0,int(groups[0][0]-groups[0][2]*2))]=255
            comparison[min(len(gray),int(groups[-1][1]+groups[-1][2]*5)):]=255
        return tab_signature(comparison, 4)
    return signature(gray)


def detect_region(frame, notation, mode='auto'):
    if mode == 'page':return Region()
    h,w=frame.shape[:2]
    # Looking at top/bottom panels separately avoids choosing ink polarity from
    # the much larger performance video or piano-roll visualization.
    candidates=[]
    panels=[(0,h),(0,int(h*.48)),(int(h*.5),h)]
    if notation == 'guitar':panels.append((int(h*.7),h))
    for y0,y1 in panels:
        gray=clean_notation(frame[y0:y1],notation)
        groups=system_groups(gray,notation)
        for first,last,spacing in groups:
            candidates.append((first+y0,last+y0,spacing))
    unique=[]
    for group in sorted(candidates):
        if not any(abs(group[0]-other[0]) < max(3,group[2]) and abs(group[1]-other[1]) < group[2]*2 for other in unique):
            unique.append(group)
    if mode == 'bottom':unique=[g for g in unique if g[0] > h*.45]
    if not unique:return Region(0,.7,1,1) if mode=='bottom' else Region()
    # A page with multiple complete systems should retain all of them.
    if len(unique)>1 and np.mean(frame>200)>.65:return Region()
    first,last,spacing=max(unique,key=lambda g:g[1]-g[0])
    raw=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY)
    is_light=np.mean(raw[first:last+1]>200)>.55
    margin=(9 if notation == 'guitar' else 7) if is_light else 5
    top=max(0,int(first-spacing*margin))
    bottom=min(h,int(last+spacing*margin))
    if notation == 'bass' and not is_light and last-first < spacing*3.5:
        # Standalone white TAB: its labels sit just above the strings and its
        # rhythm stems below. Symmetric five-gap padding includes the instrument
        # and bright room behind it, overwhelming both comparison and cleanup.
        top=max(0,int(first-spacing*2.5))
        bottom=min(h,int(last+spacing*3.5))
    if is_light:
        # Stop at the edge of the white panel, including its annotations.
        white=(raw>200).mean(axis=1)
        # Staff rows themselves are mostly ink. Smooth over a few rule spacings
        # so a long horizontal rule cannot be mistaken for the panel boundary.
        smooth=cv2.blur(white.reshape(-1,1),(1,max(3,int(spacing*3)))).ravel()
        start,end=first,last
        while start>0 and smooth[start-1]>.65:start-=1
        while end<h-1 and smooth[end+1]>.65:end+=1
        top=max(top,start)
        bottom=min(bottom,end+1)
    return Region(0,top/h,1,bottom/h)
