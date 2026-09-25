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
