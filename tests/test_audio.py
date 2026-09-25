import os
from pathlib import Path
import subprocess

import numpy as np
import pytest
import yt_dlp

from drumscore.server import Workspace
from drumscore.video import audio_codec, download, ffmpeg_path, metadata


def ffmpeg(*args):
    return subprocess.run([ffmpeg_path(), '-hide_banner', '-loglevel', 'error', *map(str, args)],
                          check=True, capture_output=True, timeout=30,
                          creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0).stdout


def make_clip(path, video_codec='libx264', sound_codec='aac'):
    inputs = ['-f', 'lavfi', '-i', 'testsrc2=size=320x180:rate=10']
    if sound_codec:
        inputs += ['-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=44100']
    options = ['-c:v', video_codec]
    if sound_codec:
        options += ['-c:a', sound_codec]
    ffmpeg('-y', *inputs, '-t', '1.5', *options, path)


def assert_audible(path):
    samples = ffmpeg('-i', path, '-map', '0:a:0', '-t', '0.5', '-ac', '1', '-ar', '8000', '-f', 's16le', '-')
    assert np.frombuffer(samples, dtype='<i2').std() > 100


@pytest.mark.parametrize('sound', ['pcm_s16le', None])
def test_converted_preview_preserves_audio_and_accepts_silent_video(tmp_path, sound):
    source = tmp_path/'source.mkv'
    make_clip(source, video_codec='mpeg4', sound_codec=sound)
    workspace = Workspace(tmp_path/'output')
    result = workspace.browser_media(source, audio_codec(source))
    assert result != source
    assert '-preview-av' in result.name
    assert audio_codec(result) == ('aac' if sound else None)
    assert metadata(result) == pytest.approx(metadata(source))
    if sound:
        assert_audible(result)
    modified = result.stat().st_mtime_ns
    assert workspace.browser_media(source, audio_codec(source)) == result
    assert result.stat().st_mtime_ns == modified


def test_compatible_mp4_needs_no_conversion(tmp_path):
    source = tmp_path/'source.mp4'
    make_clip(source)
    workspace = Workspace(tmp_path/'output')
    assert audio_codec(source) == 'aac'
    assert workspace.browser_media(source, 'aac') == source
    assert_audible(source)


def test_audio_only_conversion_copies_video_bitstream(tmp_path):
    source = tmp_path/'source.mp4'
    make_clip(source, sound_codec='alac')
    workspace = Workspace(tmp_path/'output')
    assert audio_codec(source) == 'alac'
    result = workspace.browser_media(source, 'alac')
    assert result != source
    assert audio_codec(result) == 'aac'
    assert_audible(result)
    hashes = [ffmpeg('-i', path, '-map', '0:v:0', '-c', 'copy', '-f', 'hash', '-') for path in (source, result)]
    assert hashes[0] == hashes[1]


def test_youtube_requests_audio_avoids_old_cache_and_uses_merged_path(tmp_path, monkeypatch):
    captured = {}
    merged = tmp_path/'merged.mp4'
    merged.write_bytes(b'merged test file')
    class Downloader:
        def __init__(self, options):
            captured.update(options)
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def extract_info(self, url, download):
            return {'title':'Music', 'filepath':str(merged)}
        def prepare_filename(self, info):
            raise AssertionError('Use the final merged path.')
    with monkeypatch.context() as patch:
        patch.setattr(yt_dlp, 'YoutubeDL', Downloader)
        result, title = download('https://youtu.be/kgNjaXTh0rU', tmp_path)
    assert result == merged and title == 'Music'
    assert captured['merge_output_format'] == 'mp4'
    assert '%(id)s-av.' in captured['outtmpl']
    assert Path(captured['ffmpeg_location']).is_file()
    # Exercise yt-dlp's real selector to verify both streams are chosen.
    formats = [
        {'format_id':'audio', 'ext':'m4a', 'acodec':'mp4a.40.2', 'vcodec':'none', 'url':'https://example.com/a'},
        {'format_id':'video', 'ext':'mp4', 'height':1080, 'acodec':'none', 'vcodec':'avc1.640028', 'url':'https://example.com/v'},
    ]
    with yt_dlp.YoutubeDL({'quiet':True}) as downloader:
        select = downloader.build_format_selector(captured['format'])
        chosen = list(select({'formats':formats, 'has_merged_format':False, 'incomplete_formats':False}))
    assert [item['format_id'] for item in chosen[0]['requested_formats']] == ['video','audio']
