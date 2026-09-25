import cv2
import numpy as np
from PIL import Image

from drumscore.extract import Extraction, extract
from drumscore.vision import Region, auto_region, clean_tab, staffs, split_systems, tab_signature, difference
from drumscore.guitar import overlap_cut


def tab(note='12', box=None):
    image = np.full((260,1000,3),255,np.uint8)
    for y in range(75,176,20):
        cv2.line(image,(0,y),(999,y),(215,215,215),1)
    for x in (15,260,505,750,995):
        cv2.line(image,(x,75),(x,175),(30,30,30),2)
    for x in range(80,980,70):
        cv2.rectangle(image,(x-5,163),(x+28,186),(255,255,255),-1)
        cv2.putText(image,note,(x,182),cv2.FONT_HERSHEY_SIMPLEX,.6,(20,20,20),2)
        cv2.line(image,(x+5,193),(x+5,227),(30,30,30),2)
    cv2.putText(image,'P.M.',(70,45),cv2.FONT_HERSHEY_SIMPLEX,.55,(20,20,20),1)
    if box is not None:
        cv2.rectangle(image,(box,55),(box+235,196),(0,0,0),2)
    return image


def test_six_strings_bottom_frets_and_rhythm_are_preserved():
    image = clean_tab(tab())
    assert len(staffs(image,6)) == 1
    strips = split_systems(image,rules=6)
    assert len(strips) == 1
    assert len(staffs(strips[0],6)) == 1
    assert np.count_nonzero(strips[0][-35:] < 100) > 100
    frame=np.full((720,1000,3),70,np.uint8)
    frame[460:]=tab()
    crop=auto_region(frame,notation='guitar')
    assert .6 < crop.top < .75


def test_white_ink_tab_on_moving_dark_background():
    source=tab()
    a=np.full_like(source,35)
    b=a.copy()
    b[10:240,100:400]=65
    for frame in (a,b):
        frame[source[:,:,0]<100]=235
        frame[(source[:,:,0]>=100)&(source[:,:,0]<240)] += 25
    first, second=clean_tab(a),clean_tab(b)
    assert len(staffs(first,6)) == len(staffs(second,6)) == 1
    assert difference(tab_signature(first),tab_signature(second)) < .035
    assert first[10,600] == 255


def test_playback_box_does_not_create_duplicates_but_changed_frets_do(tmp_path):
    a,b,c=tab(box=20),tab(box=520),tab('14',box=20)
    assert difference(tab_signature(clean_tab(a)),tab_signature(clean_tab(b))) < .035
    assert difference(tab_signature(clean_tab(a)),tab_signature(clean_tab(c)), fine=True) > .035
    filename=tmp_path/'tab.avi'
    writer=cv2.VideoWriter(str(filename),cv2.VideoWriter_fourcc(*'MJPG'),6,(1000,260))
    assert writer.isOpened()
    for frame in (a,b,c,a):
        for _ in range(12):writer.write(frame)
    writer.release()
    project=extract(filename,tmp_path,region=Region(),notation='guitar',interval=.25)
    assert len(project.lines) == 3
    assert Extraction.load(project.directory/'project.json').notation == 'guitar'
    with Image.open(project.directory/project.lines[0].path) as line:
        assert len(staffs(np.array(line),6)) == 1


def test_ambiguous_or_unrelated_panels_are_not_trimmed():
    assert overlap_cut(clean_tab(tab()),clean_tab(tab('19'))) is None
    assert overlap_cut(np.full((100,500),255,np.uint8),np.full((100,500),255,np.uint8)) is None


def test_overlapping_panels_join_at_the_same_barline():
    canvas=np.full((260,1800),255,np.uint8)
    for y in range(75,176,20):cv2.line(canvas,(0,y),(1799,y),215,1)
    for x in range(15,1800,250):cv2.line(canvas,(x,75),(x,175),20,2)
    rng=np.random.default_rng(42)
    for x in range(45,1770,45):
        y=75+int(rng.integers(0,6))*20
        cv2.rectangle(canvas,(x-2,y-14),(x+26,y+4),255,-1)
        cv2.putText(canvas,str(rng.integers(0,24)),(x,y+4),cv2.FONT_HERSHEY_SIMPLEX,.6,20,2)
    cut=overlap_cut(canvas[:,:1000],canvas[:,700:1700])
    assert cut is not None
    assert abs(cut[0]-765)<=2 and abs(cut[1]-65)<=2
