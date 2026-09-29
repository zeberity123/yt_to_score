"""Read small measure labels and recover moving, white-on-video bass TAB.

Only consecutive, independently recognized labels establish measure identities.
The music itself remains captured pixels; it is never synthesized from OCR.
"""
from functools import lru_cache
from pathlib import Path
import uuid

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .vision import runs, staffs, clean_tab


def _glyph(mask):
    ys, xs = np.where(mask)
    if not len(xs):
        return None
    crop = mask[ys.min():ys.max()+1, xs.min():xs.max()+1].astype(np.float32)
    return cv2.resize(crop, (16, 24), interpolation=cv2.INTER_AREA)


@lru_cache(maxsize=1)
def _digits():
    fonts = [ImageFont.load_default(size=28)]
    # Windows' standard fonts are optional; no OCR service or model download.
    for name in ('arial.ttf', 'segoeui.ttf', 'calibri.ttf'):
        try:
            fonts.append(ImageFont.truetype(name, 28))
        except OSError:
            pass
    templates = []
    for font in fonts:
        for number in range(10):
            image = Image.new('L', (50, 50))
            ImageDraw.Draw(image).text((5, 0), str(number), font=font, fill=255)
            templates.append((number, _glyph(np.array(image) > 100)))
    return np.array([n for n,_ in templates]), np.stack([t for _,t in templates])


def read_number(gray, x, first, spacing):
    """Return a confident centered label immediately above a barline, or None."""
    radius = round(spacing*1.35)
    left, right = max(0, x-radius), min(gray.shape[1], x+radius+1)
    top, bottom = max(0, round(first-spacing*1.15)), max(0, round(first-spacing*.18))
    roi = gray[top:bottom, left:right]
    if min(roi.shape, default=0) < 8:
        return None
    background = cv2.morphologyEx(roi, cv2.MORPH_OPEN, np.ones((13, 13), np.uint8))
    mask = ((roi.astype(int)-background > 14) & (roi > 85)).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    characters = []
    for label in range(1, count):
        xx, yy, w, h, area = stats[label]
        if not (spacing*.42 <= h <= spacing*.95 and 1 <= w <= spacing*.75 and area >= 9):
            continue
        sample = _glyph(labels == label)
        numbers,templates = _digits()
        errors = np.mean(np.abs(templates-sample),axis=(1,2))
        scores = np.ones(10)
        np.minimum.at(scores,numbers,errors)
        ordered = sorted((error, number) for number,error in enumerate(scores))
        if ordered[0][0] > .29 or ordered[1][0]-ordered[0][0] < .025:
            continue
        characters.append((xx, xx+w, yy, h, ordered[0][1], ordered[0][0]))
    characters.sort()
    # Group nearby digits. Background fragments outside the centered label do
    # not turn a valid single digit into a spurious multi-digit bar number.
    groups = []
    for character in characters:
        if (groups and character[0]-groups[-1][-1][1] < spacing*.45
                and abs(character[2]-groups[-1][-1][2]) < spacing*.2):
            groups[-1].append(character)
        else:
            groups.append([character])
    for group in groups:
        center = left+(group[0][0]+group[-1][1])/2
        if len(group) <= 3 and abs(center-x) < spacing*.20:
            number = int(''.join(str(c[4]) for c in group))
            if 0 < number < 1000:
                return number
    return None


def _bar_candidates(frame, group):
    first, last, spacing = group
    light = frame.min(axis=2) if frame.ndim == 3 else frame
    vertical = cv2.morphologyEx(light, cv2.MORPH_TOPHAT, np.ones((1, 15), np.uint8))
    band = (vertical[first+3:last-2] > 10) & (light[first+3:last-2] > 140)
    if not len(band):
        return light, [], set()
    support=(band.mean(axis=0)>.55)&(band[:5].mean(axis=0)>.6)&(band[-5:].mean(axis=0)>.6)
    xs = [round(run.mean()) for run in runs(np.flatnonzero(support))]
    doubles=set()
    merged=[]
    for x in xs:
        if merged and x-merged[-1]<spacing*.75:
            doubles.add(merged[-1])
        else:
            merged.append(x)
    return light,merged,doubles


def numbered_boundaries(frame, group, widths=None, seen=(), detection=None):
    """Measure boundaries supported by vertical contrast and sequential labels."""
    first,last,spacing=group
    light,xs,doubles=detection if detection is not None else _bar_candidates(frame,group)
    labels = [(x, read_number(light, x, first, spacing)) for x in xs]
    widths = widths or {}
    known = [(i, x, number) for i, (x, number) in enumerate(labels) if number is not None]
    verified = {}
    added = []
    for (i, x, n), (j, xx, nn) in zip(known, known[1:]):
        # A missing or extra vertical boundary must not silently renumber bars.
        if nn-n == j-i and 0 < j-i <= 3:
            for offset in range(j-i+1):
                verified[i+offset] = n+offset
        elif 1 <= j-i < nn-n <= 3:
            sizes = [widths.get(number) for number in range(n,nn)]
            # A bright background can erase a boundary entirely. Two readable
            # labels and previously measured widths locate it without counting
            # the merged span as one bar. At most one width may be unknown.
            if sum(size is None for size in sizes) > 1:
                continue
            remainder = xx-x-sum(size for size in sizes if size is not None)
            if None in sizes:
                if not spacing*3 < remainder < frame.shape[1]*.65:
                    continue
                sizes[sizes.index(None)] = remainder
            if abs(sum(sizes)-(xx-x)) > max(4,(xx-x)*.02):
                continue
            position=x
            inferred=[]
            for number,size in zip(range(n,nn),sizes):
                inferred.append((round(position),number))
                position+=size
            inferred.append((xx,nn))
            if all(any(abs(bx-cx)<4 for cx,_ in inferred) for bx,_ in labels[i:j+1]):
                added.extend(inferred)
    # Reuse established measure widths to recognize a fleeting clean position
    # with only one legible label. Never blindly number an unlabelled neighbor:
    # there may be another barline hidden between the two visible ones.
    for i,x,n in known:
        for j,number in ((i-1,n-1),(i+1,n+1)):
            bar_number=min(n,number)
            if 0 <= j < len(labels) and bar_number in widths and labels[j][1] in (None,number):
                if abs(abs(labels[j][0]-x)-widths[bar_number]) <= max(4,widths[bar_number]*.02):
                    verified[i]=n
                    verified[j]=number
    for i,n in list(verified.items()):
        for j,number in ((i-1,n-1),(i+1,n+1)):
            if 0 <= j < len(labels) and labels[j][1] is None:
                if number in seen or (j==i+1 and labels[j][0] in doubles):
                    verified.setdefault(j,number)
    # Engravers commonly omit the initial "1". Accept the opening measure only
    # when the first boundary is the actual left end of at least two string
    # rules, followed by a verified measure 2. A clipped continuation fails this.
    if verified.get(1)==2 and labels[0][1] is None and labels[0][0]<frame.shape[1]*.2:
        thin=cv2.morphologyEx(light,cv2.MORPH_TOPHAT,np.ones((7,1),np.uint8))
        starts=0
        for y in np.linspace(first,last,4).round().astype(int):
            row=(thin[max(0,y-1):y+2]>8).any(axis=0).astype(np.uint8)
            row=cv2.morphologyEx(row.reshape(1,-1),cv2.MORPH_CLOSE,np.ones((1,7),np.uint8)).ravel()
            long=[run for run in runs(np.flatnonzero(row)) if len(run)>spacing*3]
            if long and abs(int(long[0][0])-labels[0][0])<spacing*.3:
                starts+=1
        if starts>=2:
            verified[0]=1
    result={x:verified.get(i) for i,(x,_) in enumerate(labels)}
    for x,n in added:
        nearest=min(result,key=lambda xx:abs(xx-x))
        result[nearest if abs(nearest-x)<4 else x]=n
    for x,n in list(result.items()):
        if n is None:
            continue
        for number,position in ((n+1,x+widths.get(n,0)), (n-1,x-widths.get(n-1,0))):
            if position == x or not 0 <= position < frame.shape[1] or number < 1:
                continue
            nearest=min(result,key=lambda xx:abs(xx-position))
            if abs(nearest-position)<4:
                if result[nearest] in (None,number):
                    result[nearest]=number
            elif not any(min(x,position)<xx<max(x,position) for xx in result):
                result[round(position)]=number
    return sorted(result.items()) if verified or added else []


def overlay_group(frame):
    """Restrict recovery to one white-on-video four-string system."""
    if frame.ndim != 3 or np.mean(frame > 200) > .55:
        return None
    gray = clean_tab(frame, 4)
    groups = staffs(gray, 4)
    if len(groups) != 1 or staffs(gray, 5):
        return None
    return groups[0]


def is_numbered_video(path, region, start, end, cancel=None):
    from .video import preview, check_cancel
    readings = []
    for fraction in (.1, .3, .6):
        check_cancel(cancel)
        frame = region.crop(preview(path, start+(end-start)*fraction))
        group = overlay_group(frame)
        if group is None:
            continue
        numbers = [n for _, n in numbered_boundaries(frame, group) if n is not None]
        if len(numbers) >= 2:
            readings.append(min(numbers))
    return len(readings) >= 2 and max(readings) > min(readings)


def _clean_overlay(frame, group):
    # Polarity is fixed for the whole video, never re-selected from a bright bar.
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    contrast = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, np.ones((15,15),np.uint8))
    bright, dark = frame.max(axis=2), frame.min(axis=2)
    # Antialiased white strokes inherit color from the footage underneath.
    # A narrow neutral-color cutoff would erase real thin stems and digits.
    ink = (contrast > 22) & (dark > 170) & (bright.astype(int)-dark < 45)
    result = np.where(ink, 0, 255).astype(np.uint8)
    first,last,_ = group
    for y in np.linspace(first,last,4).round().astype(int):
        result[y] = np.minimum(result[y],185)
    return result


def _patch_quality(background, spacing):
    step=max(12,round(spacing*1.5))
    rows=max(1,int(np.ceil(background.shape[0]/step)))
    cols=max(1,int(np.ceil(background.shape[1]/step)))
    return cv2.resize(background.astype(np.float32),(cols,rows),interpolation=cv2.INTER_AREA)


class BarRecovery:
    """Align numbered bars, retain clear source patches, and reject transient ink."""
    def __init__(self):
        self.bars = {}
        self.highest = 0
        self.backward = False
        self.last_numbers = None
        self.seen = set()

    def observe(self, frame, group, time, detection=None):
        widths={n:max(variants,key=lambda v:v['count'])['width']-1 for n,variants in self.bars.items()
                if max(v['count'] for v in variants)>=2}
        bounds = numbered_boundaries(frame, group, widths,self.seen,detection)
        numbers = [n for _, n in bounds if n is not None]
        if not numbers:
            return
        # Repeated passages with a numbering reset must stay in performance
        # order. Decline the specialized path instead of globally deduplicating.
        if self.last_numbers and max(numbers) < min(self.last_numbers)-1:
            self.backward = True
        self.last_numbers = numbers
        self.seen.update(numbers)
        self.highest = max(self.highest, max(numbers))
        first,last,spacing = group
        top, bottom = max(0, round(first-spacing*1.5)), min(len(frame),round(last+spacing*3.3))
        gray = cv2.cvtColor(frame[top:bottom], cv2.COLOR_BGR2GRAY)
        clean = None
        for (left,n),(right,nn) in zip(bounds,bounds[1:]):
            if n is None or nn != n+1 or right-left < spacing*3:
                continue
            width = right-left+1
            variants = self.bars.setdefault(n, [])
            variant = next((v for v in variants if abs(v['width']-width) <= max(3,width*.02)),None)
            if variant is None:
                variant = {'width':width, 'count':0, 'time':time, 'first':first-top,
                           'spacing':spacing, 'image':None, 'quality':None, 'raw':None,
                           'clear':None, 'support':None, 'samples':set()}
                variants.append(variant)
            variant['count'] += 1
            raw = gray[:,left:right+1]
            # Score local background after removing thin white notation. A
            # bright object above the strings must not choose the source for
            # notes below them, as whole-column selection did.
            background = cv2.morphologyEx(raw,cv2.MORPH_OPEN,np.ones((15,15),np.uint8))
            background = cv2.resize(background,(variant['width'],background.shape[0]),interpolation=cv2.INTER_LINEAR)
            quality = _patch_quality(background,spacing)
            if clean is None:
                clean = _clean_overlay(frame,group)[top:bottom]
            bar = clean[:,left:right+1]
            bar = cv2.resize(bar,(variant['width'],bar.shape[0]),interpolation=cv2.INTER_NEAREST)
            color = cv2.resize(frame[top:bottom,left:right+1],(variant['width'],bar.shape[0]),interpolation=cv2.INTER_LINEAR)
            if variant['image'] is not None and variant['image'].shape != bar.shape:
                continue
            # Aligned notation stays put while video scenery moves. Count only
            # observations with locally dark background, where absence of white
            # notation is meaningful. Bright/occluded frames cannot vote it away.
            sample=round(time*5)
            if sample not in variant['samples']:
                visible=background<150
                support=cv2.dilate((bar<100).astype(np.uint8),np.ones((3,3),np.uint8))>0
                if variant['clear'] is None:
                    variant['clear']=np.zeros(bar.shape,np.uint16)
                    variant['support']=np.zeros(bar.shape,np.uint16)
                eligible=visible & (variant['clear']<60000)
                variant['clear']+=eligible
                variant['support']+=eligible & support
                variant['samples'].add(sample)
            if variant['image'] is None:
                variant['image'] = bar.copy()
                variant['raw'] = color.copy()
                variant['quality'] = quality.copy()
            elif variant['image'].shape == bar.shape:
                # Keep actual source patches, with the same geometry for Off.
                # Never draw or infer a musical symbol hidden in every source.
                ys=np.linspace(0,bar.shape[0],quality.shape[0]+1).astype(int)
                xs=np.linspace(0,bar.shape[1],quality.shape[1]+1).astype(int)
                for row,col in np.argwhere(quality+8 < variant['quality']):
                    area=np.s_[ys[row]:ys[row+1],xs[col]:xs[col+1]]
                    variant['image'][area]=bar[area]
                    variant['raw'][area]=color[area]
                    variant['quality'][row,col]=quality[row,col]

    def resolved(self):
        result={}
        for n,variants in self.bars.items():
            value=dict(max(variants,key=lambda v:v['count']))
            image=value['image'].copy()
            transient=(value['clear']>=3)&(value['support']<value['clear']*.3)&(image<100)
            image[transient]=255
            value['image']=image
            result[n]=value
        return result


def extract_numbered(path, destination, title, source, region, start, end, progress, cancel):
    from .extract import Extraction, ScoreLine
    from .video import frames, check_cancel
    # The intermediate scrolling position can last exactly one source frame.
    cap = cv2.VideoCapture(str(path))
    try:
        fps = cap.get(cv2.CAP_PROP_FPS)
    finally:
        cap.release()
    interval = 1/min(60,max(10,fps or 30))
    recovery = BarRecovery()
    group = None
    positions=[]
    last_sample=-float('inf')
    iterator = frames(path,interval,start,end,cancel,dense=True)
    try:
        for time,frame in iterator:
            check_cancel(cancel)
            crop = region.crop(frame)
            if group is None:
                group = overlay_group(crop)
            if group is not None:
                detection=_bar_candidates(crop,group)
                current_positions=detection[1]
                stationary=(len(positions)==len(current_positions)
                            and all(abs(a-b)<=2 for a,b in zip(positions,current_positions)))
                # Check boundaries at source frame rate, but OCR and retain a
                # stationary view only a few times per second. Every changed
                # position still gets sampled, including a one-frame scroll.
                if not stationary or time-last_sample>=.35:
                    recovery.observe(crop,group,time,detection)
                    last_sample=time
                positions=current_positions
            if round((time-start)/interval) % 30 == 0:
                progress(f'Recovering numbered TAB bars: {len(recovery.bars)} found', .9*(time-start)/(end-start))
    finally:
        iterator.close()
    if recovery.backward:
        return None
    # Later views can establish widths that were unknowable in the opening
    # footage. Revisit the video sparsely with those anchors to close such gaps.
    recovery.last_numbers=None
    iterator=frames(path,.2,start,end,cancel)
    try:
        for time,frame in iterator:
            check_cancel(cancel)
            if group is not None:
                recovery.observe(region.crop(frame),group,time)
            if round((time-start)*2)%10==0:
                progress(f'Checking numbered TAB gaps: {len(recovery.bars)} found', .9+.1*(time-start)/(end-start))
    finally:
        iterator.close()
    bars = recovery.resolved()
    if recovery.backward or len(bars) < 8:
        return None
    numbers = sorted(bars)
    missing = [n for n in range(numbers[0],numbers[-1]+1) if n not in bars]
    if start==0 and numbers[0]<=8:
        missing=list(range(1,numbers[0]))+missing
    # Ambiguous numbering must not replace a usable ordinary extraction with a
    # small fragment. Sparse recovery is deliberately left to the normal path.
    if len(missing) > max(3,len(bars)*.08):
        return None
    directory = Path(destination)/('score_'+uuid.uuid4().hex[:10])
    directory.mkdir(parents=True)
    project = Extraction(directory,title,source or str(path),region,[],[],notation='bass')
    pending = []
    weak = []
    def flush():
        if not pending:
            return
        height = max(image.shape[0] for _,image in pending)
        image = np.full((height,sum(image.shape[1] for _,image in pending)),255,np.uint8)
        raw_image=np.zeros((*image.shape,3),np.uint8)
        boundaries=[0]
        x=0
        for number,part in pending:
            image[:len(part),x:x+part.shape[1]] = part
            raw_image[:len(part),x:x+part.shape[1]] = bars[number]['raw']
            x += part.shape[1]
            boundaries.append(x)
        name = f'line_{len(project.lines)+1:04d}.png'
        Image.fromarray(image).save(directory/name)
        raw_name=f'raw_{name}'
        Image.fromarray(cv2.cvtColor(raw_image,cv2.COLOR_BGR2RGB)).save(directory/raw_name)
        project.lines.append(ScoreLine(name,bars[pending[0][0]]['time'],len(project.lines)+1,
                                      source_path=name,crop=[0,0,1,1],original_path=name,original_crop=[0,0,1,1],
                                      raw_source_path=raw_name,bar_bounds=boundaries,
                                      bar_numbers=[n for n,_ in pending],
                                      bar_staff=[bars[pending[0][0]]['first'],bars[pending[0][0]]['spacing']]))
        pending.clear()
    previous = None
    for n in numbers:
        check_cancel(cancel)
        value=bars[n]
        if previous is not None and n != previous+1:
            flush()
        part=value['image'].copy()
        first,spacing=value['first'],value['spacing']
        # The original label straddles the cut. Move the recognized number to
        # the inside margin so joins do not leave half a digit on either side.
        label_top=max(0,round(first-spacing*1.15))
        label_bottom=max(0,round(first-spacing*.18))
        margin=round(spacing*1.35)
        part[label_top:label_bottom,:margin]=255
        part[label_top:label_bottom,-margin:]=255
        picture=Image.fromarray(part)
        ImageDraw.Draw(picture).text((4,label_top),str(n),fill=0,font=ImageFont.load_default(size=max(10,round(spacing*.7))))
        pending.append((n,np.array(picture)))
        if float(np.mean(value['quality'] > 150)) > .12:
            weak.append(n)
        previous=n
        if len(pending)==4:
            flush()
    flush()
    project.warnings.append(f'Recovered {len(bars)} numbered TAB bars from their clearest observed positions; joined in groups of four. Review before printing.')
    if missing:
        project.warnings.append('Could not recover numbered bars: '+', '.join(map(str,missing))+'. Use Manual capture to add them.')
    if weak:
        project.warnings.append('Background may still obscure parts of bars: '+', '.join(map(str,weak))+'. Review these bars against the video.')
    append_numbered_ending(project,path,numbers[-1],max(start,end-12),end,cancel)
    project.warnings.append('Moving background fragments were filtered using repeated observations. Original shows the source-color slices used for each assembled bar. Check faint notes and obscured areas against the video.')
    project.save()
    progress(f'Ready: {len(project.lines)} lines from {len(bars)} numbered bars',1)
    return project


def append_numbered_ending(project,path,last_number,start,end,cancel=None):
    """Preserve an unresolved ending through its visible closing double bar.

    This stays an explicitly unconfirmed capture, not guessed measure numbers.
    """
    from .extract import ScoreLine
    from .video import frames, check_cancel
    best=None
    iterator=frames(path,.1,start,end,cancel)
    group=None
    try:
        for time,frame in iterator:
            check_cancel(cancel)
            crop=project.region.crop(frame)
            if group is None:
                group=overlay_group(crop)
            if group is None:
                continue
            detection=_bar_candidates(crop,group)
            if not detection[2]:
                continue
            bounds=numbered_boundaries(crop,group,detection=detection)
            left=next((x for x,n in bounds if n==last_number+1),None)
            if left is None:
                continue
            right=max(detection[2])
            first,last,spacing=group
            if right-left<spacing*3:
                continue
            top,bottom=max(0,round(first-spacing*1.5)),min(len(crop),round(last+spacing*3.3))
            quality=float(np.mean(crop[top:bottom,left:right+1]))
            if best is None or quality<best[0]:
                best=(quality,time,frame.copy(),_clean_overlay(crop,group)[top:bottom,left:right+1],
                      (left,top,right+1,bottom))
    finally:
        iterator.close()
    if best is None:
        project.warnings.append('Check the video ending for partial or unreadable bars beyond the last recovered number.')
        return False
    _,time,frame,strip,bounds=best
    name=f'line_{len(project.lines)+1:04d}.png'
    source='ending_source.png'
    Image.fromarray(strip).save(project.directory/name)
    Image.fromarray(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB)).save(project.directory/source)
    h,w=frame.shape[:2]
    x,y=int(project.region.left*w),int(project.region.top*h)
    left,top,right,bottom=bounds
    crop=[(x+left)/w,(y+top)/h,(x+right)/w,(y+bottom)/h]
    project.lines.append(ScoreLine(name,time,len(project.lines)+1,source_path=source,
                                  crop=crop,original_path=name,original_crop=crop.copy(),raw_source_path=source))
    project.warnings.append(f'Ending from bar {last_number+1} kept as an unconfirmed capture through the closing barline. Review against the video.')
    return True
