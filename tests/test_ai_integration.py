import copy
import json
import time
from pathlib import Path
from unittest.mock import patch

from ai_score.contracts import default_format, printed_slots
from drumscore.ai_workspace import create_project, export_ai, update_layout
from drumscore.editing import archive_project, open_project, duplicate_line
from drumscore.server import Workspace


def fixture():
    bars = []
    for number in range(1, 11):
        bars.append(dict(number=number, meter=[4, 4], pickup=False, confidence=1., timestamp=number,
                         system_end=number in (3, 7, 10), issues=[], events=[dict(onset=0, duration=4,
                         staff=1, voice=1, notes=[], marks='')]))
    return dict(meta=dict(title='Original rows', instrument='bass', strings=4, bpm=120, meter=[4, 4],
                          source_bars_per_line=0, first_bar=1, last_bar=10),
                bars=bars, layout=default_format('Original rows', 0), review=[])


def test_source_rows_and_explicit_override():
    score = fixture()
    assert [len(row) for row in printed_slots(score, score['layout'])] == [3, 4, 3]
    score['layout']['bars_per_line'] = 4
    assert [len(row) for row in printed_slots(score, score['layout'])] == [4, 4, 2]


def test_integrated_project_archive_reorder_duplicate_and_footer(tmp_path):
    import pymupdf
    project = create_project(fixture(), tmp_path/'project', 'test-source')
    assert [line.ai_bar_ids for line in project.lines] == [[1, 2, 3], [4, 5, 6, 7], [8, 9, 10]]
    duplicate_line(project, 0)
    project.lines.pop(2)  # Remove original second source row.
    project.lines.reverse()
    update_layout(project, dict(title='My score', subtitle='My subtitle', song_info='4/4 | Bass',
                               show_metadata=True, footer='Technique legend\nSource note'))
    archive = tmp_path/'test.drumscore'
    archive_project(project, archive)
    reopened = open_project(archive, tmp_path/'opened')
    assert reopened.ai_score
    assert [line.ai_bar_ids for line in reopened.lines] == [[8, 9, 10], [1, 2, 3], [1, 2, 3]]
    pdf = tmp_path/'out.pdf'
    export_ai(reopened, pdf)
    with pymupdf.open(pdf) as doc:
        text = doc[0].get_text()
        assert all(value in text for value in ('My score', 'My subtitle', '4/4 | Bass', 'Technique legend', 'Source note'))
        assert not doc[0].get_images()
    update_layout(reopened, dict(bars_per_line=4))
    assert [line.ai_bar_ids for line in reopened.lines] == [[8, 9, 10, 1], [2, 3, 1, 2], [3]]


def test_rest_merge_toggle_round_trips_rows(tmp_path):
    project = create_project(fixture(), tmp_path/'rests', 'test-source')  # every bar is a whole rest
    update_layout(project, dict(bars_per_line=4, merge_rests_auto=True))
    assert [line.ai_bar_ids for line in project.lines] == [list(range(1, 11))]
    update_layout(project, dict(bars_per_line=4, merge_rests_auto=False))
    assert [line.ai_bar_ids for line in project.lines] == [[1, 2, 3, 4], [5, 6, 7, 8], [9, 10]]
    update_layout(project, dict(bars_per_line=0))
    assert [line.ai_bar_ids for line in project.lines] == [[1, 2, 3], [4, 5, 6, 7], [8, 9, 10]]


def wait(workspace):
    deadline = time.monotonic()+30
    while workspace.busy and time.monotonic() < deadline:
        time.sleep(.02)
    assert not workspace.busy
    assert not workspace.error, workspace.error


def test_workspace_import_preview_save_and_export_without_ai_request(tmp_path):
    score = fixture()
    path = tmp_path/'sample.aiscore.json'
    path.write_text(json.dumps(score), encoding='utf-8')
    workspace = Workspace(tmp_path/'workspace')
    workspace.command('open', {'path': str(path)})
    state = workspace.state()
    assert state['ai'] and len(state['lines']) == 3
    assert state['mode'] == 'ai' and workspace.projects['ai'] is workspace.project
    with patch('ai_score.providers.Client.request', side_effect=AssertionError('No AI calls for page formatting')):
        workspace.command('ai-preview', {'layout': {'footer': 'Test footer', 'title': 'Preview title'}})
        wait(workspace)
        assert workspace.state()['printPreview']['pages']
        assert workspace.print_images[0].startswith(b'\x89PNG')
        workspace.command('export', {'title': 'Export title', 'aiLayout': {'title': 'Export title', 'footer': ''}})
        wait(workspace)
        assert Path(next(iter(workspace.artifacts.values()))['path']).exists()


def test_chord_lyrics_render_and_round_trip(tmp_path):
    score = {'meta': {'instrument': 'chord', 'title': 'Song', 'meter': [], 'bpm': 0}, 'bars': [],
             'lead_lines': [{'number': 1, 'timestamp': 2, 'section': 'Verse', 'confidence': 1., 'issues': [],
                             'segments': [{'chord': 'Am7', 'lyric': 'Hello '}, {'chord': 'D/F#', 'lyric': 'world'}]}],
             'layout': default_format('Song', 0), 'review': []}
    project = create_project(score, tmp_path/'chords', 'fixture')
    assert len(project.lines) == 1 and project.notation == 'chord'
    export_ai(project, tmp_path/'chords.pdf')
    import pymupdf
    with pymupdf.open(tmp_path/'chords.pdf') as doc:
        text = doc[0].get_text()
        assert 'Am7' in text and 'D/F#' in text and 'Hello' in text and 'world' in text


def test_ai_extract_bridge_preserves_request_and_keeps_key_private(tmp_path):
    workspace = Workspace(tmp_path/'workspace')
    workspace.video = tmp_path/'input.mp4'
    workspace.video.write_bytes(b'fixture')
    workspace.source = 'local fixture'
    workspace.title = 'Real video title'
    def extract(client, source, instrument, folder, **options):
        assert client.key == 'secret-key-not-for-project'
        assert client.max_requests is None and client.budget is None
        assert instrument == 'bass'
        assert options['bars_per_line'] == 0
        assert options['instructions'] == 'Title on first page only'
        assert options['title'] == 'Real video title'  # yt-dlp title, not the cached file stem
        return None, None, fixture()
    with patch('ai_score.pipeline.extract', side_effect=extract):
        workspace.command('ai-extract', dict(provider='OpenAI', model='gpt-6-luna',
                          apiKey='secret-key-not-for-project', instrument='bass', bars=0,
                          instructions='Title on first page only'))
        wait(workspace)
    assert workspace.state()['ai'] and len(workspace.project.lines) == 3
    assert workspace.mode == 'ai' and workspace.projects['automatic'] is None
    assert 'secret-key-not-for-project' not in json.dumps(workspace.state())
    assert 'secret-key-not-for-project' not in (workspace.project.directory/'project.json').read_text()


def test_staff_previews_in_successive_worker_threads(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    import verovio  # Import on the main thread, then render elsewhere.
    for instrument in ('piano', 'drums', 'piano'):
        score = fixture()
        score['meta'].update(instrument=instrument, key_fifths=0)
        if instrument == 'piano':
            for bar in score['bars']:
                bar['events'].append({**bar['events'][0], 'staff': 2})
        with ThreadPoolExecutor(max_workers=1) as pool:
            project = pool.submit(create_project, score, tmp_path/instrument, 'fixture').result()
            assert len(project.lines) == 3


def test_cancel_opens_completed_draft_and_reports_real_batch_progress(tmp_path):
    import threading
    from ai_score.providers import check_cancel
    workspace = Workspace(tmp_path/'workspace')
    workspace.video = tmp_path/'input.mp4'
    workspace.video.write_bytes(b'fixture')
    prepared = threading.Event()
    def extract(client, source, instrument, folder, **options):
        assert options['selected_crop'] == [0, .7, 1, 1]
        client.partial_score = fixture()
        client.partial_score['bars'] = client.partial_score['bars'][:3]
        client.partial_score['conflicts'] = [2]
        client.progress('Transcribing score', 2, 19, 3)
        client.log('Reusing a completed AI response')
        prepared.set()
        client.cancel.wait(5)
        check_cancel(client.cancel)
    with patch('ai_score.pipeline.extract', side_effect=extract):
        workspace.command('ai-extract', dict(provider='Codex', instrument='bass', crop=[0, .7, 1, 1]))
        assert prepared.wait(5)
        state = workspace.state()
        assert '2/19 batches completed' in state['status']
        assert state['progress'] == 2/19
        workspace.command('cancel', {})
        assert 'Cancelling' in workspace.state()['status']
        wait(workspace)
    assert 'Cancelled.' in workspace.state()['status']
    assert workspace.project.ai_score['partial']
    assert workspace.project.lines[0].ai_bar_ids == [1, 2, 3]
    assert 'INCOMPLETE DRAFT' in workspace.project.ai_score['layout']['subtitle']
    assert any('conflicting' in issue for issue in workspace.project.warnings)
    assert any('Missing bars: 4' in issue for issue in workspace.project.warnings)
    assert next(workspace.output.glob('ai-jobs/*/cancelled-draft.aiscore.json')).exists()
    assert workspace.state()['elapsedSeconds'] > 0


def test_cancel_before_first_batch_does_not_open_stale_checkpoint(tmp_path):
    from ai_score.providers import Cancelled
    workspace = Workspace(tmp_path)
    workspace.video = tmp_path/'input.mp4'
    workspace.video.write_bytes(b'fixture')
    def extract(client, source, instrument, folder, **options):
        folder.mkdir(parents=True, exist_ok=True)
        (folder/'checkpoint.json').write_text(json.dumps(fixture()), encoding='utf-8')
        client.cancel.set()
        raise Cancelled('test')
    with patch('ai_score.pipeline.extract', side_effect=extract):
        workspace.command('ai-extract', dict(provider='Codex', instrument='bass'))
        wait(workspace)
    assert not workspace.state()['lines']
    assert 'before any complete score batches' in workspace.state()['status']


def test_claude_subscription_transport_and_expired_login(tmp_path):
    import io
    import pytest
    from ai_score.contracts import FORMAT
    from ai_score.providers import Client
    layout = default_format('Claude fixture')
    response = dict(type='result', structured_output=layout, usage=dict(
                    input_tokens=80, cache_read_input_tokens=20, output_tokens=30))
    class Process:
        returncode = 0
        def __init__(self, command, **options):
            assert command[command.index('--output-format')+1] == 'stream-json'
            assert '--verbose' in command and '--restricted' in command
            assert command[command.index('--tools')+1] == ''
            assert 'ANTHROPIC_API_KEY' not in options['env']
            self.stdin = io.BytesIO()
            options['stdout'].write((json.dumps(response)+'\n').encode())
        def poll(self): return self.returncode
        def wait(self, **kwargs): return self.returncode
    with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'must-not-use'}), \
         patch('ai_score.providers.claude_login_status', return_value='Signed in'), \
         patch('ai_score.providers.claude_executable', return_value='claude.exe'), \
         patch('ai_score.providers.subprocess.Popen', Process):
        client = Client('Claude CLI', 'sonnet', '', tmp_path)
        assert client.request('Read the fixture', FORMAT) == layout
        assert client.usage['subscription'] and client.usage['estimated_usd'] == 0
        assert client.usage['input_tokens'] == 100
        response.clear()
        response.update(type='result', result='OAuth session expired; failed to authenticate', is_error=True)
        with pytest.raises(RuntimeError, match='claude auth login'):
            client.request('Different request', FORMAT)
