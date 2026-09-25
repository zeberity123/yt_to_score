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


def system_groups(gray, notation):
    if notation == 'guitar':
        return staffs(gray,6)
    ordinary = staffs(gray)
    if notation == 'bass':
        tabs = staffs(gray, 4)
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
