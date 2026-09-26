from pathlib import Path
import threading

import cv2
import numpy as np
from PIL import Image
import pytest

from drumscore.editing import archive_project, edit_line, open_project
from drumscore.extract import extract
from drumscore.free import text_mask, text_rows, row_signature, text_difference
from drumscore.pdf import export_pdf
from drumscore.server import Workspace
from drumscore.video import Cancelled
from drumscore.vision import Region


def overlay(rows, phase=0):
    frame = np.full((360, 960, 3), (120, 145, 160), np.uint8)
    # Bright moving footage must not become a lyric row or a new view.
    cv2.rectangle(frame, (600+phase*4, 0), (850+phase*4, 355), (240, 240, 240), -1)
    for i, text in enumerate(rows):
        color = (245, 150, 0) if i % 2 == 0 else (255, 255, 255)
        baseline = (12, 60+i*80)
        glyph = np.zeros(frame.shape[:2], np.uint8)
        cv2.putText(glyph, text, baseline, cv2.FONT_HERSHEY_SIMPLEX, 1.5, 255, 4, cv2.LINE_AA)
        outline = cv2.dilate(glyph, np.ones((11, 11), np.uint8))
        frame[outline > 0] = 0
        frame[glyph > 120] = color
    return frame


def video(path, pages):
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'MJPG'), 6, (960, 360))
    assert writer.isOpened()
    for rows in pages:
        for phase in range(12):
            writer.write(overlay(rows, phase))
    writer.release()
    return path


@pytest.mark.parametrize('rows', [['Am7'], ['Am7', 'G / E7'], ['Am7 G /', 'First lyric', 'Dm7 E7 /', 'Next lyric']])
def test_free_detects_variable_rows_and_preserves_color(tmp_path, rows):
    path = video(tmp_path/'text.avi', [rows])
    result = extract(path, tmp_path, region=Region(), mode='free', interval=.25)
    assert len(result.lines) == len(rows)
    assert result.notation == 'free'
    image = np.array(Image.open(result.directory/result.lines[0].path))
    assert image.ndim == 3 and np.any(image[:, :, 2].astype(int)-image[:, :, 0] > 100)
    assert all(line.crop[0] == 0 and line.crop[2] == 1 for line in result.lines)
    assert [line.crop[1] for line in result.lines] == sorted(line.crop[1] for line in result.lines)


def test_free_changes_repeats_overlap_and_blank_intervals(tmp_path):
    a, b, c = 'Am7 G /', 'Dm7 E7 /', 'FM7 C /'
    path = video(tmp_path/'changes.avi', [[a,b], [b,c], [a,b], [], [a,b]])
    result = extract(path, tmp_path, region=Region(), mode='free', interval=.25)
    assert len(result.lines) == 7
    assert [line.view for line in result.lines] == [1,1,2,3,3,4,4]
    assert any('Removed 1 matching' in warning for warning in result.warnings)
    kept = extract(path, tmp_path, region=Region(), mode='free', interval=.25, remove_overlap=False)
    assert len(kept.lines) == 8


def test_free_roundtrip_edit_export_and_mode_isolation(tmp_path):
    path = video(tmp_path/'text.avi', [['Am7 G /', 'Lyrics']])
    result = extract(path, tmp_path, region=Region(), mode='free', interval=.25)
    original = np.array(Image.open(result.directory/result.lines[0].path))
    edit_line(result, 0, [0, 0, 1, .5])
    edit_line(result, 0, reset=True)
    assert np.array_equal(np.array(Image.open(result.directory/result.lines[0].path)), original)
    archive = tmp_path/'free.drumscore'
    archive_project(result, archive)
    restored = open_project(archive, tmp_path/'opened')
    assert restored.notation == 'free'
    assert export_pdf(restored, tmp_path/'free.pdf') == 1
    workspace = Workspace(tmp_path/'workspace')
    workspace.command('open', {'path': str(archive)})
    assert workspace.mode == workspace.notation == 'free'
    workspace.command('remove', {'index': 0})
    workspace.command('mode', {'mode': 'automatic'})
    assert workspace.project is None and not workspace.state()['canUndo']
    workspace.command('mode', {'mode': 'manual'})
    assert workspace.project is None
    workspace.command('mode', {'mode': 'free'})
    workspace.command('undo', {})
    assert len(workspace.project.lines) == 2


def test_free_requires_region_valid_range_and_honors_cancel(tmp_path):
    with pytest.raises(ValueError, match='rectangle'):
        extract('unused', tmp_path, mode='free')
    path = video(tmp_path/'text.avi', [['Am7']])
    with pytest.raises(ValueError, match='start/end'):
        extract(path, tmp_path, mode='free', region=Region(), start=2, end=1)
    with pytest.raises(ValueError, match='interval'):
        extract(path, tmp_path, mode='free', region=Region(), interval=0)
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(Cancelled):
        extract(path, tmp_path, mode='free', region=Region(), cancel=cancel)


def test_user_sample_has_four_rows():
    path = Path(__file__).resolve().parents[1]/'screen_sample/test1.png'
    if not path.exists():
        pytest.skip('Local user reference image is not bundled.')
    assert len(text_rows(text_mask(cv2.imread(str(path))))) == 4


def test_background_highlight_does_not_hide_a_real_chord_change():
    frames = [overlay(['Am7 G /']), overlay(['Am7 G /']), overlay(['Am7 E7 /'])]
    # A high-contrast white patch adjacent to blue text can pass the outline
    # filter. It must not change the blue row's scale or create a new view.
    cv2.rectangle(frames[1], (200, 10), (250, 27), (0, 0, 0), -1)
    cv2.rectangle(frames[1], (207, 17), (243, 20), (255, 255, 255), -1)
    signatures = []
    for frame in frames:
        mask = text_mask(frame)
        signatures.append(row_signature(mask, text_rows(mask)[0]))
    assert text_difference(signatures[0], signatures[1]) < .035
    assert text_difference(signatures[0], signatures[2]) > .035
