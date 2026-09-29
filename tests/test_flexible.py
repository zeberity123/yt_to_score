import cv2
import numpy as np
import pytest
from PIL import Image

from drumscore.extract import extract
from drumscore.notation import clean_notation, follow_region, split_notation, system_groups
from drumscore.tempo import complete_system_bars, recover_timed_repeats
from drumscore.vision import Region
from test_instruments import music
from test_tempo import timed_project
from test_print_layout import tab


def test_faint_fifth_rule_does_not_drop_line_or_detach_rest_count():
    frame = music('bass')
    frame[120,26:975] = 210
    cv2.putText(frame,'2',(850,65),cv2.FONT_HERSHEY_SIMPLEX,.8,(0,0,0),2)
    gray = clean_notation(frame,'bass')
    assert len(system_groups(gray,'bass')) == 1
    strips = split_notation(gray,'bass')
    assert len(strips) == 1
    assert np.count_nonzero(strips[0][:30,850:880] < 100) > 10


def panel(offset, note=400):
    frame = np.full((800,1000,3),45,np.uint8)
    frame[offset:offset+370] = music('bass',note)
    return frame


def test_following_keeps_shifted_system_and_tightens_blank_margins():
    region = Region(0,.40,1,.82)
    for offset in (300,390):
        frame = panel(offset)
        area = follow_region(frame,region,'bass')
        gray = clean_notation(area.crop(frame),'bass')
        assert len(system_groups(gray,'bass')) == 1
        assert area.top*800 <= offset+60
        assert area.bottom*800 >= offset+325
        assert area.left > 0
    page = np.concatenate((music(),music()))
    assert follow_region(page,Region(),'piano') == Region()


def test_flexible_extraction_retains_source_coordinates(monkeypatch,tmp_path):
    sequence = [(i*.5,panel(300 if i<4 else 390,200 if i<4 else 700)) for i in range(8)]
    monkeypatch.setattr('drumscore.extract.metadata',lambda _: (1000,800,4))
    monkeypatch.setattr('drumscore.extract.frames',lambda *args: iter(sequence))
    monkeypatch.setattr('drumscore.numbered.is_numbered_video',lambda *args: False)
    # Use a generator with close(), just like the real decoder.
    def samples(*args):
        yield from sequence
    monkeypatch.setattr('drumscore.extract.frames',samples)
    project = extract('unused',tmp_path,region=Region(0,.40,1,.82),notation='bass',flexible_area=True)
    assert len(project.lines) == 2
    for line in project.lines:
        with Image.open(project.directory/line.raw_source_path) as source:
            crop = source.crop(tuple(round(v*s) for v,s in zip(line.crop,(1000,800,1000,800))))
        with Image.open(project.directory/line.path) as image:
            assert crop.size == image.size
            assert len(system_groups(clean_notation(np.array(crop)[:,:,::-1],'bass'),'bass')) == 1
    assert project.lines[1].crop[1] > project.lines[0].crop[1]


@pytest.mark.parametrize('notation',['staff','piano','bass'])
def test_complete_system_bar_counts(notation):
    image = tab(bars=4,rules=5) if notation == 'staff' else Image.fromarray(music(notation))
    assert complete_system_bars(image,notation) == (4 if notation == 'staff' else 3)
    assert complete_system_bars(image.crop((0,0,image.width-70,image.height)),notation) is None
    if notation == 'piano':
        assert complete_system_bars(Image.fromarray(np.concatenate((music(),music()))),notation) is None


@pytest.mark.parametrize('notation',['staff','piano'])
def test_timing_recovery_for_drums_and_piano(tmp_path,notation):
    project = timed_project(tmp_path,durations=(12,8,8,8,16,8,8,8,20))
    project.notation = notation
    for line in project.lines:
        image = tab(bars=4,rules=5) if notation == 'staff' else Image.fromarray(music())
        image.save(project.directory/line.path)
    assert recover_timed_repeats(project,120 if notation == 'staff' else 90) == 1
