import json
from zipfile import ZipFile

import cv2
import numpy as np
from PIL import Image
import pytest

from drumscore.editing import archive_project, edit_line, open_project, safe_name
from drumscore.extract import Extraction, ScoreLine
from drumscore.manual import append_line, new_manual_project
from drumscore.vision import Region


def test_crop_can_expand_after_save_reopen_and_reset(tmp_path):
    frame = np.random.default_rng(4).integers(0, 255, (100, 200, 3), dtype=np.uint8)
    project = new_manual_project(tmp_path, 'My practice score', '', Region())
    append_line(project, frame, Region(.2, .3, .8, .6), 4)
    original = project.lines[0].path
    edit_line(project, 0, [.1, .2, .9, .8])
    with Image.open(project.directory/project.lines[0].path) as image:
        np.testing.assert_array_equal(np.array(image), cv2.cvtColor(frame[20:80,20:180], cv2.COLOR_BGR2RGB))
    bundle = archive_project(project, tmp_path/'My practice score.drumscore')
    reopened = open_project(bundle, tmp_path/'reopened')
    edit_line(reopened, 0, [0, 0, 1, 1])
    with Image.open(reopened.directory/reopened.lines[0].path) as image:
        assert image.size == (200, 100)
    edit_line(reopened, 0, reset=True)
    assert reopened.lines[0].path == original
    assert reopened.lines[0].crop == [.2, .3, .8, .6]
    with Image.open(reopened.directory/original) as image:
        assert image.size == (120, 30)


def test_edit_failure_does_not_replace_line_or_leave_image(tmp_path, monkeypatch):
    project = new_manual_project(tmp_path, 'Score', '', Region())
    append_line(project, np.zeros((40,80,3), np.uint8), Region(), 0)
    original = project.lines[0].path
    def fail():
        raise OSError('Disk full')
    monkeypatch.setattr(project, 'save', fail)
    with pytest.raises(OSError):
        edit_line(project, 0, [.1,.1,.9,.9])
    assert project.lines[0].path == original
    assert not list(project.directory.glob('edit_*.png'))


def test_legacy_project_edits_use_original_image(tmp_path):
    Image.new('RGB', (200,100), 'white').save(tmp_path/'line.png')
    project = Extraction(tmp_path, 'Legacy', '', Region(), [ScoreLine('line.png',0,1)], [])
    project.save()
    data = json.loads((tmp_path/'project.json').read_text())
    data['lines'] = [{'path':'line.png','time':0,'view':1,'included':True}]
    (tmp_path/'project.json').write_text(json.dumps(data))
    project = open_project(tmp_path/'project.json', tmp_path)
    edit_line(project, 0, [.2,.2,.8,.8])
    edit_line(project, 0, [0,0,1,1])
    with Image.open(tmp_path/project.lines[0].path) as image:
        assert image.size == (200,100)
    edit_line(project, 0, reset=True)
    assert project.lines[0].path == 'line.png'


@pytest.mark.parametrize('name', ['../escape.png', 'C:\\escape.png', 'folder/image.png'])
def test_archive_rejects_unsafe_paths(tmp_path, name):
    bundle = tmp_path/'bad.drumscore'
    with ZipFile(bundle, 'w') as archive:
        archive.writestr(name, 'bad')
    with pytest.raises(ValueError, match='path'):
        open_project(bundle, tmp_path/'imports')


def test_title_filename_retains_unicode_and_handles_windows_names():
    assert safe_name('연습곡 / Song?') == '연습곡 _ Song_'
    assert safe_name('CON') == '_CON'
    assert safe_name('...') == 'Sheet music'
