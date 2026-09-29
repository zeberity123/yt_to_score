import copy
import json
import threading
import time
import xml.etree.ElementTree as ET
from unittest.mock import patch

import cv2
import numpy as np
import pytest

from ai_score.control import RequestGate
from ai_score.contracts import bar_issues, default_format
from ai_score.pipeline import extract
from ai_score.providers import Client, Cancelled
from ai_score.render import musicxml, render
from ai_score.review import music_signature, needs_visual_review, apply_result
from drumscore.server import Workspace


def bar(number=1, confidence=1.):
    return dict(number=number, meter=[4, 4], pickup=False, confidence=confidence, timestamp=(number-1)*7,
                issues=[], system_end=True, tempo_bpm=0, rehearsal='', multirest=0,
                events=[dict(onset=0, duration=4, voice=1, staff=1, notes=[], marks='')])


def test_pause_finishes_current_call_blocks_next_and_resumes_without_replay(tmp_path):
    gate = RequestGate()
    client = Client('Codex', 'gpt-6-astra', '', tmp_path)
    client.auth_checked, client.gate = True, gate
    entered, release = threading.Event(), threading.Event()
    calls = []
    from ai_score.contracts import FORMAT
    def transport(*args):
        calls.append(1)
        entered.set()
        assert release.wait(3)
        return default_format('Test'), {}
    with patch.object(client, '_codex', transport):
        first = threading.Thread(target=lambda: client.request('first', FORMAT))
        first.start(); assert entered.wait(3)
        gate.pause()
        second = threading.Thread(target=lambda: client.request('second', FORMAT))
        second.start()
        assert gate.state()['active'] == 1
        release.set(); first.join(3)
        time.sleep(.05)
        assert len(calls) == 1 and second.is_alive()
        assert gate.state()['active'] == 0 and gate.state()['seconds'] > 0
        gate.resume(); second.join(3)
        assert not second.is_alive() and len(calls) == 2


def test_workspace_pause_timer_and_cancel_while_waiting(tmp_path):
    workspace = Workspace(tmp_path)
    workspace.ai_gate = gate = RequestGate()
    entered = threading.Event()
    def task():
        while not workspace.cancel.is_set():
            entered.set()
            gate.wait(workspace.cancel)
            time.sleep(.005)
    workspace.start(task, timed=True)
    assert entered.wait(3)
    workspace.command('pause-ai', {})
    first = workspace.state()['elapsedSeconds']
    time.sleep(.05)
    assert abs(workspace.state()['elapsedSeconds']-first) < .01
    assert workspace.state()['status'].startswith('Paused.')
    workspace.command('cancel', {})
    deadline = time.monotonic()+3
    while workspace.busy and time.monotonic() < deadline:
        time.sleep(.01)
    assert not workspace.busy


def test_grace_note_renders_without_consuming_time(tmp_path):
    b = bar()
    grace = dict(onset=0, duration=0, voice=1, staff=1, marks='slashed grace eighth',
                 notes=[dict(string=0, fret='', step='C', alter=0, octave=5, drum='snare', marks='')])
    b['events'].insert(0, grace)
    s = dict(meta=dict(instrument='drums', title='Grace', strings=0, meter=[4, 4], bpm=120), bars=[b])
    assert not bar_issues(b, 'drums', 0)
    layout = default_format('Grace', 4)
    xml = ET.fromstring(musicxml(s, layout))
    note = xml.find('.//note[grace]')
    assert note is not None and note.find('duration') is None
    assert note.find('grace').get('slash') == 'yes'
    render(s, layout, tmp_path/'grace.pdf')
    grace['marks'] = ''
    assert 'Event falls outside the measure' in bar_issues(b, 'drums', 0)


def test_review_ignores_prose_and_engraving_limitations_but_catches_notes():
    a = bar(); b = copy.deepcopy(a)
    b['events'][0]['marks'] = 'Eight-measure rest: measure 1 of 8'
    assert music_signature(a) == music_signature(b)
    b['issues'] = ['The instrument legend is not visible.']
    meta = dict(instrument='drums', strings=0)
    assert not needs_visual_review(b, meta)
    b['events'][0]['duration'] = 3
    assert music_signature(a) != music_signature(b)
    assert needs_visual_review(b, meta)
    assert bar_issues(b, 'drums', 0)  # Warnings remain visible.


def test_targeted_review_rejects_extra_bars_and_retains_no_decision_warning():
    bars = {1: bar()}; conflicts = {1}; observations = []
    meta = dict(instrument='drums', strings=0)
    with pytest.raises(ValueError, match='unrelated'):
        apply_result(dict(bars=[bar(2)], confirmed=[], unreadable=[], observations=[]),
                     [1], bars, conflicts, observations, meta, None)
    apply_result(dict(bars=[], confirmed=[], unreadable=[], observations=[]),
                 [1], bars, conflicts, observations, meta, None)
    assert conflicts == {1} and 'no decision' in observations[0]


def test_review_checkpoint_resumes_only_unfinished_request(tmp_path):
    video = tmp_path/'input.avi'
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*'MJPG'), 10, (320, 240))
    for _ in range(80):
        writer.write(np.full((240, 320, 3), 255, np.uint8))
    writer.release()
    folder = tmp_path/'job'
    meta = dict(title='Fixture', instrument='drums', numbered=True, first_bar=1, last_bar=2,
                meter=[4, 4], bpm=120, key_fifths=0, strings=0, crop=[0, 0, 1, 1],
                observations=[], source_bars_per_line=1)
    def initial(self, prompt, schema, images, identity):
        context = json.loads(next(line for line in prompt.splitlines() if line.startswith('{')))
        if 'video_title' in context:
            return meta, {}
        if 'review_only_bars' not in context:
            return {'bars': [bar(1, .5), bar(2, .5)], 'observations': [], 'repeats': []}, {}
        numbers = context['review_only_bars']
        if numbers == [2]:
            self.cancel.set()
            raise Cancelled('test')
        return dict(bars=[], confirmed=numbers, unreadable=[], observations=[]), {}
    client = Client('Codex', 'gpt-6-astra', '', folder/'responses')
    client.auth_checked = True
    with patch.object(Client, '_codex', initial), pytest.raises(Cancelled):
        extract(client, str(video), 'drums', folder)
    saved = json.loads(next(folder.glob('resume-*.json')).read_text(encoding='utf-8'))
    assert list(saved['reviews']) == ['1']
    def resume(self, prompt, schema, images, identity):
        context = json.loads(prompt.rsplit('\n', 1)[-1])
        assert context['review_only_bars'] == [2]
        return dict(bars=[], confirmed=[2], unreadable=[], observations=[]), {}
    client = Client('Codex', 'gpt-6-astra', '', folder/'responses')
    client.auth_checked = True
    with patch.object(Client, '_codex', resume) as transport:
        _, pdf, result = extract(client, str(video), 'drums', folder)
    assert client.usage['requests'] == 1 and pdf.exists()
    assert len(result['bars']) == 2


def test_video_title_and_job_origin_are_recorded(tmp_path):
    from pathlib import Path
    video = tmp_path/'input.avi'
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*'MJPG'), 10, (320, 240))
    for _ in range(80):
        writer.write(np.full((240, 320, 3), 255, np.uint8))
    writer.release()
    folder = tmp_path/'job'
    meta = dict(title='Model guess', instrument='drums', numbered=True, first_bar=1, last_bar=2,
                meter=[4, 4], bpm=120, key_fifths=0, strings=0, crop=[0, 0, 1, 1],
                observations=[], source_bars_per_line=1)
    def transport(self, prompt, schema, images, identity):
        context = json.loads(next(line for line in prompt.splitlines() if line.startswith('{')))
        if 'video_title' in context:
            assert context['video_title'] == 'Given title'  # the real title, not the file stem
            return meta, {}
        if 'review_only_bars' not in context:
            return {'bars': [bar(1), bar(2)], 'observations': [], 'repeats': []}, {}
        return dict(bars=[], confirmed=context['review_only_bars'], unreadable=[], observations=[]), {}
    client = Client('Codex', 'gpt-6-astra', '', folder/'responses')
    client.auth_checked = True
    with patch.object(Client, '_codex', transport):
        _, pdf, result = extract(client, str(video), 'drums', folder, title='Given title')
    assert result['meta']['title'] == 'Given title' and result['layout']['title'] == 'Given title'
    assert Path(result['job_folder']) == folder and result['frame_identity'] and result['selected_crop'] is None
    assert all(b['tempo_bpm'] == 0 and b['rehearsal'] == '' for b in result['bars'])


def test_pattern_expansion_keeps_all_numbered_occurrences_and_independent_events():
    from ai_score.accelerate import expand_patterns
    first = bar()
    first.update(rehearsal='A', tempo_bpm=110)
    result = expand_patterns({'bars': [first], 'observations': [], 'repeats': [
        dict(number=2, repeat_of=1, timestamp=3, confidence=.9, system_end=True, issues=[]),
        dict(number=3, repeat_of=2, timestamp=6, confidence=.95, system_end=False, issues=[], rehearsal='B', tempo_bpm=0, multirest=0)]})
    assert [b['number'] for b in result['bars']] == [1, 2, 3]
    assert [b['timestamp'] for b in result['bars']] == [0, 3, 6]
    # A repeated picture never inherits the first occurrence's label or tempo.
    assert [b['rehearsal'] for b in result['bars']] == ['A', '', 'B']
    assert [b['tempo_bpm'] for b in result['bars']] == [110, 0, 0]
    result['bars'][1]['events'][0]['duration'] = 2
    assert result['bars'][0]['events'][0]['duration'] == 4
    assert result['bars'][2]['events'][0]['duration'] == 4
    with pytest.raises(ValueError, match='unknown or circular'):
        expand_patterns({'bars': [], 'observations': [], 'repeats': [
            dict(number=1, repeat_of=1, timestamp=0, confidence=1, system_end=True, issues=[])]})
