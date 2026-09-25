"""Duplicate suppression must retain musical changes, not merely lower counts."""
import cv2
import numpy as np
import pytest
from PIL import Image

from drumscore.extract import extract
from drumscore.guitar import overlap_cut
from drumscore.matching import aligned_difference, measure_anchors
from drumscore.notation import clean_notation, system_fingerprint
from drumscore.vision import Region, system_signature, staffs
from test_instruments import music
from test_pipeline import score, make_video


def bass_tab(note='12', width=1000):
    image=np.full((300,width,3),255,np.uint8)
    for y in (90,110,130,150):cv2.line(image,(10,y),(width-10,y),(140,140,140),1)
    for x in range(25,width-10,250):cv2.line(image,(x,90),(x,150),(20,20,20),2)
    for x in range(80,width-40,100):
        cv2.rectangle(image,(x-4,116),(x+32,137),(255,255,255),-1)
        cv2.putText(image,note,(x,134),cv2.FONT_HERSHEY_SIMPLEX,.6,(20,20,20),2)
        cv2.line(image,(x+5,166),(x+5,200),(20,20,20),2)
    return image


def panel(kind):
    return score(width=1000) if kind=='staff' else bass_tab() if kind=='tab' else music(kind)


def nudge(image,dx):
    return cv2.warpAffine(image,np.float32([[1,0,dx],[0,1,0]]),image.shape[1::-1],borderValue=(255,255,255))


def fingerprint(image,kind):
    gray=clean_notation(image,kind)
    return system_signature(gray) if kind=='staff' else system_fingerprint(gray,kind)


def changed_panel(kind):
    if kind=='staff':return score(note=175,width=1000)
    if kind=='tab':
        image=bass_tab()
        cv2.rectangle(image,(76,116),(112,137),(255,255,255),-1)
        cv2.putText(image,'14',(80,134),cv2.FONT_HERSHEY_SIMPLEX,.6,(20,20,20),2)
        return image
    image=music(kind)
    # Change only the upper staff, leaving the bass TAB / other hand untouched.
    cv2.ellipse(image,(580,100),(7,5),-20,0,360,(0,0,0),-1)
    cv2.line(image,(586,100),(586,63),(0,0,0),2)
    return image


@pytest.mark.parametrize('kind',['staff','tab','bass','piano'])
def test_panel_nudges_removed_but_changed_music_and_later_return_kept(tmp_path,kind):
    notation='bass' if kind=='tab' else kind
    original=panel(kind)
    shifted=nudge(original,-12)
    change=nudge(changed_panel(kind),-12)
    video=tmp_path/f'{kind}.avi'
    make_video(video,[original,shifted,change,original])
    project=extract(video,tmp_path,region=Region(),notation=notation,interval=.25)
    assert len(project.lines)==3
    assert [line.time for line in project.lines]==[0,4,6]
    # No shift is applied to the printable image or retained editing source.
    with Image.open(project.directory/project.lines[0].source_path) as source:
        assert source.width==original.shape[1]
    kept=extract(video,tmp_path,region=Region(),notation=notation,interval=.25,remove_overlap=False)
    assert len(kept.lines)==4


@pytest.mark.parametrize('kind',['staff','tab','bass','piano'])
def test_moving_highlight_does_not_repeat_a_panel(tmp_path,kind):
    notation='bass' if kind=='tab' else kind
    a,b=[panel(kind) for _ in range(2)]
    for image,x in ((a,300),(b,700)):
        original=image.copy()
        cv2.line(image,(x,40),(x,image.shape[0]-40),(0,255,0),4)
        image[original.max(axis=2)<80]=original[original.max(axis=2)<80]
        # Light measure wash retains black notation and staff rules.
        roi=image[40:-40,x+8:x+120]
        roi[:,:,0]=np.minimum(roi[:,:,0],210)
    video=tmp_path/'highlight.avi'
    make_video(video,[a,b])
    project=extract(video,tmp_path,region=Region(),notation=notation,interval=.25)
    assert len(project.lines)==1


@pytest.mark.parametrize('kind',['staff','bass','piano'])
def test_fixed_barlines_prevent_aligning_away_a_changed_note(kind):
    a=panel(kind)
    # Shift all noteheads but leave barlines and staff geometry fixed.
    b=a.copy()
    top,bottom=(50,140) if kind=='staff' else (65,130)
    b[top:bottom,130:210]=255
    for y in range(80,121,10):cv2.line(b,(130,y),(209,y),(130,130,130),1)
    b[top:bottom,142:222]=a[top:bottom,130:210]
    first,second=[fingerprint(image,kind) for image in (a,b)]
    anchors=[measure_anchors(clean_notation(image,kind),rules=4 if kind=='bass' else 5,paired=True) for image in (a,b)]
    assert aligned_difference(first,second,anchors=anchors)>.035


def test_piano_lower_hand_change_survives_panel_alignment():
    a=music(lower_note=400)
    b=nudge(music(lower_note=430),-12)
    anchors=[measure_anchors(clean_notation(image,'piano')) for image in (a,b)]
    assert aligned_difference(fingerprint(a,'piano'),fingerprint(b,'piano'),anchors=anchors)>.035


@pytest.mark.parametrize('change',['pitch','notehead','rhythm'])
def test_drum_musical_changes_survive_panel_alignment(change):
    a=score(width=1000)
    b=a.copy()
    if change=='pitch':
        b[102:118,139:161]=255
        cv2.line(b,(139,110),(160,110),(120,120,120),1)
        cv2.ellipse(b,(150,100),(7,5),-20,0,360,(0,0,0),-1)
    elif change=='notehead':
        b[102:118,139:161]=255
        cv2.line(b,(139,110),(160,110),(120,120,120),1)
        cv2.line(b,(143,104),(157,116),(0,0,0),2)
        cv2.line(b,(143,116),(157,104),(0,0,0),2)
    else:
        cv2.ellipse(b,(161,65),(6,9),-25,0,180,(0,0,0),3)
    b=nudge(b,-12)
    anchors=[measure_anchors(clean_notation(image,'staff')) for image in (a,b)]
    assert aligned_difference(fingerprint(a,'staff'),fingerprint(b,'staff'),anchors=anchors)>.035


def test_bass_hd_single_fret_change_is_retained(tmp_path):
    frames=[cv2.resize(image,(1920,480)) for image in (bass_tab(),changed_panel('tab'))]
    video=tmp_path/'fret.avi'
    make_video(video,frames)
    project=extract(video,tmp_path,region=Region(),notation='bass',interval=.25)
    assert len(project.lines)==2


def test_gradual_nudges_do_not_move_the_accepted_anchor(tmp_path):
    video=tmp_path/'drift.avi'
    make_video(video,[nudge(score(width=1000),dx) for dx in (0,-10,-20,-30,-40)])
    project=extract(video,tmp_path,region=Region(),interval=.25)
    assert len(project.lines)>=2
    assert project.lines[0].time==0


def test_new_edge_notation_is_not_discarded_as_a_panel_nudge():
    a=score(width=1000)
    b=nudge(a,20)
    cv2.putText(b,'7',(3,70),cv2.FONT_HERSHEY_SIMPLEX,.6,(0,0,0),2)
    anchors=[measure_anchors(clean_notation(image,'staff')) for image in (a,b)]
    assert aligned_difference(fingerprint(a,'staff'),fingerprint(b,'staff'),anchors=anchors)>.035


def overlapping_bass_panels():
    canvas=np.full((260,1800),255,np.uint8)
    for y in range(75,136,20):cv2.line(canvas,(0,y),(1799,y),140,1)
    for x in range(15,1800,250):cv2.line(canvas,(x,75),(x,135),20,2)
    rng=np.random.default_rng(42)
    for x in range(45,1770,45):
        y=75+int(rng.integers(0,4))*20
        cv2.rectangle(canvas,(x-2,y-14),(x+26,y+4),255,-1)
        cv2.putText(canvas,str(rng.integers(0,24)),(x,y+4),cv2.FONT_HERSHEY_SIMPLEX,.6,20,2)
    return canvas[:,:1000],canvas[:,700:1700]


def test_bass_overlap_joins_only_matching_standalone_tab():
    a,b=overlapping_bass_panels()
    cut=overlap_cut(a,b,rules=4)
    assert cut is not None
    assert abs(cut[0]-765)<=2 and abs(cut[1]-65)<=2
    changed=b.copy()
    cv2.rectangle(changed,(130,80),(170,106),255,-1)
    cv2.putText(changed,'19',(135,102),cv2.FONT_HERSHEY_SIMPLEX,.7,0,2)
    assert overlap_cut(a,changed,rules=4) is None
    combined=clean_notation(music('bass'),'bass')
    assert overlap_cut(combined,combined,rules=4) is None


def test_bass_joined_capture_keeps_original_panels_for_crop_editing(tmp_path):
    video=tmp_path/'overlap.avi'
    # Keep this recovery test lossless so codec noise cannot make the purposely
    # conservative overlap verifier decline an otherwise exact shared measure.
    writer=cv2.VideoWriter(str(video),cv2.VideoWriter_fourcc(*'FFV1'),6,(1000,260))
    assert writer.isOpened()
    for image in overlapping_bass_panels():
        for _ in range(12):writer.write(cv2.cvtColor(image,cv2.COLOR_GRAY2BGR))
    writer.release()
    project=extract(video,tmp_path,region=Region(),notation='bass',interval=.25)
    assert len(project.lines)==2
    assert any('Joined 1 overlapping TAB' in warning for warning in project.warnings)
    first,second=project.lines
    assert .76 < first.crop[2] < .77
    assert .06 < second.crop[0] < .07
    for line in project.lines:
        with Image.open(project.directory/line.source_path) as source:assert source.width==1000
        assert line.original_crop==line.crop
