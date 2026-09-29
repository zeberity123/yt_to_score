import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import numpy as np
import pytest

from drumscore.manual import append_line, new_manual_project
from drumscore.server import make_server
from drumscore.vision import Region


@pytest.fixture
def server(tmp_path):
    instance = make_server(output=tmp_path)
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    yield instance
    instance.shutdown()
    instance.server_close()
    thread.join()


def request(server, path, data=None, token=True, headers=None):
    header = {'X-Session-Token':server.token} if token else {}
    header.update(headers or {})
    return urlopen(Request(f'http://127.0.0.1:{server.server_port}{path}',
                           data=json.dumps(data).encode() if data else None, headers=header))


def test_api_auth_and_static_path_boundaries(server):
    with pytest.raises(HTTPError) as error:
        request(server, '/api/state', token=False)
    assert error.value.code == 403
    with request(server, '/api/state') as response:
        assert json.load(response)['lines'] == []
    with pytest.raises(HTTPError) as error:
        request(server, '/%2e%2e/drumscore/server.py', token=False)
    assert error.value.code == 404


def settle(workspace):
    import time
    deadline = time.monotonic()+30
    while workspace.busy and time.monotonic() < deadline:
        time.sleep(.02)
    assert not workspace.busy and not workspace.error, workspace.error


def test_capture_modes_and_open_routing(server, tmp_path):
    workspace = server.workspace
    assert set(workspace.projects) == {'automatic', 'ai', 'manual'}
    workspace.command('mode', {'mode': 'ai'})
    assert workspace.state()['mode'] == 'ai' and not workspace.state()['canUndo']
    workspace.command('mode', {'mode': 'free'})  # older UI alias for chord capture
    assert workspace.mode == 'automatic'
    with pytest.raises(ValueError, match='Unknown capture mode'):
        workspace.command('mode', {'mode': 'hybrid'})
    manual = new_manual_project(workspace.output, 'Manual', '', Region())
    append_line(manual, np.full((80, 160, 3), 255, np.uint8), Region(), 1)
    workspace.command('open', {'path': str(manual.directory/'project.json')})
    assert workspace.mode == 'manual' and len(workspace.project.lines) == 1
    workspace.video = tmp_path/'video.mp4'
    workspace.video.write_bytes(b'fixture')
    with pytest.raises(ValueError, match='Choose Automatic mode'):
        workspace.command('extract', {'notation': 'staff'})


def test_extract_action_maps_chord_to_text_capture(server, tmp_path):
    from unittest.mock import patch
    workspace = server.workspace
    workspace.video = tmp_path/'video.mp4'
    workspace.video.write_bytes(b'fixture')
    calls = []
    def fake(path, output, title, source, region, **options):
        calls.append(options)
        return new_manual_project(output, title, source, region)
    with patch('drumscore.server.extract', fake):
        workspace.command('extract', {'notation': 'chord', 'interval': .5, 'timingRepeats': True, 'bpm': None})
        settle(workspace)
        workspace.command('extract', {'notation': 'bass', 'bpm': 120, 'beatsPerBar': 3})
        settle(workspace)
    assert calls[0]['mode'] == 'free' and calls[0]['notation'] == 'free' and calls[0]['timing_repeats'] and calls[0]['bpm'] is None
    assert calls[1]['mode'] == 'auto' and calls[1]['notation'] == 'bass' and calls[1]['bpm'] == 120 and calls[1]['beats_per_bar'] == 3
    assert workspace.mode == 'automatic' and workspace.state()['notation'] == 'bass'
    assert workspace.projects['automatic'] is not None and workspace.projects['ai'] is None


def test_instrument_restored_from_project_and_invalid_mode_rejected(server):
    workspace=server.workspace
    project=new_manual_project(workspace.output,'Piano','',Region())
    project.notation='piano'
    append_line(project,np.full((80,160,3),255,np.uint8),Region(),0)
    workspace.command('open',{'path':str(project.directory/'project.json')})
    assert workspace.state()['notation']=='piano'
    assert workspace.mode=='manual'  # hand-picked frames open in Manual
    workspace.command('mode',{'mode':'automatic'})
    workspace.notation='bass'
    workspace.command('mode',{'mode':'manual'})
    assert workspace.state()['notation']=='piano'
    with pytest.raises(ValueError,match='Unknown notation'):
        workspace.command('load',{'source':'unused','notation':'invalid'})


def test_duplicate_api_inserts_after_selection_and_invalidates_preview(server):
    workspace=server.workspace
    project=new_manual_project(workspace.output,'Repeat','',Region())
    workspace.projects['manual']=project
    workspace.mode='manual'
    for time in (4,42,59):
        append_line(project,np.full((80,160,3),255,np.uint8),Region(),time)
    workspace.print_preview={'id':'old'}
    with request(server,'/api/command',{'action':'duplicate','index':1}) as response:
        assert json.load(response)['ok']
    assert [line.time for line in project.lines]==[4,42,42,59]
    assert workspace.print_preview is None
    assert project.lines[1].path != project.lines[2].path
    workspace.command('remove',{'index':2})
    workspace.command('undo',{})
    assert [line.time for line in project.lines]==[4,42,42,59]
    with pytest.raises(ValueError,match='Select a score'):
        workspace.command('duplicate',{'index':-1})


def test_original_image_endpoint_uses_preserved_color_pixels(server):
    import io
    from PIL import Image
    from drumscore.extract import ScoreLine
    workspace=server.workspace
    project=new_manual_project(workspace.output,'Colors','',Region())
    project.notation='bass'
    Image.new('RGB',(200,80),'white').save(project.directory/'clean.png')
    Image.new('RGB',(200,80),(20,60,90)).save(project.directory/'raw.png')
    project.lines=[ScoreLine('clean.png',0,1,raw_source_path='raw.png',crop=[0,0,1,1])]
    workspace.projects['automatic']=project
    assert workspace.state()['originalMissing']==0
    workspace.command('background',{'background':'original'})
    with request(server,'/api/image?index=0') as response:
        image=Image.open(io.BytesIO(response.read()))
        assert image.getpixel((50,20))==(20,60,90)
    project.lines[0].raw_source_path=None
    assert workspace.state()['originalMissing']==1


def test_edit_and_range_requests_and_archive_download(server):
    workspace = server.workspace
    workspace.projects['manual'] = new_manual_project(workspace.output, 'Named score', '', Region())
    workspace.mode = 'manual'
    append_line(workspace.project, np.full((80,160,3), 255, np.uint8), Region(.2,.2,.8,.8), 0)
    with request(server, '/api/command', {'action':'edit','index':0,'crop':[0,0,1,1]}) as response:
        assert json.load(response)['ok']
    with request(server, '/api/image?index=0', headers={'Range':'bytes=0-7'}) as response:
        assert response.status == 206
        assert response.read() == b'\x89PNG\r\n\x1a\n'
    with request(server, '/api/command', {'action':'save','title':'My song'}) as response:
        assert response.status == 200
    import time
    deadline = time.monotonic()+5
    while workspace.busy and time.monotonic()<deadline:
        time.sleep(.01)
    assert not workspace.error
    key, artifact = next(iter(workspace.artifacts.items()))
    assert artifact['name'] == 'My song.drumscore'
    with request(server, f'/api/download?id={key}') as response:
        assert 'My%20song.drumscore' in response.headers['Content-Disposition']
        assert response.read().startswith(b'PK')
    deadline = time.monotonic()+2
    while key in workspace.artifacts and time.monotonic()<deadline:
        time.sleep(.01)
    assert key not in workspace.artifacts
    assert not (workspace.output/'exports'/key).exists()
    assert workspace.project.directory.exists()
    assert not list(workspace.output.rglob('*.tmp'))


def test_remove_and_undo_preserve_order_images_and_project_isolation(server):
    workspace = server.workspace
    project = new_manual_project(workspace.output, 'Removal', '', Region())
    workspace.projects['manual'] = project
    workspace.mode = 'manual'
    for time in range(3):
        append_line(project, np.full((80,160,3), 255, np.uint8), Region(), time)
    original = project.lines.copy()
    workspace.command('remove', {'index':1})
    workspace.command('remove', {'index':1})
    assert project.lines == original[:1]
    assert workspace.state()['canUndo']
    assert len(json.loads((project.directory/'project.json').read_text())['lines']) == 1
    workspace.command('mode', {'mode':'automatic'})
    assert not workspace.state()['canUndo']
    workspace.command('mode', {'mode':'manual'})
    workspace.command('undo', {})
    workspace.command('undo', {})
    assert project.lines == original
    assert not workspace.state()['canUndo']
    for line in original:
        assert (project.directory/line.path).exists()


def test_failed_project_save_cleans_tmp_and_rolls_back_removal(server, monkeypatch):
    from pathlib import Path
    workspace = server.workspace
    project = new_manual_project(workspace.output, 'Failure', '', Region())
    workspace.projects['manual'] = project
    workspace.mode = 'manual'
    append_line(project, np.full((80,160,3), 255, np.uint8), Region(), 0)
    old = (project.directory/'project.json').read_bytes()
    def fail_replace(*args):
        raise PermissionError('File locked')
    monkeypatch.setattr(Path, 'replace', fail_replace)
    with pytest.raises(PermissionError):
        workspace.command('remove', {'index':0})
    assert len(project.lines) == 1
    assert not workspace.state()['canUndo']
    assert (project.directory/'project.json').read_bytes() == old
    assert not (project.directory/'project.tmp').exists()


def test_old_exclusions_are_hidden_and_can_be_undone(server):
    workspace = server.workspace
    project = new_manual_project(workspace.output, 'Older project', '', Region())
    for time in range(4):
        append_line(project, np.full((80,160,3), 255, np.uint8), Region(), time)
    project.lines[1].included = project.lines[2].included = False
    project.save()
    workspace.command('open', {'path':str(project.directory/'project.json')})
    assert [line.time for line in workspace.project.lines] == [0,3]
    workspace.command('undo', {})
    workspace.command('undo', {})
    assert [line.time for line in workspace.project.lines] == [0,1,2,3]
    assert all(line.included for line in workspace.project.lines)


def test_upload_preserves_title_and_invalid_bundle_returns_error(server):
    from pathlib import Path
    with urlopen(Request(f'http://127.0.0.1:{server.server_port}/api/upload', data=b'not a zip',
                         headers={'X-Session-Token':server.token, 'X-Filename':'My%20practice.drumscore'})) as response:
        path = json.load(response)['path']
    assert Path(path).name == 'My practice.drumscore'
    with pytest.raises(HTTPError) as error:
        request(server, '/api/command', {'action':'open','path':path})
    assert error.value.code == 400
    assert 'zip' in json.load(error.value)['error'].lower()


def test_print_exception_rejects_stale_anchor_and_rolls_back_failed_save(server,monkeypatch):
    from test_print_layout import project_at
    from drumscore.print_layout import print_rows
    workspace=server.workspace
    project=project_at(workspace.output/'tabs')
    project.bars_per_line=6
    workspace.projects[workspace.mode]=project
    anchor=print_rows(project)[0][0].anchor
    workspace.print_preview={'anchors':[anchor]}
    with pytest.raises(ValueError):workspace.command('print-line-bars',{'anchor':'stale','bars':3})
    with pytest.raises(ValueError):workspace.command('print-line-bars',{'anchor':anchor,'bars':17})
    assert project.bar_overrides=={}
    def fail():raise OSError('Disk full')
    with monkeypatch.context() as patch:
        patch.setattr(project,'save',fail)
        with pytest.raises(OSError):workspace.command('print-line-bars',{'anchor':anchor,'bars':3})
    assert project.bar_overrides=={}
    assert workspace.print_preview is not None
    workspace.command('print-line-bars',{'anchor':anchor,'bars':3})
    assert project.bar_overrides=={anchor:3}
    assert workspace.print_preview is None
    workspace.print_preview={'anchors':[anchor]}
    workspace.command('print-line-bars',{'anchor':anchor,'bars':0})
    assert project.bar_overrides=={}
