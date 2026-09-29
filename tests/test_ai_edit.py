import json
import time
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
import pytest

from ai_score.contracts import EDIT, LINE_EDIT, default_format, validate_schema
from ai_score.edit import apply_marks
from ai_score.providers import Client
from drumscore.server import Workspace


def fixture():
    bars = []
    for number in range(1, 11):
        bars.append(dict(number=number, meter=[4, 4], pickup=False, confidence=1., timestamp=number,
                         system_end=number in (3, 7, 10), issues=[], events=[dict(onset=0, duration=4,
                         staff=1, voice=1, notes=[], marks='')]))
    return dict(meta=dict(title='Original rows', instrument='bass', strings=4, bpm=120, meter=[4, 4],
                          source_bars_per_line=0, first_bar=1, last_bar=10, numbered=True, observations=[]),
                bars=bars, layout=default_format('Original rows', 0), review=[])


def edit_result(**overrides):
    result = {**default_format('Original rows', 0), 'set_marks': [], 'reread_bars': []}
    result.update(overrides)
    return result


def settle(workspace):
    deadline = time.monotonic()+30
    while workspace.busy and time.monotonic() < deadline:
        time.sleep(.02)
    assert not workspace.busy
    return workspace.error


def context_of(prompt):
    return json.loads(next(line for line in prompt.splitlines() if line.startswith('{')))


def test_edit_schema_and_apply_marks():
    validate_schema(edit_result(set_marks=[dict(bar=1, tempo_bpm=120, rehearsal='A', remove_words=['cresc.'])]), EDIT)
    validate_schema({'exclude_lines': [2], 'move_line': [{'line': 3, 'before': 1}], 'retranscribe_lines': [],
                     'notes': [], 'unsupported_requests': []}, LINE_EDIT)
    score = fixture()
    score['bars'][0]['events'][0]['marks'] = 'cresc.'
    changed = apply_marks(score, [dict(bar=1, tempo_bpm=120, rehearsal='A', remove_words=['cresc.']),
                                  dict(bar=2, tempo_bpm=0, rehearsal='', remove_words=[])])
    assert changed == [1]
    first = score['bars'][0]
    assert first['tempo_bpm'] == 120 and first['rehearsal'] == 'A' and first['events'][0]['marks'] == ''
    with pytest.raises(ValueError, match='not in this score'):
        apply_marks(score, [dict(bar=99, tempo_bpm=0, rehearsal='', remove_words=[])])
    with pytest.raises(ValueError, match='between 0 and 400'):
        apply_marks(score, [dict(bar=1, tempo_bpm=999, rehearsal='', remove_words=[])])


def test_workspace_ai_edit_applies_layout_and_marks_with_one_text_request(tmp_path):
    path = tmp_path/'sample.aiscore.json'
    path.write_text(json.dumps(fixture()), encoding='utf-8')
    workspace = Workspace(tmp_path/'workspace')
    workspace.command('open', {'path': str(path)})
    workspace.command('remove', {'index': 0})  # exclusions must survive the edit
    before = [line.path for line in workspace.project.lines]
    requests = []
    request = 'Rehearsal A and 120 bpm at bar 1; merge rests 4-5; title Edited; make the notes blue'
    def transport(self, prompt, schema, blobs):
        requests.append(blobs)
        assert context_of(prompt)['user_request'] == request
        assert context_of(prompt)['bars'][0] == {'number': 1, 'tempo_bpm': 0, 'rehearsal': '', 'words': [], 'whole_rest': True}
        return edit_result(title='Edited', merge_rests=[[4, 5]], unsupported_requests=['make the notes blue'],
                           set_marks=[dict(bar=1, tempo_bpm=120, rehearsal='A', remove_words=[])]), {'input_tokens': 10, 'output_tokens': 5}
    with patch.object(Client, '_api', transport):
        workspace.command('ai-edit', dict(provider='OpenAI', model='gpt-6-luna', apiKey='k', text=request))
        assert settle(workspace) is None
    assert len(requests) == 1 and not requests[0]  # text only, no frames
    state = workspace.state()
    assert state['aiEdit']['marks'] == [1] and state['aiEdit']['unsupported'] == ['make the notes blue']
    assert state['title'] == 'Edited' and state['aiLayout']['merge_rests'] == [[4, 5]]
    assert 'AI edit applied: 1 bar(s) updated' in state['status']
    project = workspace.project
    assert project.ai_score['bars'][0]['rehearsal'] == 'A' and project.ai_score['bars'][0]['tempo_bpm'] == 120
    assert [line.ai_bar_ids for line in project.lines] == [[4, 5, 6, 7], [8, 9, 10]]  # first row stays excluded; 4–5 prints as one slot
    assert [line.path for line in project.lines] != before
    assert 'Not applied: make the notes blue' in project.warnings
    assert project.ai_score['edits'][0]['request'] == request
    saved = json.loads((project.directory/'project.json').read_text(encoding='utf-8'))
    assert saved['ai_score']['layout']['title'] == 'Edited'
    with patch.object(Client, '_api', transport):
        with pytest.raises(ValueError, match='Describe the change'):
            workspace.command('ai-edit', dict(provider='OpenAI', model='gpt-6-luna', apiKey='k', text='  '))


def test_ai_edit_rereads_requested_bars_from_the_video(tmp_path):
    video = tmp_path/'input.avi'
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*'MJPG'), 10, (320, 240))
    for _ in range(80):
        writer.write(np.full((240, 320, 3), 255, np.uint8))
    writer.release()
    score = fixture()
    (tmp_path/'job').mkdir()
    score.update(video_path=str(video), job_folder=str(tmp_path/'job'), frame_identity='', selected_crop=None)
    path = tmp_path/'sample.aiscore.json'
    path.write_text(json.dumps(score), encoding='utf-8')
    workspace = Workspace(tmp_path/'workspace')
    workspace.command('open', {'path': str(path)})
    reviews = []
    def transport(self, prompt, schema, blobs):
        context = context_of(prompt)
        if 'user_request' in context:
            return edit_result(reread_bars=[2]), {}
        reviews.append((context['review_only_bars'], len(blobs)))
        corrected = {**fixture()['bars'][1], 'tempo_bpm': 0, 'rehearsal': '', 'multirest': 0,
                     'events': [dict(onset=0, duration=4, staff=1, voice=1, marks='', notes=[dict(string=1, fret='3', marks='')])]}
        return dict(bars=[corrected], confirmed=[], unreadable=[], observations=['Bar 2 re-read from the video.']), {}
    with patch.object(Client, '_api', transport):
        workspace.command('ai-edit', dict(provider='OpenAI', model='gpt-6-luna', apiKey='k', text='bar 2 has a note on fret 3'))
        assert settle(workspace) is None
    assert len(reviews) == 1 and reviews[0][0] == [2] and reviews[0][1] >= 3  # broad frames around the bar's own moment
    project = workspace.project
    assert project.ai_score['bars'][1]['events'][0]['notes'][0]['fret'] == '3'
    assert 'Bar 2 re-read from the video.' in project.warnings
    assert workspace.state()['aiEdit']['reread'] == [2]
    assert (tmp_path/'job'/'frames').is_dir()
    # Without the job folder the request is refused cleanly rather than guessed.
    score.pop('job_folder')
    path.write_text(json.dumps(score), encoding='utf-8')
    workspace.command('open', {'path': str(path)})
    with patch.object(Client, '_api', transport):
        workspace.command('ai-edit', dict(provider='OpenAI', model='gpt-6-luna', apiKey='k', text='bar 2 again'))
        assert 'job folder' in settle(workspace)
