"""Standalone vector TAB typesetter; no imports from the video-score app."""
import json
import math
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase.pdfmetrics import stringWidth
from transcription import bars, references, validate

ROOT=Path(__file__).resolve().parent
OUTPUT=ROOT/'Ado_independent_4_bars.pdf'
W,H=A4
LEFT,RIGHT=49,W-36
BW=(RIGHT-LEFT)/4
GAP=10
SIZE=10.2

def curve(c,x0,y0,x1,y1,rise=7):
    p=c.beginPath();p.moveTo(x0,y0)
    p.curveTo(x0+(x1-x0)*.30,y0+rise,x0+(x1-x0)*.70,y1+rise,x1,y1)
    c.setLineWidth(.65);c.drawPath(p)

def rest(c,x,y,duration):
    c.setFillColorRGB(0,0,0);c.setStrokeColorRGB(0,0,0)
    if duration>=2:
        yy=y-10 if duration==4 else y-20
        c.rect(x-4,yy-(4 if duration==4 else 0),8,4,stroke=0,fill=1)
        c.setLineWidth(.45);c.line(x-7,yy,x+7,yy)
    elif duration>=1:
        yy=y-15
        p=c.beginPath();p.moveTo(x-2,yy+11);p.lineTo(x+3,yy+5)
        p.lineTo(x-.7,yy+1);p.lineTo(x+3,yy-5);p.lineTo(x-.2,yy-3)
        p.curveTo(x-4,yy-1,x-4,yy-6,x,yy-10)
        p.curveTo(x-7,yy-7,x-6,yy,x-1,yy-1)
        p.lineTo(x-4,yy+4);p.lineTo(x,yy+8);p.close()
        c.drawPath(p,stroke=0,fill=1)
        if duration==1.5:c.circle(x+6,yy,1.1,stroke=0,fill=1)
    else:
        yy=y-14
        c.setLineWidth(.85);c.line(x+3,yy+5,x-1,yy-9)
        c.circle(x,yy+4,1.8,stroke=0,fill=1)
        c.line(x,yy+3,x+3,yy+5)
        if duration==.25:
            c.circle(x-1,yy-1,1.8,stroke=0,fill=1)
            c.line(x-1,yy-2,x+1.5,yy)

def flag(c,x,y,count):
    for n in range(count):
        p=c.beginPath();yy=y+n*4
        p.moveTo(x,yy);p.curveTo(x+9,yy+5,x+9,yy+11,x+3,yy+15)
        p.curveTo(x+6,yy+9,x+4,yy+7,x,yy+5);p.close()
        c.drawPath(p,stroke=0,fill=1)

def positions(events,x):
    def width(e):
        if e['string'] is None:return 7
        text=f"({e['fret']})" if 'c' in e['marks'] else e['fret']
        return stringWidth(text,'Helvetica' if 'c' in e['marks'] else 'Helvetica-Bold',SIZE-1 if 'c' in e['marks'] else SIZE)
    minimum=[(width(a)+width(b))/2+2.2+(3 if 'i' in b['marks'] or 'o' in a['marks'] else 0)
             for a,b in zip(events,events[1:])]
    weights=[math.sqrt(e['duration']) for e in events[:-1]]
    extra=max(0,BW-28-sum(minimum))
    assert sum(minimum)<=BW-26,(events,minimum)
    gaps=[m+extra*w/sum(weights) for m,w in zip(minimum,weights)]
    points=[];advance=0;onset=0
    for i,e in enumerate(events):
        points.append(dict(x=x+14+advance,onset=onset,event=e))
        advance+=gaps[i] if i<len(gaps) else 0;onset+=e['duration']
    return points

def render_bar(c,n,x,y):
    events=bars[n];points=positions(events,x)
    c.setFillColorRGB(.23,.23,.23);c.setFont('Helvetica',7)
    c.drawString(x+3,y+23,str(n))
    bottom=y-30;beam_y=bottom-24
    for point in points:
        e=point['event'];px=point['x'];d=e['duration'];marks=e['marks']
        if e['string'] is None:
            rest(c,x+BW/2 if d==4 else px,y,d);continue
        ny=y-'GDAE'.index(e['string'])*GAP
        fret=f"({e['fret']})" if 'c' in marks else e['fret']
        font='Helvetica' if 'c' in marks else 'Helvetica-Bold'
        size=SIZE-1 if 'c' in marks else SIZE
        fw=stringWidth(fret,font,size)
        c.setFillColorRGB(1,1,1);c.rect(px-fw/2-.7,ny-5,fw+1.4,10,stroke=0,fill=1)
        c.setFillColorRGB(0,0,0);c.setFont(font,size);c.drawCentredString(px,ny-3.4,fret)
        if d>=2 and 'c' not in marks:
            c.setLineWidth(.65);c.ellipse(px-fw/2-2,ny-6,px+fw/2+2,ny+6)
        c.setLineWidth(.65);c.line(px,bottom-7,px,beam_y)
        if d in (1.5,.75):c.circle(px+3.1,beam_y+1.2,1,stroke=0,fill=1)
        for mark in ('S','P'):
            if mark in marks:
                c.setFont('Helvetica-Bold',6.2);c.drawCentredString(px,y+12,mark)
        if 'i' in marks:
            c.setLineWidth(.7);c.line(px-fw/2-7,ny-4,px-fw/2-1.8,ny+2)
        if 'o' in marks or 'u' in marks:
            c.setLineWidth(.7);c.line(px+fw/2+1.5,ny+2,px+fw/2+7,ny+7 if 'u' in marks else ny-4)
    # Beam within beats; preserve syncopation by flagging isolated eighths.
    groups=[];group=[]
    for point in points:
        e=point['event'];eligible=e['string'] is not None and e['duration']<1
        if not eligible or (group and int(point['onset']+1e-6)!=int(group[0]['onset']+1e-6)):
            if group:groups.append(group)
            group=[]
        if eligible:group.append(point)
    if group:groups.append(group)
    for group in groups:
        if len(group)==1:
            flag(c,group[0]['x'],beam_y,2 if group[0]['event']['duration']==.25 else 1)
            continue
        c.setLineWidth(2.3);c.line(group[0]['x'],beam_y,group[-1]['x'],beam_y)
        for i,point in enumerate(group):
            if point['event']['duration']!=.25:continue
            if i+1<len(group) and group[i+1]['event']['duration']==.25:
                c.line(point['x'],beam_y+4,group[i+1]['x'],beam_y+4)
            elif i>0 and group[i-1]['event']['duration']==.25:continue
            else:
                direction=-1 if i else 1
                c.line(point['x'],beam_y+4,point['x']+direction*4,beam_y+4)
    for i,point in enumerate(points):
        e=point['event'];marks=e['marks'];px=point['x']
        if e['string'] is None:continue
        ny=y-'GDAE'.index(e['string'])*GAP
        if 'h' in marks and i+1<len(points):
            nx=points[i+1]['x']
            curve(c,px+2,ny+6,nx-2,ny+6,6)
            c.setFont('Helvetica',5.8);c.drawCentredString((px+nx)/2,ny+13,'H')
        if 't' in marks:
            if i+1<len(points):nx=points[i+1]['x']-5
            elif n%4: nx=positions(bars[n+1],x+BW)[0]['x']-5
            else:nx=x+BW-2
            curve(c,px+5,ny+5,nx,ny+5,6)
        if 'c' in marks and i==0 and n%4==1:
            curve(c,x+1,ny+5,px-5,ny+5,4)
        if 'v' in marks:
            end=points[i+1]['x']-4 if i+1<len(points) else x+BW-5
            p=c.beginPath();p.moveTo(px,y+35)
            for j in range(1,max(2,int((end-px)*2))):
                xx=px+j*.5
                p.lineTo(xx,y+35+1.3*math.sin((xx-px)*1.7))
            c.setLineWidth(.55);c.drawPath(p)

def main():
    validate()
    c=canvas.Canvas(str(OUTPUT),pagesize=A4,pageCompression=1)
    c.setTitle('Ado - independent bass TAB - four bars per line')
    c.setAuthor('Independent visual transcription from the supplied video')
    total_rows=math.ceil(len(bars)/4)
    pages=math.ceil(total_rows/6)
    for page in range(pages):
        c.setFillColorRGB(0,0,0);c.setFont('Helvetica-Bold',19)
        c.drawString(36,H-43,'Ado | Bass TAB')
        c.setFont('Helvetica',8.5)
        c.drawString(36,H-60,'Independent visual transcription  /  4 bars per line')
        c.setFont('Helvetica-Bold',8)
        c.drawRightString(RIGHT,H-43,f'{page+1} / {pages}')
        c.setFont('Helvetica',8)
        c.drawString(36,H-80,'4/4   |   Quarter note = 145   |   Four-string TAB, as displayed in the video')
        c.setStrokeColorRGB(.72,.72,.72);c.setLineWidth(.4);c.line(36,H-90,RIGHT,H-90)
        for row in range(6):
            number=(page*6+row)*4+1
            if number>143:break
            y=H-132-row*110
            count=min(4,144-number)
            c.setFont('Helvetica-Bold',6.5);c.setFillColorRGB(.2,.2,.2)
            for j,label in enumerate('TAB'):c.drawRightString(LEFT-6,y-j*GAP-7.3,label)
            c.setStrokeColorRGB(.45,.45,.45);c.setLineWidth(.35)
            for j in range(4):c.line(LEFT,y-j*GAP,LEFT+count*BW,y-j*GAP)
            c.setStrokeColorRGB(0,0,0);c.setLineWidth(.6)
            for j in range(count+1):c.line(LEFT+j*BW,y,LEFT+j*BW,y-30)
            for j in range(count):render_bar(c,number+j,LEFT+j*BW,y)
            if number+count-1==143:
                end=LEFT+count*BW;c.setLineWidth(1.7);c.line(end+2.5,y,end+2.5,y-30)
        c.setFillColorRGB(.32,.32,.32);c.setFont('Helvetica',6.5)
        c.drawString(36,57,'X = muted note   S = slap   P = pop   H = hammer-on   / or \\ = slide   ( ) = tied continuation')
        c.drawString(36,44,'Source: youtube.com/watch?v=wpme40lu_XE  |  Visual transcription; not independently verified against audio.')
        c.linkURL('https://youtu.be/wpme40lu_XE',(36,42,240,51),relative=0)
        c.showPage()
    c.save()
    (ROOT/'transcription.json').write_text(json.dumps({'source':'https://youtu.be/wpme40lu_XE',
        'method':'Manually read source-video frames; independent vector typesetting.',
        'meter':[4,4],'quarter_bpm':145,'bars':bars,'inspection_references':references},indent=2),encoding='utf-8')
    print(OUTPUT)

if __name__=='__main__':main()
