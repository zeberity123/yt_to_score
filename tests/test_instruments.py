import cv2
import numpy as np
import pytest
from PIL import Image

from drumscore.extract import Extraction, extract
from drumscore.notation import clean_notation, system_groups, split_notation, system_fingerprint
from drumscore.vision import Region, auto_region, staffs, difference


def music(kind='piano', lower_note=400):
    image=np.full((370,1000,3),255,np.uint8)
    upper=(80,120,10)
    lower=(220,260,10) if kind=='piano' else (220,280,20)
    for first,last,gap in (upper,lower):
        for y in range(first,last+1,gap):cv2.line(image,(25,y),(975,y),(130,130,130),1)
    for x in (25,330,650,975):cv2.line(image,(x,upper[0]),(x,lower[1]),(30,30,30),2)
    for x,y in ((180,110),(lower_note,lower[1]-10)):
        cv2.ellipse(image,(x,y),(7,5),-20,0,360,(0,0,0),-1)
        cv2.line(image,(x+6,y),(x+6,y-37),(0,0,0),2)
    if kind=='bass':
        cv2.rectangle(image,(380,240),(420,283),(255,255,255),-1)
        cv2.putText(image,'12',(385,275),cv2.FONT_HERSHEY_SIMPLEX,.65,(0,0,0),2)
    cv2.putText(image,'mf',(60,178),cv2.FONT_HERSHEY_SIMPLEX,.6,(0,0,0),2)
    cv2.putText(image,'Ped.',(60,324),cv2.FONT_HERSHEY_SIMPLEX,.55,(0,0,0),1)
    return image


@pytest.mark.parametrize('kind',['bass','piano'])
def test_related_staves_stay_together_with_dynamics_and_pedal(kind):
    gray=clean_notation(music(kind),kind)
    assert len(system_groups(gray,kind))==1
    parts=split_notation(gray,kind)
    assert len(parts)==1
    expected=2 if kind=='piano' else 1
    assert len(staffs(parts[0]))==expected
    if kind=='bass':assert len(staffs(parts[0],4))==1
    assert np.count_nonzero(parts[0][-25:]<100)>20


@pytest.mark.parametrize('kind',['bass','piano'])
@pytest.mark.parametrize('top',[True,False])
def test_detects_score_panel_above_or_below_footage(kind,top):
    image=np.full((900,1000,3),55,np.uint8)
    start=0 if top else 530
    image[start:start+370]=music(kind)
    region=auto_region(image,notation=kind)
    assert region.top*900<=start+45
    assert region.bottom*900>=start+325
    assert (region.bottom-region.top)*900<430
    assert len(system_groups(clean_notation(region.crop(image),kind),kind))==1


def test_four_string_tab_detector_does_not_accept_part_of_five_line_staff():
    image=clean_notation(music(),'piano')
    assert len(staffs(image))==2
    assert staffs(image,4)==[]


def test_piano_page_does_not_pair_an_orphan_staff_with_the_next_system():
    complete=music()
    orphan=complete[205:290]
    page=np.concatenate((orphan,np.full((60,1000,3),255,np.uint8),complete))
    groups=system_groups(clean_notation(page,'piano'),'piano')
    assert len(groups)==1
    assert groups[0][0]>len(orphan)


def test_left_hand_change_is_part_of_the_piano_fingerprint():
    a,b=[clean_notation(music(lower_note=x),'piano') for x in (400,700)]
    assert difference(system_fingerprint(a,'piano'),system_fingerprint(b,'piano'))>.035


def test_playback_cursor_is_removed_but_colored_notes_survive():
    image=music()
    cv2.line(image,(500,75),(500,285),(0,255,0),4)
    image[106:115,176:185]=(255,0,0)
    gray=clean_notation(image,'piano')
    assert gray[150,500]==255
    assert gray[110,180]<100


def test_piano_overlap_removal_keeps_both_hands_and_later_repeats(tmp_path):
    a,b,c=[music(lower_note=x) for x in (200,400,700)]
    pages=[np.concatenate((a,b)),np.concatenate((b,c)),np.concatenate((a,b))]
    filename=tmp_path/'piano.avi'
    writer=cv2.VideoWriter(str(filename),cv2.VideoWriter_fourcc(*'MJPG'),6,(1000,740))
    assert writer.isOpened()
    for page in pages:
        for _ in range(12):writer.write(page)
    writer.release()
    project=extract(filename,tmp_path,region=Region(),notation='piano',interval=.25)
    assert len(project.lines)==5
    assert Extraction.load(project.directory/'project.json').notation=='piano'
    for line in project.lines:
        with Image.open(project.directory/line.path) as image:assert len(staffs(np.array(image)))==2


def test_bass_project_extracts_combined_notation_and_tab(tmp_path):
    filename=tmp_path/'bass.avi'
    frame=music('bass')
    writer=cv2.VideoWriter(str(filename),cv2.VideoWriter_fourcc(*'MJPG'),6,(1000,370))
    assert writer.isOpened()
    for _ in range(15):writer.write(frame)
    writer.release()
    project=extract(filename,tmp_path,notation='bass',region=Region())
    assert len(project.lines)==1
    assert Extraction.load(project.directory/'project.json').notation=='bass'
    with Image.open(project.directory/project.lines[0].path) as image:
        gray=np.array(image)
        assert len(staffs(gray))==len(staffs(gray,4))==1


def test_bass_tempo_badge_disappearing_does_not_repeat_the_same_tab():
    from drumscore.notation import notation_signature
    image=np.full((350,1000),255,np.uint8)
    for y in (150,170,190,210):cv2.line(image,(20,y),(980,y),0,1)
    for x in (100,250,400,650,850):
        cv2.putText(image,'7',(x,192),cv2.FONT_HERSHEY_SIMPLEX,.7,0,2)
    badge=image.copy()
    cv2.putText(badge,'Tempo = 100',(70,55),cv2.FONT_HERSHEY_SIMPLEX,.7,0,2)
    assert difference(notation_signature(image,'bass'),notation_signature(badge,'bass'))==0
    changed=image.copy()
    cv2.putText(changed,'12',(530,172),cv2.FONT_HERSHEY_SIMPLEX,.7,0,2)
    assert difference(notation_signature(image,'bass'),notation_signature(changed,'bass'))>.035
