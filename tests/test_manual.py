import time

import cv2
import numpy as np
from PIL import Image
import pymupdf
import pytest

from drumscore.extract import Extraction
from drumscore.manual import append_line, new_manual_project
from drumscore.pdf import export_pdf
from drumscore.playback import PlaybackClock, VideoPlayer
from drumscore.vision import Region


def test_manual_capture_keeps_exact_top_crop_duplicates_and_click_order(tmp_path):
    # No staff lines: this must still work when automatic detection cannot.
    frame = np.full((120, 320, 3), (20, 90, 200), np.uint8)
    frame[5:20, 50:90] = (200, 40, 10)
    region = Region(.1, 0, .9, .25)
    project = new_manual_project(tmp_path, 'Manual score', 'video.mp4', region)
    append_line(project, frame, region, 8)
    append_line(project, frame, region, 2)
    append_line(project, frame, region, 2)
    reopened = Extraction.load(project.directory/'project.json')
    assert [line.time for line in reopened.lines] == [8, 2, 2]
    assert len({line.path for line in reopened.lines}) == 3
    expected = cv2.cvtColor(region.crop(frame), cv2.COLOR_BGR2RGB)
    for line in reopened.lines:
        with Image.open(reopened.directory/line.path) as image:
            assert image.size == (256, 30)
            np.testing.assert_array_equal(np.array(image), expected)
    output = tmp_path/'manual.pdf'
    export_pdf(reopened, output)
    with pymupdf.open(output) as pdf:
        assert sum(len(page.get_image_info()) for page in pdf) == 3


def test_failed_manual_save_rolls_back_line_and_file(tmp_path, monkeypatch):
    project = new_manual_project(tmp_path, 'Manual', '', Region())
    def fail():
        raise OSError('Disk full')
    monkeypatch.setattr(project, 'save', fail)
    with pytest.raises(OSError, match='Disk full'):
        append_line(project, np.zeros((40, 60, 3), np.uint8), Region(0, 0, 1, .5), 0)
    assert not project.lines
    assert not list(project.directory.glob('*.png'))
    assert project.region == Region()


def test_playback_clock_pause_speed_seek_and_replay():
    now = [0.0]
    clock = PlaybackClock(10, lambda: now[0])
    clock.play()
    now[0] = 2
    assert clock.position() == 2
    clock.set_speed(2)
    now[0] = 3
    assert clock.position() == 4
    clock.pause()
    now[0] = 8
    assert clock.position() == 4
    clock.seek(7)
    clock.play()
    now[0] = 10
    assert clock.position() == 10
    clock.play()
    assert clock.position() == 0
    with pytest.raises(ValueError):
        clock.set_speed(3)
    with pytest.raises(ValueError):
        clock.seek(float('nan'))


def wait_frame(player, predicate=lambda frame: True, timeout=5):
    deadline = time.monotonic()+timeout
    while time.monotonic() < deadline:
        frame = player.take_frame()
        if frame:
            assert not frame.error, frame.error
            if predicate(frame):
                return frame
        time.sleep(.01)
    raise AssertionError('Timed out waiting for a decoded frame')


def test_decoder_seeks_plays_reaches_end_and_releases_file(tmp_path):
    path = tmp_path/'playback.avi'
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'MJPG'), 10, (160, 100))
    assert writer.isOpened()
    for i in range(30):
        writer.write(np.full((100, 160, 3), i*7, np.uint8))
    writer.release()
    player = VideoPlayer(path, 3)
    try:
        first = wait_frame(player)
        assert first.seconds == 0
        player.seek(.4)
        player.seek(1.2)
        sought = wait_frame(player)
        assert sought.seconds == pytest.approx(1.2)
        assert abs(float(sought.image.mean())-84) < 3
        player.set_speed(2)
        player.play()
        advanced = wait_frame(player, lambda frame: frame.seconds >= 1.5)
        assert advanced.seconds > sought.seconds
        player.pause()
        assert not player.playing
        time.sleep(.05)
        assert player.take_frame() is None
        player.seek(2.8)
        wait_frame(player)
        player.play()
        ended = wait_frame(player, lambda frame: frame.ended)
        assert ended.seconds == pytest.approx(2.9)
        assert not player.playing
        player.play()
        replay = wait_frame(player)
        assert replay.seconds < 1
    finally:
        player.close()
        player.thread.join(timeout=5)
    assert not player.thread.is_alive()
    path.unlink()
