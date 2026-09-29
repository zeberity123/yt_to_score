"""Deterministic vector PDF rendering. No model-generated drawing code is run."""
import io
import math
import os
import threading
import xml.etree.ElementTree as ET
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.pdfbase.pdfmetrics import stringWidth

from .contracts import printed_slots, is_grace

W, H = A4
LEFT, RIGHT = 49, W - 36
RENDER_LOCK = threading.RLock()


def text_font(text, bold=False):
    if all(ord(c) < 256 for c in text):
        return 'Helvetica-Bold' if bold else 'Helvetica'
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    name = 'ScoreUnicodeBold' if bold else 'ScoreUnicode'
    if name not in pdfmetrics.getRegisteredFontNames():
        directory = Path(os.environ.get('WINDIR', 'C:/Windows'))/'Fonts'
        candidates = ['malgunbd.ttf', 'malgun.ttf', 'arialuni.ttf', 'segoeuib.ttf'] if bold else ['malgun.ttf', 'arialuni.ttf', 'segoeui.ttf']
        for filename in candidates:
            if (directory/filename).exists():
                pdfmetrics.registerFont(TTFont(name, str(directory/filename)))
                break
        else:
            from reportlab.pdfbase.cidfonts import UnicodeCIDFont
            fallback = 'HeiseiKakuGo-W5'
            if fallback not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(UnicodeCIDFont(fallback))
            return fallback
    return name


def curve(c, x0, y0, x1, y1, rise=7):
    p = c.beginPath()
    p.moveTo(x0, y0)
    p.curveTo(x0 + (x1-x0)*.3, y0+rise, x0+(x1-x0)*.7, y1+rise, x1, y1)
    c.setLineWidth(.65)
    c.drawPath(p)


def rest(c, x, y, duration):
    c.setFillColorRGB(0, 0, 0)
    if duration >= 2:
        yy = y-10 if duration >= 4 else y-20
        c.rect(x-4, yy-(4 if duration >= 4 else 0), 8, 4, stroke=0, fill=1)
        c.setLineWidth(.45)
        c.line(x-7, yy, x+7, yy)
    elif duration >= 1:
        yy = y-15
        p = c.beginPath()
        p.moveTo(x-2, yy+11)
        for xx, dy in [(3, 5), (-.7, 1), (3, -5), (-.2, -3)]:
            p.lineTo(x+xx, yy+dy)
        p.curveTo(x-4, yy-1, x-4, yy-6, x, yy-10)
        p.curveTo(x-7, yy-7, x-6, yy, x-1, yy-1)
        p.lineTo(x-4, yy+4)
        p.lineTo(x, yy+8)
        p.close()
        c.drawPath(p, stroke=0, fill=1)
    else:
        yy = y-14
        count = flag_count(duration)
        c.setLineWidth(.85)
        c.line(x+3, yy+5, x-1, yy-9)
        for j in range(count):
            c.circle(x-j, yy+4-j*5, 1.8, stroke=0, fill=1)
            c.line(x-j, yy+3-j*5, x+3-j, yy+5-j*5)
    if duration in (3, 1.5, .75, .375):
        c.circle(x+7, y-15, 1, stroke=0, fill=1)


def flag(c, x, y, count):
    for n in range(count):
        p = c.beginPath()
        yy = y+n*4
        p.moveTo(x, yy)
        p.curveTo(x+9, yy+5, x+9, yy+11, x+3, yy+15)
        p.curveTo(x+6, yy+9, x+4, yy+7, x, yy+5)
        p.close()
        c.drawPath(p, stroke=0, fill=1)


def flag_count(duration):
    return {'eighth': 1, '16th': 2, '32nd': 3, '64th': 4}.get(rhythm(duration)[0], 0)


def label(bar):
    nums = bar['source_numbers']
    return str(nums[0]) if len(nums) == 1 else f'{nums[0]}–{nums[-1]}'


def page_header(c, layout, meta, page, pages):
    c.setFillColorRGB(0, 0, 0)
    if page == 0 or not layout['title_first_page_only']:
        font = text_font(layout['title'], True)
        title_width = stringWidth(layout['title'], font, 18)
        c.setFont(font, min(18, 18*(RIGHT-90)/max(title_width, 1)))
        c.drawString(36, H-42, layout['title'])
    if layout['subtitle']:
        c.setFont(text_font(layout['subtitle']), 8)
        c.drawString(36, H-59, layout['subtitle'])
    if layout['show_metadata']:
        meter = '/'.join(map(str, meta['meter']))
        c.setFont('Helvetica', 8)
        info = layout.get('song_info') or f"{meter} | Quarter note = {meta['bpm']:g} | {meta['instrument'].title()}"
        c.setFont(text_font(info), 8)
        for index, line in enumerate(info.splitlines()[:3]):
            c.drawString(36, H-74-index*10, line)
    if layout['page_numbers']:
        c.setFont('Helvetica', 8)
        c.drawRightString(RIGHT, H-42, f'{page+1} / {pages}')
    if layout['footer']:
        c.setFont(text_font(layout['footer']), 6.5)
        lines = layout['footer'].splitlines()[:4]
        for index, line in enumerate(lines):
            c.drawString(36, 25+(len(lines)-1-index)*9, line)


def tab_points(events, x, width):
    def event_width(e):
        if not e['notes']:
            return 7
        return max(stringWidth(f"({n['fret']})" if 'ghost' in n['marks'] or 'tie-stop' in n['marks'] else n['fret'],
                               'Helvetica' if 'ghost' in n['marks'] or 'tie-stop' in n['marks'] else 'Helvetica-Bold',
                               9.2 if 'ghost' in n['marks'] or 'tie-stop' in n['marks'] else 10.2)
                   for n in e['notes'])
    minima = [(event_width(a)+event_width(b))/2+2.2 for a, b in zip(events, events[1:])]
    if sum(minima) > width-25:
        raise ValueError('A dense TAB bar will not fit cleanly. Reduce bars per line.')
    weights = [math.sqrt(e['duration']) for e in events[:-1]]
    spare = max(0, width-28-sum(minima))
    points = []
    px = x+14
    for i, e in enumerate(events):
        points.append((px, e))
        if i < len(minima):
            px += minima[i] + spare*weights[i]/sum(weights)
    return points


def quarter_glyph(c, x, y):
    """A small quarter note drawn with paths, so no text font needs the ♩ glyph."""
    c.setFillColorRGB(0, 0, 0)
    c.ellipse(x-2.6, y-1.9, x+2.6, y+1.9, stroke=0, fill=1)
    c.setLineWidth(.8)
    c.line(x+2.3, y, x+2.3, y+9)


def bar_marks(c, bar, x, y):
    """Boxed rehearsal label and metronome mark printed once above the bar."""
    px = x+3
    if bar.get('rehearsal'):
        c.setFont('Helvetica-Bold', 7.5)
        width = stringWidth(bar['rehearsal'], 'Helvetica-Bold', 7.5)+5
        c.setStrokeColorRGB(0, 0, 0)
        c.setLineWidth(.6)
        c.rect(px, y+30, width, 10, stroke=1, fill=0)
        c.setFillColorRGB(0, 0, 0)
        c.drawString(px+2.5, y+32.6, bar['rehearsal'])
        px += width+5
    if bar.get('tempo_bpm'):
        quarter_glyph(c, px+3, y+32)
        c.setFont('Helvetica', 7.5)
        c.drawString(px+8, y+32, f" = {int(bar['tempo_bpm'])}")


def tab_bar(c, bar, x, y, width, strings, first, last, printed_tempo=0):
    c.setFillColorRGB(.23, .23, .23)
    c.setFont('Helvetica', 7)
    c.drawString(x+3, y+23, label(bar))
    if bar.get('tempo_bpm') == printed_tempo:
        bar = {**bar, 'tempo_bpm': 0}
    bar_marks(c, bar, x, y)
    bottom = y-(strings-1)*10
    if len(bar['source_numbers']) > 1:
        c.setFillColorRGB(0, 0, 0)
        cy = (y+bottom)/2
        c.setLineWidth(3)
        c.line(x+width*.27, cy, x+width*.73, cy)
        c.setLineWidth(.7)
        for xx in (x+width*.27, x+width*.73):
            c.line(xx, cy-5, xx, cy+5)
        c.setFont('Helvetica-Bold', 12)
        c.drawCentredString(x+width/2, y+10, str(len(bar['source_numbers'])))
        return
    events = sorted(bar['events'], key=lambda e: e['onset'])
    if len({e['voice'] for e in events}) > 1:
        raise ValueError(f"Bar {bar['number']}: independent TAB voices need manual review before rendering.")
    points = tab_points(events, x, width)
    beam_y = bottom-24
    for index, (px, e) in enumerate(points):
        d = e['duration']
        if not e['notes']:
            rest(c, x+width/2 if d >= 4 else px, y, d)
            continue
        for n in e['notes']:
            ny = y-(n['string']-1)*10
            marks = n['marks'].split()
            text = f"({n['fret']})" if 'ghost' in marks or 'tie-stop' in marks else n['fret']
            size = 9.2 if '(' in text else 10.2
            fw = stringWidth(text, 'Helvetica-Bold', size)
            c.setFillColorRGB(1, 1, 1)
            c.rect(px-fw/2-.7, ny-5, fw+1.4, 10, stroke=0, fill=1)
            c.setFillColorRGB(0, 0, 0)
            c.setFont('Helvetica-Bold', size)
            c.drawCentredString(px, ny-3.4, text)
            if d >= 2 and '(' not in text:
                c.setLineWidth(.65)
                c.ellipse(px-fw/2-2, ny-6, px+fw/2+2, ny+6)
            for mark, symbol in [('slap', 'S'), ('pop', 'P')]:
                if mark in marks:
                    c.setFont('Helvetica-Bold', 6.2)
                    c.drawCentredString(px, y+12, symbol)
            if 'slide-in' in marks:
                c.setLineWidth(.7)
                c.line(px-fw/2-7, ny-4, px-fw/2-1.8, ny+2)
            if 'slide-up' in marks or 'slide-down' in marks:
                c.setLineWidth(.7)
                c.line(px+fw/2+1.5, ny+2, px+fw/2+7, ny+(7 if 'slide-up' in marks else -4))
            nx = points[index+1][0]-4 if index+1 < len(points) else x+width-2
            if 'hammer-start' in marks or 'pull-start' in marks:
                curve(c, px+3, ny+6, nx, ny+6, 6)
                c.setFont('Helvetica', 5.8)
                c.drawCentredString((px+nx)/2, ny+13, 'H' if 'hammer-start' in marks else 'P')
            if 'tie-start' in marks:
                curve(c, px+5, ny+5, nx if last or index+1 < len(points) else x+width+9, ny+5, 6)
            if 'tie-stop' in marks and index == 0 and first:
                curve(c, x+1, ny+5, px-5, ny+5, 4)
            if 'vibrato' in marks:
                p = c.beginPath()
                p.moveTo(px, y+35)
                for j in range(1, max(2, int((nx-px)*2))):
                    xx = px+j*.5
                    p.lineTo(xx, y+35+1.3*math.sin((xx-px)*1.7))
                c.setLineWidth(.55)
                c.drawPath(p)
        if d < 4:
            c.setLineWidth(.65)
            c.line(px, bottom-7, px, beam_y)
        if d in (3, 1.5, .75, .375):
            c.circle(px+3.1, beam_y+1.2, 1, stroke=0, fill=1)
        if e['marks']:
            c.setFont('Helvetica', 6)
            c.drawCentredString(px, y+36, e['marks'])
    groups, group = [], []
    for point in points:
        e = point[1]
        eligible = e['notes'] and e['duration'] < 1
        if not eligible or (group and int(e['onset']+1e-6) != int(group[0][1]['onset']+1e-6)):
            if group:
                groups.append(group)
            group = []
        if eligible:
            group.append(point)
    if group:
        groups.append(group)
    for group in groups:
        levels = [flag_count(e['duration']) for _, e in group]
        if len(group) == 1:
            flag(c, group[0][0], beam_y, levels[0])
            continue
        c.setLineWidth(2.3)
        c.line(group[0][0], beam_y, group[-1][0], beam_y)
        if all(rhythm(e['duration'])[2] for _, e in group):
            c.setFont('Helvetica', 6)
            c.drawCentredString((group[0][0]+group[-1][0])/2, beam_y-10, '3')
        for level in range(2, max(levels)+1):
            for i, (px, _) in enumerate(group):
                if levels[i] < level:
                    continue
                yy = beam_y+4*(level-1)
                if i+1 < len(group) and levels[i+1] >= level:
                    c.line(px, yy, group[i+1][0], yy)
                elif i == 0 or levels[i-1] < level:
                    c.line(px, yy, px+(-4 if i else 4), yy)


def render_tab(score, layout, output):
    rows = printed_slots(score, layout)
    strings = score['meta']['strings']
    if not 4 <= strings <= 7:
        raise ValueError('TAB engraving supports 4–7 strings.')
    height = 110+(strings-4)*10
    per_page = int((H-145)//height)
    pages = math.ceil(len(rows)/per_page)
    c = canvas.Canvas(str(output), pagesize=(W, H), pageCompression=1)
    c.setTitle(layout['title'])
    width = (RIGHT-LEFT)/(layout['bars_per_line'] or max(map(len, rows), default=4))
    printed_tempo = 0
    for page in range(pages):
        page_header(c, layout, score['meta'], page, pages)
        for r, row in enumerate(rows[page*per_page:(page+1)*per_page]):
            y = H-127-r*height
            c.setFillColorRGB(.2, .2, .2)
            c.setFont('Helvetica-Bold', 6.5)
            for j, letter in enumerate('TAB'):
                c.drawRightString(LEFT-6, y-j*10-7, letter)
            c.setStrokeColorRGB(.45, .45, .45)
            c.setLineWidth(.35)
            for j in range(strings):
                c.line(LEFT, y-j*10, LEFT+len(row)*width, y-j*10)
            c.setStrokeColorRGB(0, 0, 0)
            c.setLineWidth(.6)
            for j in range(len(row)+1):
                c.line(LEFT+j*width, y, LEFT+j*width, y-(strings-1)*10)
            for j, bar in enumerate(row):
                tab_bar(c, bar, LEFT+j*width, y, width, strings, j == 0, j == len(row)-1, printed_tempo)
                printed_tempo = bar.get('tempo_bpm') or printed_tempo
        c.showPage()
    c.save()


def el(parent, name, text=None, **attrs):
    node = ET.SubElement(parent, name, {key: str(value) for key, value in attrs.items()})
    if text is not None:
        node.text = str(text)
    return node


def rhythm(duration):
    types = {16: 'long', 8: 'breve', 4: 'whole', 2: 'half', 1: 'quarter',
             .5: 'eighth', .25: '16th', .125: '32nd', .0625: '64th'}
    for dots, factor in ((0, 1), (1, 1.5), (2, 1.75)):
        for base, name in types.items():
            if abs(duration-base*factor) < .0001:
                return name, dots, False
    for base, name in types.items():
        if abs(duration-base*2/3) < .001:
            return name, 0, True
    raise ValueError(f'Unsupported rhythmic duration {duration}; review this bar.')


def beam_groups(events, meter):
    beat = 1.5 if meter[1] == 8 and meter[0] > 3 and meter[0] % 3 == 0 else 1.
    groups, group = [], []
    for index, event in enumerate(events):
        eligible = event['notes'] and 0 < event['duration'] < 1
        if not eligible or (group and int((event['onset']+.001)/beat) != int((events[group[0]]['onset']+.001)/beat)):
            if group:
                groups.append(group)
            group = []
        if eligible:
            group.append(index)
    if group:
        groups.append(group)
    result = {}
    for group in groups:
        if len(group) < 2:
            continue
        levels = [{'eighth': 1, '16th': 2, '32nd': 3, '64th': 4}.get(rhythm(events[i]['duration'])[0], 0) for i in group]
        for pos, index in enumerate(group):
            beams = []
            for level in range(1, levels[pos]+1):
                before = pos > 0 and levels[pos-1] >= level
                after = pos+1 < len(group) and levels[pos+1] >= level
                kind = 'continue' if before and after else 'end' if before else 'begin' if after else 'backward hook' if pos else 'forward hook'
                beams.append((level, kind))
            result[index] = beams
    return result


def musicxml(score, layout):
    rows = printed_slots(score, layout)
    piano = score['meta']['instrument'] == 'piano'
    root = ET.Element('score-partwise', version='4.0')
    part_list = el(root, 'part-list')
    part_info = el(part_list, 'score-part', id='P1')
    el(part_info, 'part-name', '')  # An empty name keeps the instrument label off every system.
    part = el(root, 'part', id='P1')
    previous_meter = None
    printed_tempo = 0
    for ri, row in enumerate(rows):
        for bi, bar in enumerate(row):
            measure = el(part, 'measure', number=label(bar), implicit='yes' if bar['pickup'] else 'no')
            if bi == 0:
                attrs = {'new-page': 'yes'} if ri and ri % (4 if piano else 7) == 0 else {'new-system': 'yes'}
                el(measure, 'print', **attrs)
            attr = el(measure, 'attributes')
            el(attr, 'divisions', 960)
            if previous_meter != bar['meter']:
                time = el(attr, 'time')
                el(time, 'beats', bar['meter'][0])
                el(time, 'beat-type', bar['meter'][1])
                previous_meter = bar['meter']
            if ri == 0 and bi == 0:
                if piano:
                    key = el(attr, 'key')
                    el(key, 'fifths', score['meta']['key_fifths'])
                    el(attr, 'staves', 2)
                for staff in range(1, 3 if piano else 2):
                    clef = el(attr, 'clef', number=str(staff))
                    el(clef, 'sign', ('G' if staff == 1 else 'F') if piano else 'percussion')
                    if piano:
                        el(clef, 'line', 2 if staff == 1 else 4)
            merged = len(bar['source_numbers'])
            if merged > 1:
                style = el(attr, 'measure-style')
                el(style, 'multiple-rest', merged, **{'use-symbols': 'no'})
            if bar.get('rehearsal'):
                direction = el(measure, 'direction', placement='above')
                el(el(direction, 'direction-type'), 'rehearsal', bar['rehearsal'])
                el(direction, 'staff', 1)
            tempo = int(bar.get('tempo_bpm') or 0)
            if tempo and tempo != printed_tempo:
                direction = el(measure, 'direction', placement='above')
                metronome = el(el(direction, 'direction-type'), 'metronome')
                el(metronome, 'beat-unit', 'quarter')
                el(metronome, 'per-minute', tempo)
                el(direction, 'staff', 1)
                printed_tempo = tempo
            voices = {}
            for event in bar['events']:
                voices.setdefault((event['staff'], event['voice']), []).append(event)
            previous_length = 0
            printed_words = set()  # The same direction in two voices prints once.
            for (staff, voice), events in sorted(voices.items()):
                if previous_length:
                    el(el(measure, 'backup'), 'duration', round(previous_length*960))
                cursor = 0
                ordered = sorted(events, key=lambda e: (e['onset'], not is_grace(e)))
                beams = beam_groups(ordered, bar['meter'])
                for ei, event in enumerate(ordered):
                    if event['onset'] > cursor+.001:
                        el(el(measure, 'forward'), 'duration', round((event['onset']-cursor)*960))
                    grace = is_grace(event)
                    if event['marks'] and not grace and (event['onset'], event['marks']) not in printed_words:
                        printed_words.add((event['onset'], event['marks']))
                        direction = el(measure, 'direction', placement='above')
                        direction_type = el(direction, 'direction-type')
                        if event['marks'] in ('ppp', 'pp', 'p', 'mp', 'mf', 'f', 'ff', 'fff', 'sfz'):
                            el(el(direction_type, 'dynamics'), event['marks'])
                        else:
                            el(direction_type, 'words', event['marks'])
                        el(direction, 'staff', staff)
                    duration = event['duration']
                    kind, dots, triplet = (next((name for name in ('64th', '32nd', '16th', 'eighth', 'quarter')
                                                  if name in event['marks'].lower()), 'eighth'), 0, False) if grace else rhythm(duration)
                    for ni, note in enumerate(event['notes'] or [None]):
                        node = el(measure, 'note')
                        if grace:
                            el(node, 'grace', slash='yes' if 'slash' in event['marks'].lower() else 'no')
                        if ni:
                            el(node, 'chord')
                        if note is None:
                            el(node, 'rest', **({'measure': 'yes'} if duration == bar['meter'][0]*4/bar['meter'][1] else {}))
                        elif piano:
                            pitch = el(node, 'pitch')
                            el(pitch, 'step', note['step'])
                            el(pitch, 'alter', note['alter'])
                            el(pitch, 'octave', note['octave'])
                        else:
                            pitch = el(node, 'unpitched')
                            el(pitch, 'display-step', note['step'] or 'C')
                            el(pitch, 'display-octave', note['octave'] or 5)
                        if not grace:
                            el(node, 'duration', round(duration*960))
                        marks = note['marks'].split() if note else []
                        for mark in ('stop', 'start'):
                            if 'tie-'+mark in marks:
                                el(node, 'tie', type=mark)
                        el(node, 'voice', (staff-1)*8+voice)
                        el(node, 'type', kind)
                        for _ in range(dots):
                            el(node, 'dot')
                        if triplet:
                            tm = el(node, 'time-modification')
                            el(tm, 'actual-notes', 3)
                            el(tm, 'normal-notes', 2)
                        if note and not piano and any(t in note['drum'].lower() for t in ('hat', 'cymbal', 'ride', 'crash')):
                            el(node, 'notehead', 'x', **({'parentheses': 'yes'} if 'ghost' in marks else {}))
                        elif note and ('ghost' in marks or 'muted' in marks):
                            el(node, 'notehead', 'x' if 'muted' in marks else 'normal', **({'parentheses': 'yes'} if 'ghost' in marks else {}))
                        el(node, 'staff', staff)
                        if ni == 0:
                            for level, kind in beams.get(ei, []):
                                el(node, 'beam', kind, number=level)
                        if marks:
                            notations = el(node, 'notations')
                            for mark in ('stop', 'start'):
                                if 'tie-'+mark in marks:
                                    el(notations, 'tied', type=mark)
                                if 'slur-'+mark in marks:
                                    el(notations, 'slur', type=mark, number='1')
                            articulation = [m for m in marks if m in ('staccato', 'accent', 'tenuto')]
                            if articulation:
                                art = el(notations, 'articulations')
                                for mark in articulation:
                                    el(art, mark)
                    cursor = max(cursor, event['onset']+duration)
                previous_length = cursor
            # MusicXML multiple-rest spans real following measures. Retain the
            # hidden source rests so the importer never swallows the next note bar.
            for source_number in bar['source_numbers'][1:]:
                hidden = el(part, 'measure', number=source_number)
                beats = bar['meter'][0]*4/bar['meter'][1]
                for staff in range(1, 3 if piano else 2):
                    if staff > 1:
                        el(el(hidden, 'backup'), 'duration', round(beats*960))
                    node = el(hidden, 'note')
                    el(node, 'rest', measure='yes')
                    el(node, 'duration', round(beats*960))
                    el(node, 'voice', (staff-1)*8+1)
                    el(node, 'staff', staff)
    return ET.tostring(root, encoding='unicode')


def render_staff(score, layout, output):
    import verovio
    from importlib.resources import files
    from svglib.svglib import svg2rlg
    from reportlab.graphics import renderPDF
    xml = musicxml(score, layout)
    Path(output).with_suffix('.musicxml').write_text(xml, encoding='utf-8')
    # Verovio's default resource path is thread-local. Each HTTP/worker thread
    # must initialize it before constructing a toolkit, including frozen builds.
    verovio.setDefaultResourcePath(str(files('verovio')/'data'))
    toolkit = verovio.toolkit()
    toolkit.setOptions({'inputFrom': 'musicxml', 'breaks': 'encoded', 'pageWidth': 2100,
                        'pageHeight': 2600, 'scale': 40, 'adjustPageHeight': True,
                        'header': 'none', 'footer': 'none', 'mnumInterval': 0,  # numbers at system starts only
                        'minLastJustification': 0})
    if not toolkit.loadData(xml):
        raise ValueError('The notation renderer could not read the score.')
    pages = toolkit.getPageCount()
    c = canvas.Canvas(str(output), pagesize=(W, H), pageCompression=1)
    c.setTitle(layout['title'])
    for page in range(pages):
        page_header(c, layout, score['meta'], page, pages)
        drawing = svg2rlg(io.BytesIO(toolkit.renderToSVG(page+1).encode('utf-8')))
        if drawing is None:
            raise ValueError('Could not convert engraved notation to PDF.')
        # svglib includes the outer SVG viewport and nested SVG whitespace in
        # width/height. Fit the actual notation bounds, not that empty viewport.
        xmin, ymin, xmax, ymax = drawing.getBounds()
        scale = min((RIGHT-LEFT)/max(xmax-xmin, 1), (H-155)/max(ymax-ymin, 1))
        drawing.scale(scale, scale)
        renderPDF.draw(drawing, c, LEFT-xmin*scale, H-105-ymax*scale)
        c.showPage()
    c.save()


def render(score, layout, output):
    global W, H, LEFT, RIGHT
    from reportlab.lib import pagesizes
    with RENDER_LOCK:
        previous = W, H, LEFT, RIGHT
        try:
            settings = score.get('page_settings', {})
            W, H = getattr(pagesizes, settings.get('paper', 'A4').upper(), A4)
            LEFT = max(36, float(settings.get('left', 12))*72/25.4+13)
            RIGHT = W-max(20, float(settings.get('right', 12))*72/25.4)
            Path(output).parent.mkdir(parents=True, exist_ok=True)
            if score['meta']['instrument'] == 'chord':
                from .lead import draw_lead
                c = canvas.Canvas(str(output), pagesize=(W, H), pageCompression=1)
                c.setTitle(layout['title'])
                draw_lead(c, score, layout, page_header, W, H, LEFT, RIGHT)
                c.save()
            elif score['meta']['instrument'] in ('bass', 'guitar'):
                render_tab(score, layout, output)
            else:
                render_staff(score, layout, output)
        finally:
            W, H, LEFT, RIGHT = previous
