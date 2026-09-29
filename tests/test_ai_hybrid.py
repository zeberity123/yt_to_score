import json
import time
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
import pytest

from ai_score.contracts import LINE_CHECK, validate_schema
from ai_score.hybrid import apply_line_check, extract_images, transcribe_line
from ai_score.providers import Client, Cancelled
from drumscore.editing import archive_project, edit_line, open_project
from drumscore.extract import Extraction, ScoreLine
from drumscore.pdf import export_pdf
from drumscore.server import Workspace
from drumscore.vision import Region

META = dict(title='Model guess', instrument='drums', numbered=True, first_bar=1, last_bar=0, meter=[4, 4], bpm=120,
            key_fifths=0, strings=0, crop=[0, 0, 1, 1], observations=[], source_bars_per_line=1)


def score(note=150, top=80, height=210, width=800):
    image = np.full((height, width, 3), 255, np.uint8)
    for y in range(top, top+41, 10):
        cv2.line(image, (20, y), (width-20, y), (120, 120, 120), 1)
    for x in range(25, width-10, 190):
        cv2.line(image, (x, top), (x, top+40), (0, 0, 0), 2)
    cv2.ellipse(image, (note, top+30), (7, 5), -20, 0, 360, (0, 0, 0), -1)
    cv2.line(image, (note+6, top+30), (note+6, top-25), (0, 0, 0), 2)
    return image


def make_video(path, images, repeats=12):
    h, w = images[0].shape[:2]
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'MJPG'), 6, (w, h))
    for image in images:
        for _ in range(repeats):
            writer.write(image)
    writer.release()


def finding(index, first, last, duplicate_of=0, problems=(), complete=True, confidence=1.):
    return {'index': index, 'first_bar': first, 'last_bar': last, 'complete': complete, 'duplicate_of': duplicate_of,
            'problems': list(problems), 'order_confidence': confidence}


def context_of(prompt):
    return json.loads(next(line for line in prompt.splitlines() if line.startswith('{')))


def transport_for(on_check, on_line=None):
    def transport(self, prompt, schema, images, identity):
        context = context_of(prompt)
        if 'video_title' in context:
            assert context['video_title'] == 'Given'
            return META, {}
        if 'line_index' in context:
            return on_line(self, context, images), {}
        return on_check(self, context, images), {}
    return transport


def client_for(folder):
    client = Client('Codex', 'gpt-6-astra', '', folder/'responses')
    client.auth_checked = True
    return client


@pytest.fixture(autouse=True)
def no_real_ai_calls():
    """Every transport is patched per test; an unpatched call must fail loudly, never reach a CLI or API."""
    def refuse(self, *args, **kwargs):
        raise AssertionError('Test reached a real AI transport')
    with patch.object(Client, '_codex', refuse), patch.object(Client, '_api', refuse), patch.object(Client, '_claude', refuse):
        yield


def capture_fixture(tmp_path):
    """Runs under the caller's transport patch."""
    video = tmp_path/'repeat.avi'
    make_video(video, [score(), score(400), score()])
    client = client_for(tmp_path/'job')
    project = extract_images(client, str(video), 'drums', tmp_path/'job', 'Given', 'fixture', tmp_path/'out',
                             options={'interval': .25})
    return client, project


def test_images_method_keeps_captures_checks_lines_and_round_trips(tmp_path):
    def on_check(self, context, images):
        assert len(images) == 3 and all(Path(p).name.startswith('line_') for p in images)
        assert context['meta']['numbered'] and context['lines'][0]['index'] == 1
        result = {'lines': [finding(1, 1, 4), finding(2, 5, 8, problems=['Clipped right edge']),
                            finding(3, 1, 4, duplicate_of=1, confidence=.9)],
                  'observations': ['Numbering read from printed labels.']}
        validate_schema(result, LINE_CHECK)
        return result
    with patch.object(Client, '_codex', transport_for(on_check)):
        client, project = capture_fixture(tmp_path)
    assert len(project.lines) == 3 and project.notation == 'staff' and project.ai_score is None
    assert [line.included for line in project.lines] == [True, True, False]
    assert project.lines[2].notes == ['Duplicate of line 1'] and project.lines[1].notes == ['Clipped right edge']
    assert project.lines[0].raw_source_path and project.lines[0].view >= 1  # original captures, not engravings
    assert project.ai_check['meta']['title'] == 'Given'
    assert project.ai_check['lines'][project.lines[1].path]['first_bar'] == 5
    assert any('1 duplicate lines excluded, 2 lines flagged' in w for w in project.warnings)
    assert 'Numbering read from printed labels.' in project.warnings
    assert client.usage['requests'] == 2  # one overview, one line-check batch
    reopened = open_project(archive_project(project, tmp_path/'x.drumscore'), tmp_path/'opened')
    assert reopened.ai_check['method'] == 'images' and reopened.lines[2].notes == ['Duplicate of line 1']


def test_line_check_reorders_only_on_confident_disjoint_numbering(tmp_path):
    def project():
        lines = [ScoreLine(f'l{i}.png', float(i), i) for i in (1, 2, 3)]
        return Extraction(tmp_path, 'T', '', Region(), lines, [], 'staff',
                          ai_check={'method': 'images', 'meta': {'numbered': True}, 'lines': {}, 'observations': []})
    ordered = project()
    apply_line_check(ordered, {1: finding(1, 5, 8), 2: finding(2, 1, 4), 3: finding(3, 9, 12)}, [])
    assert [line.time for line in ordered.lines] == [2, 1, 3]
    assert any('reordered' in w for w in ordered.warnings)
    unsure = project()
    apply_line_check(unsure, {1: finding(1, 5, 8), 2: finding(2, 1, 4, confidence=.5), 3: finding(3, 9, 12)}, [])
    assert [line.time for line in unsure.lines] == [1, 2, 3]
    assert unsure.lines[1].notes == ['Printed bar numbers go backwards here; check the order.']
    overlapping = project()
    apply_line_check(overlapping, {1: finding(1, 5, 8), 2: finding(2, 6, 9), 3: finding(3, 9, 12)}, [])
    assert [line.time for line in overlapping.lines] == [1, 2, 3]
    assert any('overlapping' in w for w in overlapping.warnings)


def test_cancel_during_line_check_keeps_the_captured_project(tmp_path):
    def on_check(self, context, images):
        self.cancel.set()
        raise Cancelled('test')
    with patch.object(Client, '_codex', transport_for(on_check)):
        client, project = capture_fixture(tmp_path)
    assert len(project.lines) == 3 and all(line.included for line in project.lines)
    assert any('cancelled after 0/1 batches' in w for w in project.warnings)
    assert (project.directory/'project.json').exists()


def test_transcribe_line_engraves_row_and_restore_returns_to_capture(tmp_path):
    def on_check(self, context, images):
        return {'lines': [finding(i, 4*i-3, 4*i) for i in (1, 2, 3)], 'observations': []}
    def on_line(self, context, images):
        assert context['line_index'] == 2 and context['expected_bars'] == [5, 8] and len(images) == 2
        return {'bars': [dict(number=5, meter=[4, 4], pickup=False, confidence=1., timestamp=2., issues=[], system_end=True,
                              tempo_bpm=0, rehearsal='B', multirest=0,
                              events=[dict(onset=0, duration=4, voice=1, staff=1, marks='',
                                           notes=[dict(step='C', octave=5, drum='snare', marks='')])])],
                'observations': ['Only one bar was readable.']}
    with patch.object(Client, '_codex', transport_for(on_check, on_line)):
        client, project = capture_fixture(tmp_path)
        captured = project.lines[1].path
        transcribe_line(client, project, 1)
    line = project.lines[1]
    assert line.ai_bar_ids == [5] and line.path.startswith('ai-line-') and line.original_path == captured
    assert 'Only one bar was readable.' in line.notes
    assert project.ai_check['transcribed'][line.path][0]['rehearsal'] == 'B'
    project.background = 'original'
    assert export_pdf(project, tmp_path/'mixed.pdf') >= 1  # engraved row never shows the video crop
    edit_line(project, 1, reset=True)
    assert project.lines[1].path == captured and project.lines[1].ai_bar_ids is None


def wait(workspace):
    deadline = time.monotonic()+30
    while workspace.busy and time.monotonic() < deadline:
        time.sleep(.02)
    assert not workspace.busy
    return workspace.error


def test_workspace_images_method_installs_checked_capture_and_line_edits(tmp_path):
    workspace = Workspace(tmp_path/'workspace')
    workspace.video = tmp_path/'input.mp4'
    workspace.video.write_bytes(b'fixture')
    workspace.title = 'Real title'
    directory = tmp_path/'captured'
    directory.mkdir()
    for name in ('a.png', 'b.png', 'c.png'):
        cv2.imwrite(str(directory/name), score())
    def fake(client, video, instrument, folder, title, source, output_dir, selected_crop=None, options=None):
        assert instrument == 'drums' and title == 'Real title' and options['interval'] == '0.25'
        lines = [ScoreLine('a.png', 0., 1, notes=[]), ScoreLine('b.png', 2., 2, included=False, notes=['Duplicate of line 1']),
                 ScoreLine('c.png', 4., 3, notes=['Clipped'])]
        project = Extraction(directory, title, source, Region(), lines, ['AI check: 1 duplicate lines excluded, 2 lines flagged.'], 'staff',
                             ai_check={'method': 'images', 'meta': dict(META, title=title), 'lines': {}, 'observations': [],
                                       'usage': dict(client.usage), 'job_folder': str(folder), 'source_id': 'x'})
        project.save()
        return project
    with patch('ai_score.hybrid.extract_images', side_effect=fake):
        workspace.command('ai-extract', dict(provider='OpenAI', model='gpt-6-luna', apiKey='k', instrument='drums',
                                             method='images', interval='0.25'))
        assert wait(workspace) is None
    state = workspace.state()
    assert state['mode'] == 'ai' and state['ai'] is False and state['aiCheck']['flagged'] == 1
    assert len(state['lines']) == 2 and state['canUndo']  # the duplicate is removed but recoverable
    assert state['lines'][1]['notes'] == ['Clipped']
    def transport(self, prompt, schema, blobs):
        context = context_of(prompt)
        assert context['user_request'] == 'drop line 2' and context['lines'][0]['first_bar'] == 0
        return {'exclude_lines': [2], 'move_line': [], 'retranscribe_lines': [], 'notes': ['Line 2 excluded as requested.'],
                'unsupported_requests': ['recolor']}, {}
    with patch.object(Client, '_api', transport):
        workspace.command('ai-edit', dict(provider='OpenAI', model='gpt-6-luna', apiKey='k', text='drop line 2'))
        assert wait(workspace) is None
    state = workspace.state()
    assert len(state['lines']) == 1 and state['aiEdit']['unsupported'] == ['recolor']
    assert 'Line 2 excluded as requested.' in state['warnings'] and 'Not applied: recolor' in state['warnings']
    with patch('ai_score.hybrid.transcribe_line', side_effect=lambda client, project, index: project.lines[index]) as call:
        workspace.command('ai-line-transcribe', dict(provider='OpenAI', model='gpt-6-luna', apiKey='k', index=0))
        assert wait(workspace) is None
        assert call.call_count == 1 and 'Line 1 engraved' in workspace.state()['status']
