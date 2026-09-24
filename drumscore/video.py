from __future__ import annotations

import json
import shutil
import subprocess
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
    executable = shutil.which("ffmpeg")
    if executable:
        return executable
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError as exc:
        raise RuntimeError("FFmpeg is missing. Run setup.bat to install dependencies.") from exc


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
            progress(message, None)
        def error(self, message):
            progress(message, None)

    options = {
        "format": "bestvideo[height<=1080][vcodec^=avc]/bestvideo[height<=1080]/best[height<=1080]/best",
        "outtmpl": str(cache / "%(id)s.%(ext)s"),
        "noplaylist": True, "quiet": True, "logger": Logger(),
        "progress_hooks": [hook], "socket_timeout": 20,
        "retries": 2, "fragment_retries": 2, "windowsfilenames": True,
        "ffmpeg_location": str(Path(ffmpeg_path()).parent),
    }
    runtimes = {name: {} for name in ("deno", "node") if shutil.which(name)}
    if runtimes:
        options["js_runtimes"] = runtimes
    check_cancel(cancel)
    progress("Connecting to YouTube…", 0)
    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=True)
        path = Path(ydl.prepare_filename(info))
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
