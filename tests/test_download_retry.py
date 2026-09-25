from pathlib import Path
import threading

import pytest
import yt_dlp

from drumscore.video import Cancelled, _youtube_download


def test_403_reextracts_and_rejects_lower_resolution_or_missing_audio(tmp_path, monkeypatch):
    calls = []
    final = tmp_path/'score.mp4'
    final.write_bytes(b'video')
    class Downloader:
        def __init__(self, options):
            self.options = options
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def extract_info(self, url, download):
            client = self.options.get('extractor_args', {}).get('youtube', {}).get('player_client', ['default'])[0]
            calls.append((client, download))
            if not download:
                return {'height':360 if client == 'visionos' else 1080,
                        'acodec':'none' if client == 'android_vr' else 'aac'}
            if client != 'tv':
                raise yt_dlp.utils.DownloadError('HTTP Error 403: Forbidden')
            assert self.options['continuedl'] is False
            assert self.options['cachedir'] is False
            return {'filepath':str(final), 'title':'Recovered'}
    monkeypatch.setattr(yt_dlp, 'YoutubeDL', Downloader)
    info, path = _youtube_download('https://youtu.be/nuCxusvDMD0', {}, lambda *args:None, None)
    assert path == final and info['title'] == 'Recovered'
    assert ('visionos', False) in calls and ('visionos', True) not in calls
    assert ('android_vr', False) in calls and ('android_vr', True) not in calls
    assert calls.count(('default', True)) == 2


@pytest.mark.parametrize('cancelled', [False, True])
def test_retry_does_not_swallow_other_errors_or_cancellation(monkeypatch, cancelled):
    cancel = threading.Event()
    class Downloader:
        def __init__(self, options):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def extract_info(self, url, download):
            if cancelled:
                cancel.set()
                raise yt_dlp.utils.DownloadError('HTTP Error 403: Forbidden')
            raise yt_dlp.utils.DownloadError('Video unavailable')
    monkeypatch.setattr(yt_dlp, 'YoutubeDL', Downloader)
    with pytest.raises(Cancelled if cancelled else yt_dlp.utils.DownloadError):
        _youtube_download('https://youtu.be/nuCxusvDMD0', {}, lambda *args:None, cancel)
