import threading

import numpy as np
import pytest
from PIL import Image

from drumscore.tempo import pulse_scores, complete_bars, recover_timed_repeats, validate_timing, detect_tempo
from drumscore.extract import Extraction, ScoreLine
from drumscore.editing import archive_project, open_project, edit_line
from drumscore.video import Cancelled
from drumscore.vision import Region
from test_print_layout import tab
from test_instruments import music


@pytest.mark.parametrize('bpm', [83, 113, 157])
def test_audio_pulse_estimate_from_noisy_clicks(bpm):
    rate = 11025
    audio = np.random.default_rng(0).normal(0, .001, rate*25)
    click = np.random.default_rng(1).normal(0, 1, 700)*np.exp(-np.arange(700)/80)
    for time in np.arange(.3, 24, 60/bpm):
        start = round(time*rate)
        audio[start:start+len(click)] += click
    tempos, scores = pulse_scores(audio, rate)
    assert abs(tempos[np.argmax(scores)]-bpm) < 1


def test_silence_short_audio_and_cancel(monkeypatch):
    assert pulse_scores(np.zeros(11025*20)) is None
    assert pulse_scores(np.ones(300)) is None
    event = threading.Event()
    event.set()
    monkeypatch.setattr('drumscore.tempo.metadata', lambda p: (100,100,20))
    with pytest.raises(Cancelled):
        detect_tempo('unused', cancel=event)


@pytest.mark.parametrize('bpm,beats', [(None,4), ('',4), (float('nan'),4), (120,float('inf')), (301,4), (120,0)])
def test_invalid_settings(bpm, beats):
    with pytest.raises(ValueError):
        validate_timing(bpm, beats)


def test_counts_only_complete_single_tab_lines():
    image = tab(bars=4, rules=4)
    assert complete_bars(image,4) == 4
    # Right-edge notes in a partial fifth bar must not count as four complete bars.
    assert complete_bars(image.crop((0,0,image.width-40,image.height)),4) is None
    assert complete_bars(Image.fromarray(music('bass')),4) is None
    assert complete_bars(Image.new('RGB',(800,200),'white'),4) is None


def timed_project(folder, durations=(12,8,8,8,16,4,8,8,20)):
    folder.mkdir(exist_ok=True)
    lines, time = [], 0
    for i,duration in enumerate(durations):
        name = f'line_{i}.png'
        tab(bars=2 if duration==4 else 4, rules=4).save(folder/name)
        lines.append(ScoreLine(name,time,i,source_path=name,original_path=name,
                               crop=[0,0,1,1],original_crop=[0,0,1,1],visible_until=time+duration))
        time += duration
    return Extraction(folder,'Timing','',Region(),lines,[],'bass')


def test_repeat_inference_preserves_short_lines_and_edges_and_archives(tmp_path):
    project = timed_project(tmp_path/'project')
    assert recover_timed_repeats(project,120) == 1
    assert [l.time for l in project.lines] == [0,12,20,28,36,44,52,56,64,72]
    assert project.lines[4].path != project.lines[5].path
    assert (project.directory/project.lines[4].path).read_bytes() == (project.directory/project.lines[5].path).read_bytes()
    archive = archive_project(project,tmp_path/'timed.drumscore')
    opened = open_project(archive,tmp_path/'opened')
    assert opened.lines[5].visible_until == 52
    edit_line(opened,5,height_scale=.75)
    assert opened.lines[4].height_scale == 1
    assert recover_timed_repeats(project,120) == 0


@pytest.mark.parametrize('bpm,beats', [(60,4), (240,4), (120,3), (150,4)])
def test_wrong_tempo_or_meter_does_not_multiply_every_line(tmp_path,bpm,beats):
    project = timed_project(tmp_path)
    assert recover_timed_repeats(project,bpm,beats) == 0


def test_gap_and_missing_timing_are_not_repeats(tmp_path):
    project = timed_project(tmp_path)
    project.lines[4].visible_until -= 5
    assert recover_timed_repeats(project,120) == 0
    project.lines[4].visible_until = None
    assert recover_timed_repeats(project,120) == 0


def test_multiple_identical_passes(tmp_path):
    project = timed_project(tmp_path, (12,8,8,8,24,4,8,8,20))
    assert recover_timed_repeats(project,120) == 2
    assert [l.time for l in project.lines[4:8]] == [36,44,52,60]
