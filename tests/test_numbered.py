import cv2
import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont

from drumscore.numbered import BarRecovery, numbered_boundaries, overlay_group
from drumscore.vision import auto_region


def panel(start=10, offset=40, bright=False):
    image=Image.new('RGB',(1200,210),(18,18,18))
    draw=ImageDraw.Draw(image)
    font=ImageFont.load_default(size=15)
    if bright:
        draw.rectangle((730,0,1199,209),fill=(218,218,218))
    for y in (60,80,100,120):
        draw.line((0,y,1199,y),fill=(110,110,110))
    for i in range(6):
        x=offset+i*210
        number=str(start+i)
        box=draw.textbbox((0,0),number,font=font)
        draw.text((x-(box[2]-box[0])/2,34),number,font=font,fill='white')
        draw.line((x,60,x,120),fill='white',width=2)
        if i<5:
            draw.text((x+60,90),'7',font=font,fill='white')
            draw.line((x+60,110,x+60,163),fill='white',width=2)
    return np.array(image)


def test_numbered_boundaries_distinguish_identical_music_and_ignore_cursor():
    frame=panel()
    cv2.line(frame,(570,55),(570,170),(0,90,190),2)
    assert overlay_group(frame)==(60,120,20)
    assert numbered_boundaries(frame,(60,120,20))==[(40+210*i,10+i) for i in range(6)]


def test_recovery_keeps_same_notes_in_different_numbered_bars():
    recovery=BarRecovery()
    for time in range(3):
        recovery.observe(panel(),(60,120,20),time)
    assert list(recovery.resolved())==[10,11,12,13,14]
    assert all(bar['count']==3 for bar in recovery.resolved().values())
    recovery.observe(panel(start=13),(60,120,20),4)
    assert set(recovery.resolved())==set(range(10,18))
    assert not recovery.backward


def test_numbering_reset_declines_global_deduplication():
    recovery=BarRecovery()
    recovery.observe(panel(start=30),(60,120,20),0)
    recovery.observe(panel(start=10),(60,120,20),5)
    assert recovery.backward


def test_missing_barline_does_not_merge_two_bars_or_renumber_them():
    frame=panel()
    # Number 11 and its boundary disappear against the background. Without a
    # previously measured width, the interval 10..12 must remain unassigned.
    frame[:125,220:280]=18
    unknown=numbered_boundaries(frame,(60,120,20))
    assert (40,11) not in unknown and (40,10) not in unknown
    known=numbered_boundaries(frame,(60,120,20),{10:210})
    assert (40,10) in known and (250,11) in known and (460,12) in known


def test_recovery_replaces_obscured_columns_from_another_position():
    recovery=BarRecovery()
    for time in range(2):
        recovery.observe(panel(bright=True),(60,120,20),time)
    before=recovery.resolved()[13]['quality'].mean()
    # The same bar moves into the dark center in the following view.
    recovery.observe(panel(start=12),(60,120,20),3)
    after=recovery.resolved()[13]
    assert after['quality'].mean()<before*.5
    assert np.count_nonzero(after['image']<100)>30


def test_temporal_cleanup_removes_moving_fragment_but_keeps_notation_and_raw():
    recovery=BarRecovery()
    noisy=panel()
    cv2.line(noisy,(160,140),(160,160),(255,255,255),2)
    recovery.observe(noisy,(60,120,20),0)
    before=recovery.resolved()[10]['image'].copy()
    for time in range(1,6):
        recovery.observe(panel(),(60,120,20),time)
    value=recovery.resolved()[10]
    # Coordinates relative to the bar crop (left=40, top=30).
    assert np.count_nonzero(before[110:130,119:123]<100)>20
    assert np.count_nonzero(value['image'][110:130,119:123]<100)==0
    np.testing.assert_array_equal(value['image'][55:82,55:85],before[55:82,55:85])
    assert value['raw'].shape==(*value['image'].shape,3)
    assert np.any(value['raw'][110:130,119:123]>200)  # Raw pixels remain reversible.


def test_bright_occlusions_do_not_vote_to_erase_a_real_note():
    recovery=BarRecovery()
    for time in range(3):
        recovery.observe(panel(),(60,120,20),time)
    before=recovery.resolved()[10]['image'].copy()
    hidden=panel()
    hidden[78:112,88:132]=230
    for time in range(3,10):
        recovery.observe(hidden,(60,120,20),time)
    after=recovery.resolved()[10]['image']
    np.testing.assert_array_equal(after[50:80,52:82],before[50:80,52:82])


def test_antialiased_stem_over_warm_footage_keeps_its_tinted_edge():
    recovery=BarRecovery()
    frame=panel()
    cv2.line(frame,(160,140),(160,165),(175,205,215),1)
    for time in range(5):
        recovery.observe(frame,(60,120,20),time)
    image=recovery.resolved()[10]['image']
    assert np.all(image[110:135,120]<100)


def test_white_bass_auto_crop_excludes_excess_footage_but_keeps_rhythm():
    frame=np.full((700,1200,3),35,np.uint8)
    frame[440:650]=panel()
    region=auto_region(frame,notation='bass')
    assert 435 <= region.top*700 <= 474
    assert 603 <= region.bottom*700 <= 650


def test_unnumbered_opening_requires_the_visible_start_of_the_strings():
    frame=panel(start=1)
    frame[:56,20:65]=18
    assert (40,1) not in numbered_boundaries(frame,(60,120,20))
    frame[:,:40]=18
    assert (40,1) in numbered_boundaries(frame,(60,120,20))


def test_unreadable_ending_is_kept_through_double_bar_with_full_source(tmp_path,monkeypatch):
    from drumscore.manual import new_manual_project
    from drumscore.vision import Region
    from drumscore.numbered import append_numbered_ending
    frame=panel(start=10)
    frame[:56,1060:1120]=18  # The final measure label is obscured.
    for x in (1190,1198):
        cv2.line(frame,(x,60),(x,120),(255,255,255),2)
    def sampled(*args,**kwargs):
        yield 2.0,frame
    monkeypatch.setattr('drumscore.video.frames',sampled)
    project=new_manual_project(tmp_path,'Ending','',Region())
    project.notation='bass'
    assert append_numbered_ending(project,'unused',13,0,3)
    assert len(project.lines)==1
    line=project.lines[0]
    assert line.crop[0]==pytest.approx(880/1200)
    assert line.crop[2]==pytest.approx(1191/1200)
    with Image.open(project.directory/line.source_path) as source:
        assert source.size==(1200,210)
    assert any('unconfirmed' in warning for warning in project.warnings)


def test_numbered_extraction_reports_gaps_and_keeps_original_recovered_images(tmp_path,monkeypatch):
    from drumscore.numbered import extract_numbered
    from drumscore.editing import archive_project,open_project
    frames=[panel(start=10),panel(start=13),panel(start=20)]
    def sampled(*args,**kwargs):
        for i,frame in enumerate(frames):
            yield float(i),frame
    monkeypatch.setattr('drumscore.video.frames',sampled)
    from drumscore.vision import Region
    project=extract_numbered('unused',tmp_path,'Numbered','',Region(),0,3,lambda *args:None,None)
    assert project is not None
    assert any('18, 19' in note for note in project.warnings)
    assert len(project.lines)==4
    reopened=open_project(archive_project(project,tmp_path/'numbered.drumscore'),tmp_path/'opened')
    assert len(reopened.lines)==len(project.lines)
    assert all((reopened.directory/line.original_path).is_file() for line in reopened.lines)
    assert all(line.bar_bounds[-1]==Image.open(reopened.directory/line.path).width for line in reopened.lines)
    assert all(len(line.bar_bounds)==len(line.bar_numbers)+1 for line in reopened.lines)
    assert all((reopened.directory/line.raw_source_path).is_file() for line in reopened.lines)
