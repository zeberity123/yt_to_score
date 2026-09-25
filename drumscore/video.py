from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import cv2
import numpy as np


class Cancelled(Exception):
    pass


def check_cancel(event):
    if event is not None and event.is_set():
        raise Cancelled("Cancelled")


def youtube_url(value):
    parsed = urlparse(value.strip())
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in ("http", "https") or host not in (
        "youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "www.youtu.be"):
        raise ValueError("Paste a YouTube video link, or choose a local video file.")
    if host.endswith("youtu.be"):
        video_id = parsed.path.strip("/").split("/")[0]
    elif parsed.path.startswith(("/shorts/", "/embed/", "/live/")):
        video_id = parsed.path.split("/")[2]
    else:
        video_id = parse_qs(parsed.query).get("v", [""])[0]
    import re
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
        raise ValueError("The link must identify one YouTube video.")
    return f"https://www.youtube.com/watch?v={video_id}"


def ffmpeg_path():
    if getattr(sys, 'frozen', False):
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    executable = shutil.which("ffmpeg")
    if executable:
        return executable
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError as exc:
        raise RuntimeError("FFmpeg is missing. Run setup.bat to install dependencies.") from exc


def audio_codec(path):
    """Read stream headers without decoding the video or requiring ffprobe."""
    result = subprocess.run([ffmpeg_path(), '-hide_banner', '-i', str(path)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=20,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    # FFmpeg exits with 1 when inspecting without an output; its stream headers are still valid.
    match = re.search(r'Stream #\d+:\d+[^\r\n]*: Audio:\s*([^\s,]+)',
                      result.stderr.decode('utf-8', errors='replace'))
    return match.group(1).lower() if match else None


YOUTUBE_CLIENTS = ('default', 'tv', 'mweb', 'web_embedded', 'android')
YOUTUBE_RETRY_CLIENTS = ('visionos', 'android_vr', 'tv', 'web_safari', 'mweb', 'android')


def _selected_media(info):
    streams = (info or {}).get('requested_formats') or [info or {}]
    height = max((stream.get('height') or 0 for stream in streams), default=0)
    audio = any(stream.get('acodec') not in (None, 'none') for stream in streams)
    return height, audio


def _youtube_download(url, options, progress, cancel):
    """Refresh rejected media URLs, keeping notation resolution and audio intact."""
    import yt_dlp

    def run(opts, download=True):
        check_cancel(cancel)
        with yt_dlp.YoutubeDL(opts) as downloader:
            info = downloader.extract_info(url, download=download)
            check_cancel(cancel)
            if not download:
                return info
            if not info:
                raise RuntimeError('YouTube returned no video information.')
            path = info.get('filepath')
            if not path:
                path = next((entry.get('filepath') for entry in info.get('requested_downloads', [])
                             if entry.get('filepath') and Path(entry['filepath']).is_file()), None)
            return info, Path(path or downloader.prepare_filename(info))

    try:
        return run(options)
    except yt_dlp.utils.DownloadError as first_error:
        if not re.search(r'(?:HTTP Error|HTTP error|HTTP status)\s*403|403:\s*Forbidden', str(first_error)):
            raise
        # Re-extract metadata instead of repeatedly requesting the rejected signed URL.
        retry = dict(options, cachedir=False, continuedl=False, overwrites=True)
        probe = dict(retry, skip_download=True, simulate=True, progress_hooks=[], postprocessors=[])
        try:
            desired = _selected_media(run(probe, download=False))
        except yt_dlp.utils.DownloadError:
            desired = (0, False)
        for attempt, client in enumerate((None, *YOUTUBE_RETRY_CLIENTS), 1):
            check_cancel(cancel)
            candidate = dict(retry)
            if client:
                candidate['extractor_args'] = {'youtube': {'player_client': [client]}}
            progress(f'Retrying YouTube download ({attempt})…', None)
            try:
                if client:
                    metadata_options = dict(probe, extractor_args=candidate['extractor_args'])
                    height, audio = _selected_media(run(metadata_options, download=False))
                    if height < desired[0] or (desired[1] and not audio):
                        continue
                return run(candidate)
            except yt_dlp.utils.DownloadError:
                continue
        raise first_error


def download(source, cache, progress=lambda *args: None, cancel=None):
    local = Path(source).expanduser()
    if local.is_file():
        return local.resolve(), local.stem
    url = youtube_url(source)
    import yt_dlp
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)

    def hook(data):
        check_cancel(cancel)
        if data["status"] == "downloading":
            total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
            fraction = data.get("downloaded_bytes", 0)/total if total else 0
            progress(f"Downloading video: {fraction:.0%}", fraction)

    class Logger:
        def debug(self, message):
            pass
        def warning(self, message):
            pass  # Downloader diagnostics are not actionable workspace status.
        def error(self, message):
            pass  # Fatal failures are raised by yt-dlp and shown by the task handler.

    options = {
        "format": ("bestvideo[height<=1080][vcodec^=avc]+bestaudio[ext=m4a]/"
                   "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best/bestvideo[height<=1080]"),
        # Keep audio-enabled downloads separate from older, silent cached videos.
        "outtmpl": str(cache / "%(id)s-av.%(ext)s"),
        "merge_output_format": "mp4",
        "extractor_args": {'youtube': {'player_client': list(YOUTUBE_CLIENTS)}},
        "format_sort": ['proto'],
        "skip_unavailable_fragments": False,
        "noplaylist": True, "quiet": True, "logger": Logger(),
        "progress_hooks": [hook], "socket_timeout": 20,
        "retries": 2, "fragment_retries": 2, "windowsfilenames": True,
        "ffmpeg_location": str(ffmpeg_path()),
    }
    runtimes = {name: {} for name in ("deno", "node") if shutil.which(name)}
    bundled_node = os.environ.get('DRUMSCORE_NODE')
    if bundled_node and Path(bundled_node).is_file():
        runtimes = {'node': {'path': bundled_node}}
    if runtimes:
        options["js_runtimes"] = runtimes
    check_cancel(cancel)
    progress("Connecting to YouTube…", 0)
    info, path = _youtube_download(url, options, progress, cancel)
    check_cancel(cancel)
    if not path.is_file():
        raise RuntimeError("The video download did not produce a readable file.")
    return path, info.get("title", path.stem)


def metadata(path):
    cap = cv2.VideoCapture(str(path))
    try:
        if not cap.isOpened():
            raise ValueError("Cannot open this video. Try an MP4 file.")
        fps = cap.get(cv2.CAP_PROP_FPS)
        width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        duration = cap.get(cv2.CAP_PROP_FRAME_COUNT)/fps if fps else 0
        if min(width, height, duration) <= 0:
            raise ValueError("The video has invalid dimensions or duration.")
        return width, height, duration
    finally:
        cap.release()


def preview(path, seconds):
    cap = cv2.VideoCapture(str(path))
    try:
        cap.set(cv2.CAP_PROP_POS_MSEC, max(0, seconds)*1000)
        ok, frame = cap.read()
        if not ok:
            raise ValueError("No frame at this time; choose an earlier time.")
        return frame
    finally:
        cap.release()


def frames(path, interval=.5, start=0, end=None, cancel=None):
    width, height, duration = metadata(path)
    end = duration if end is None else min(end, duration)
    if not .1 <= interval <= 10:
        raise ValueError("Sample interval must be between 0.1 and 10 seconds.")
    if not 0 <= start < end:
        raise ValueError("Start time must be before end time and within the video.")
    scale = min(1, 1920/width)
    width, height = round(width*scale), round(height*scale)
    command = [ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-nostdin",
               "-ss", str(start), "-i", str(path), "-t", str(end-start),
               "-vf", f"fps=1/{interval},scale={width}:{height}", "-an", "-sn",
               "-f", "rawvideo", "-pix_fmt", "bgr24", "pipe:1"]
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    with tempfile.TemporaryFile() as errors:
        proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=errors, creationflags=flags)
        done = threading.Event()
        def stop_on_cancel():
            while not done.wait(.2):
                if cancel is not None and cancel.is_set():
                    proc.kill()
                    return
        watcher = threading.Thread(target=stop_on_cancel, daemon=True)
        watcher.start()
        count = 0
        try:
            size = width*height*3
            while True:
                check_cancel(cancel)
                data = proc.stdout.read(size)
                if not data:
                    break
                if len(data) != size:
                    check_cancel(cancel)
                    raise RuntimeError("FFmpeg returned an incomplete video frame.")
                yield start+count*interval, np.frombuffer(data, np.uint8).reshape(height, width, 3)
                count += 1
            check_cancel(cancel)
            if proc.wait() != 0:
                errors.seek(0)
                raise RuntimeError(errors.read().decode("utf-8", "replace")[-2000:])
        finally:
            done.set()
            if proc.poll() is None:
                proc.kill()
            proc.wait()
            proc.stdout.close()
