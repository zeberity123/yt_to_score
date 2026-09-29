"""Local API shared by Electron and the responsive browser interface."""
from __future__ import annotations

import argparse
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import io
import mimetypes
import os
from pathlib import Path
import secrets
import subprocess
import threading
import time
from urllib.parse import parse_qs, unquote, urlparse
import uuid
from zipfile import BadZipFile

import cv2

from .editing import archive_project, duplicate_line, edit_line, open_project, project_file, safe_name
from .extract import extract
from .manual import append_line, new_manual_project
from .pdf import export_pdf
from .print_layout import print_rows, validate_bars, validate_bar_override
from .background import line_image, validate_background
from .video import Cancelled, audio_codec, check_cancel, download, ffmpeg_path, metadata, preview
from .vision import Region, auto_region
from .notation import NOTATIONS, clean_notation, split_notation

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / 'web'
# Automatic = frame capture, AI = transcription/AI-checked capture, Manual = hand-picked frames.
MODES = ('automatic', 'ai', 'manual')


def empty_projects():
    return {mode: None for mode in MODES}


def empty_removed():
    return {mode: [] for mode in MODES}


class Workspace:
    def __init__(self, output=None):
        self.output = Path(output or os.environ.get('DRUMSCORE_OUTPUT') or ROOT / 'output')
        self.output.mkdir(parents=True, exist_ok=True)
        self.export_root = Path(os.environ.get('DRUMSCORE_EXPORTS') or self.output/'exports').resolve()
        if not self.export_root.is_relative_to((self.output/'exports').resolve()):
            raise ValueError('Export staging must stay inside the workspace export folder.')
        self.lock = threading.RLock()
        self.cancel = threading.Event()
        self.busy = False
        self.status = 'Choose a video to start your score.'
        self.error = None
        self.progress = 0
        self.revision = 0
        self.mode = 'automatic'
        self.notation = 'staff'
        self.projects = empty_projects()
        self.video = None
        self.video_id = None
        self.media = None
        self.duration = 0
        self.has_audio = False
        self.tempo = None
        self.source = ''
        self.title = 'Sheet music'
        self.region = Region()
        self.artifacts = {}
        self.removed = empty_removed()
        self.print_preview = None
        self.print_images = []
        self.ai_usage = None
        self.ai_edit = None
        self.ai_connection = ''
        self.extraction_started = None
        self.extraction_elapsed = None
        self.extraction_running = False
        self.ai_progress = None
        self.ai_gate = None

    @property
    def project(self):
        return self.projects[self.mode]

    def state(self):
        with self.lock:
            project = self.project
            status = self.status
            pause = self.ai_gate.state() if self.ai_gate else None
            if self.extraction_running and self.ai_progress and not self.cancel.is_set():
                status = self.ai_progress['phase']
                if self.ai_progress['total']:
                    status += (f" · {self.ai_progress['completed']}/{self.ai_progress['total']} batches completed"
                               f" · {self.ai_progress['saved']} bars/rows saved")
                age = int(time.monotonic()-self.ai_progress['updated'])
                if age >= 10:
                    status += f' · {age//60:02d}:{age%60:02d} since last update'
            if self.extraction_running and pause and pause['requested'] and not self.cancel.is_set():
                status = (f"Pausing · {pause['active']} AI request(s) finishing. No new requests will start."
                          if pause['active'] else 'Paused. No AI requests are running. Click Resume to continue.')
            return {'busy': self.busy, 'status': status, 'error': self.error,
                    'progress': self.progress, 'revision': self.revision, 'mode': self.mode,
                    'title': self.title, 'video': bool(self.media), 'videoId': self.video_id,
                    'projectId': project.directory.name if project else None, 'duration': self.duration,
                    'hasAudio': self.has_audio, 'notation': self.notation,
                    'tempo': self.tempo,
                    'ai': bool(project and project.ai_score),
                    'aiLayout': project.ai_score.get('layout') if project and project.ai_score else None,
                    'aiCheck': ({'method': project.ai_check.get('method', 'images'),
                                 'flagged': sum(1 for line in project.lines if line.notes),
                                 'observations': project.ai_check.get('observations', [])}
                                if project and project.ai_check else None),
                    'aiUsage': dict(self.ai_usage) if self.ai_usage else (
                        (project.ai_score or project.ai_check).get('usage') if project and (project.ai_score or project.ai_check) else None),
                    'aiConnection': self.ai_connection,
                    'aiEdit': self.ai_edit,
                    'aiPause': pause if self.extraction_running and not self.cancel.is_set() else None,
                    'aiProgress': {k: v for k, v in self.ai_progress.items() if k != 'updated'} if self.ai_progress else None,
                    'elapsedSeconds': (time.monotonic()-self.extraction_started-(pause['seconds'] if pause else 0) if self.extraction_running
                                       else self.extraction_elapsed),
                    'canUndo': bool(self.removed[self.mode]),
                    'barsPerLine': project.bars_per_line if project else 0,
                    'background': project.background if project else 'white',
                    'originalMissing': sum(not line.raw_source_path and line.view != 0 for line in project.lines)
                        if project and project.notation not in ('free','chord') else 0,
                    'printPreview': self.print_preview,
                    'undoIndex': self.removed[self.mode][-1][0] if self.removed[self.mode] else None,
                    'region': asdict(self.region), 'source': Path(self.video).name if self.video else '',
                    'lines': [asdict(line) for line in project.lines] if project else [],
                    'warnings': project.warnings if project else [], 'artifacts': self.artifacts.copy()}

    def report(self, text, fraction=None):
        with self.lock:
            self.status = text
            if fraction is not None:
                self.progress = fraction

    def report_ai(self, phase, completed=0, total=0, saved=0):
        with self.lock:
            self.ai_progress = dict(phase=phase, completed=completed, total=total, saved=saved,
                                    updated=time.monotonic())
            self.progress = completed/total if total else 0
            self.status = phase

    def start(self, task, *, timed=False):
        if self.busy:
            raise ValueError('Wait for the current operation or cancel it first.')
        self.busy, self.error, self.progress = True, None, 0
        self.status = 'Working…'
        self.cancel.clear()
        if timed:
            self.ai_progress = None
            self.extraction_started = time.monotonic()
            self.extraction_elapsed = 0
            self.extraction_running = True
        def run():
            try:
                task()
                with self.lock:
                    if not self.cancel.is_set():
                        self.progress = 1
            except Exception as exc:
                from ai_score.providers import Cancelled as AICancelled
                with self.lock:
                    self.error = None if isinstance(exc, (Cancelled, AICancelled)) else str(exc)
                    self.status = 'Cancelled.' if isinstance(exc, (Cancelled, AICancelled)) else str(exc)
            finally:
                with self.lock:
                    if timed:
                        paused = self.ai_gate.state()['seconds'] if self.ai_gate else 0
                        self.extraction_elapsed = time.monotonic()-self.extraction_started-paused
                        self.extraction_running = False
                        if self.ai_gate:
                            self.ai_gate.resume()
                    self.busy = False
                    self.revision += 1
        threading.Thread(target=run, daemon=True).start()

    def browser_media(self, path, sound_codec=None):
        cap = cv2.VideoCapture(str(path))
        fourcc = int(cap.get(cv2.CAP_PROP_FOURCC))
        cap.release()
        codec = ''.join(chr((fourcc >> (8*i)) & 255) for i in range(4)).lower()
        mp4_video = path.suffix.lower() == '.mp4' and codec in ('avc1', 'h264', 'av01', 'vp09')
        webm_video = path.suffix.lower() == '.webm' and codec in ('vp80', 'vp90', 'vp8 ', 'vp9 ', 'av01')
        if ((mp4_video and sound_codec in (None, 'aac', 'mp3', 'opus')) or
                (webm_video and sound_codec in (None, 'opus', 'vorbis'))):
            return path
        import hashlib
        identity = f'{path.resolve()}:{path.stat().st_mtime_ns}:{path.stat().st_size}'
        target = self.output / 'cache' / (hashlib.sha256(identity.encode()).hexdigest()[:20] + '-preview-av.mp4')
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            return target
        self.report('Preparing a browser-compatible video…', 0)
        temporary = target.with_name(target.stem + '.' + uuid.uuid4().hex[:8] + '.partial.mp4')
        log_path = temporary.with_suffix('.log')
        video_options = (['-c:v', 'copy'] if mp4_video or webm_video else
                         ['-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2', '-c:v', 'libx264',
                          '-preset', 'veryfast', '-crf', '23', '-pix_fmt', 'yuv420p'])
        try:
            with log_path.open('w') as log:
                process = subprocess.Popen([ffmpeg_path(), '-y', '-i', str(path),
                    '-map', '0:v:0', '-map', '0:a:0?', *video_options,
                    '-c:a', 'aac', '-b:a', '160k', '-ac', '2', '-movflags', '+faststart', str(temporary)],
                    stdout=subprocess.DEVNULL, stderr=log,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                try:
                    while process.poll() is None:
                        check_cancel(self.cancel)
                        time.sleep(.1)
                finally:
                    if process.poll() is None:
                        process.terminate()
                        process.wait()
                if process.returncode:
                    raise ValueError('Could not prepare this video for playback. Try an H.264 MP4.')
            temporary.replace(target)
            return target
        finally:
            temporary.unlink(missing_ok=True)
            log_path.unlink(missing_ok=True)

    def command(self, action, data):
        with self.lock:
            if action == 'release-artifact':
                self.release_artifact(str(data['id']))
                return
            if action == 'cancel':
                self.cancel.set()
                self.status = 'Cancelling… preserving completed work. Please wait.'
                return
            if action in ('pause-ai', 'resume-ai'):
                if not self.extraction_running or not self.ai_gate or self.cancel.is_set():
                    raise ValueError('No active AI extraction to pause or resume.')
                self.ai_gate.pause() if action == 'pause-ai' else self.ai_gate.resume()
                return
            if self.busy:
                raise ValueError('Wait for the current operation or cancel it first.')
            self.error = None
            if action.startswith('ai-'):
                self.ai_command(action, data)
                self.revision += 1
                return
            if action in ('load','open','mode','extract','capture','add-view','remove','duplicate','undo','include','move','edit','print-settings','background'):
                self.print_preview=None
                self.print_images=[]
            notation = self.notation
            if action in ('load','detect','extract'):
                notation = str(data.get('notation', self.notation))
                if notation not in (*NOTATIONS, 'chord'):
                    raise ValueError('Unknown notation type.')
            if action == 'load':
                source = str(data['source']).strip()
                mode = self.mode
                def task():
                    path, title = download(source, self.output/'cache', self.report, self.cancel)
                    _, _, duration = metadata(path)
                    sound_codec = audio_codec(path)
                    media = self.browser_media(path, sound_codec)
                    region = Region() if mode == 'ai' or notation == 'chord' else auto_region(preview(path, 0 if mode == 'manual' else min(20, duration*.1)), data.get('layout', 'auto'), notation)
                    check_cancel(self.cancel)
                    with self.lock:
                        self.video, self.media, self.source = path, media, source
                        self.video_id = uuid.uuid4().hex
                        self.duration, self.title, self.region = duration, title, region
                        self.has_audio = sound_codec is not None
                        self.tempo = None
                        self.notation = notation
                        self.projects = empty_projects()
                        self.removed = empty_removed()
                        self.ai_edit = None
                        self.status = ('Video ready. Choose Extract with AI, or enable Select score area to drag a crop.'
                                       if mode == 'ai' else 'Video ready. Drag on the video to select your score.')
                self.start(task)
            elif action == 'mode':
                mode = 'automatic' if data['mode'] == 'free' else data['mode']  # older UI alias
                if mode not in self.projects:
                    raise ValueError('Unknown capture mode.')
                self.mode = mode
                if self.project and self.project.notation in (*NOTATIONS, 'free', 'chord'):
                    self.notation = 'chord' if self.project.notation == 'free' else self.project.notation
                elif self.notation == 'free':
                    self.notation = 'chord'
            elif action == 'title':
                self.title = str(data['title'])[:500]
                if self.project:
                    self.project.title = self.title
                    self.project.save()
            elif action == 'region':
                self.region = Region(*data['crop'])
            elif action == 'detect':
                self.require_video()
                if notation == 'chord':
                    raise ValueError('Draw a rectangle around the chords and lyrics before using Chord mode.')
                self.region = auto_region(preview(self.video, float(data['time'])), data.get('layout', 'auto'), notation)
                self.notation = notation
            elif action == 'detect-tempo':
                self.require_video()
                from .tempo import detect_tempo
                def task():
                    result = detect_tempo(self.video, self.report, self.cancel)
                    check_cancel(self.cancel)
                    with self.lock:
                        self.tempo = dict(result, id=uuid.uuid4().hex)
                        self.status = 'BPM estimate ready. Check the tempo and meter before enabling timing recovery.'
                self.start(task)
            elif action == 'extract':
                self.require_video()
                if self.mode != 'automatic':
                    raise ValueError('Choose Automatic mode to extract score lines.')
                region = self.region
                chord = notation == 'chord'  # Chord sheets use the text-row capture path.
                def task():
                    project = extract(self.video, self.output, self.title, self.source, region,
                                      mode='free' if chord else 'auto',
                                      interval=float(data.get('interval', .5)), threshold=float(data.get('threshold', .035)),
                                      start=float(data.get('start', 0)), end=float(data['end']) if data.get('end') not in ('', None) else None,
                                      remove_overlap=bool(data.get('overlap', True)), progress=self.report, cancel=self.cancel,
                                      notation='free' if chord else notation, bpm=data.get('bpm') or None, beats_per_bar=data.get('beatsPerBar') or 4,
                                      timing_repeats=bool(data.get('timingRepeats',False)),
                                      flexible_area=bool(data.get('flexibleArea',False)))
                    with self.lock:
                        self.projects['automatic'] = project
                        self.removed['automatic'] = []
                        self.mode = 'automatic'
                        self.notation = notation
                        self.status = f'{len(project.lines)} score lines ready to review.'
                self.start(task)
            elif action in ('capture', 'add-view'):
                self.require_video()
                seconds = float(data['time'])
                frame = preview(self.video, seconds)
                if action == 'capture':
                    if self.mode != 'manual':
                        raise ValueError('Choose Manual mode to capture a line.')
                    if not self.project:
                        self.projects[self.mode] = new_manual_project(self.output, self.title, self.source, self.region)
                        self.project.notation = self.notation
                    append_line(self.project, frame, self.region, seconds)
                else:
                    if not self.project:
                        raise ValueError('Extract a score first, then add missing views.')
                    from .vision import clean_score, clean_tab, split_systems
                    from .extract import ScoreLine
                    from PIL import Image
                    notation = 'free' if self.project.notation == 'chord' else self.project.notation
                    crop_frame = self.region.crop(frame)
                    if notation == 'free':
                        from .free import text_mask, text_rows
                        cleaned = cv2.cvtColor(crop_frame, cv2.COLOR_BGR2RGB)
                        segments = [(cleaned[y0:y1, x0:x1], (x0,y0,x1,y1))
                                    for x0,y0,x1,y1 in text_rows(text_mask(crop_frame))]
                    elif notation in ('bass','piano'):
                        cleaned = clean_notation(crop_frame,notation)
                        segments = split_notation(cleaned,notation,with_bounds=True)
                    else:
                        cleaned = clean_tab(crop_frame) if notation == 'guitar' else clean_score(crop_frame)
                        segments = split_systems(cleaned,with_bounds=True,rules=6 if notation=='guitar' else 5)
                    if not segments:
                        raise ValueError('No text rows found in this crop.' if notation == 'free' else 'No staff lines found in this crop.')
                    source_name = 'source_' + uuid.uuid4().hex[:12] + '.png'
                    h, w = frame.shape[:2]
                    rx, ry = int(self.region.left*w), int(self.region.top*h)
                    context = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB) if notation == 'free' else clean_score(frame)
                    context[ry:ry+cleaned.shape[0],rx:rx+cleaned.shape[1]] = cleaned
                    Image.fromarray(context).save(self.project.directory/source_name)
                    at = min(len(self.project.lines), max(0, int(data.get('after', len(self.project.lines)-1))+1))
                    for offset, (strip, box) in enumerate(segments):
                        name = 'extra_' + uuid.uuid4().hex[:12] + '.png'
                        Image.fromarray(strip).save(self.project.directory/name)
                        crop = [(rx+box[0])/w, (ry+box[1])/h, (rx+box[2])/w, (ry+box[3])/h]
                        self.project.lines.insert(at+offset, ScoreLine(name, seconds, 0, source_path=source_name,
                                                  crop=crop, original_path=name, original_crop=crop.copy()))
                    self.project.save()
                self.status = f'{len(self.project.lines)} lines captured.'
            elif action == 'open':
                path = Path(data['path'])
                if path.name.endswith('.aiscore.json'):
                    from .ai_workspace import create_project
                    project = create_project(json.loads(path.read_text(encoding='utf-8')), self.output/('ai-import-'+uuid.uuid4().hex[:12]), str(path))
                else:
                    project = open_project(path, self.output)
                if project.ai_score or getattr(project, 'ai_check', None):
                    mode = 'ai'
                elif project.lines and all(line.view == 0 for line in project.lines):
                    mode = 'manual'  # only hand-picked frames
                else:
                    mode = 'automatic'
                self.projects = empty_projects()
                self.removed = empty_removed()
                self.ai_edit = None
                self.adopt(mode, project)
                self.mode, self.title = mode, project.title
                self.region = project.region
                self.notation = 'chord' if project.notation == 'free' else project.notation if project.notation in (*NOTATIONS, 'chord') else 'staff'
                self.video = self.media = None
                self.video_id = None
                self.duration = 0
                self.has_audio = False
                self.status = 'Project opened. Your crops and original images are available.'
            elif action == 'background':
                if not self.project:
                    raise ValueError('Capture lines or open a project first.')
                background = validate_background(data.get('background'))
                old = self.project.background
                self.project.background = background
                try:
                    self.project.save()
                except Exception:
                    self.project.background = old
                    raise
            elif action == 'print-settings':
                if not self.project:
                    raise ValueError('Capture lines or open a project first.')
                bars=validate_bars(data.get('bars',0))
                if bars and self.project.notation not in ('guitar','bass'):
                    raise ValueError('Bar layout is available for guitar and bass TAB.')
                old=self.project.bars_per_line
                self.project.bars_per_line=bars
                try:
                    self.project.save()
                except Exception:
                    self.project.bars_per_line=old
                    raise
            elif action == 'print-line-bars':
                if not self.project or not self.project.bars_per_line or not self.print_preview:
                    raise ValueError('Open the print preview first.')
                anchor=str(data.get('anchor',''))
                if not anchor or anchor not in self.print_preview['anchors']:
                    raise ValueError('Open the print preview first.')
                bars=validate_bar_override(data.get('bars'))
                old=self.project.bar_overrides.copy()
                if bars:
                    self.project.bar_overrides[anchor]=bars
                else:
                    self.project.bar_overrides.pop(anchor,None)
                try:
                    self.project.save()
                except Exception:
                    self.project.bar_overrides=old
                    raise
                self.print_preview=None
                self.print_images=[]
            elif action == 'preview-print':
                if not self.project:
                    raise ValueError('Capture lines or open a project first.')
                project=self.project
                def task():
                    from PIL import Image
                    rows,notes=print_rows(project)
                    images=[]
                    sizes=[]
                    for row in rows:
                        check_cancel(self.cancel)
                        factor=min(1,1200/row.image.width,900/(row.image.height*row.height_scale))
                        size=(max(1,round(row.image.width*factor)),max(1,round(row.image.height*factor*row.height_scale)))
                        sizes.append(size)
                        with row.image:
                            thumb=row.image.resize(size,Image.Resampling.LANCZOS)
                            buffer=io.BytesIO()
                            thumb.save(buffer,format='PNG')
                        images.append(buffer.getvalue())
                    with self.lock:
                        self.print_images=images
                        self.print_preview={'id':uuid.uuid4().hex,'widths':[row.width_fraction for row in rows],
                                            'bars':[row.bars for row in rows],'notes':notes,'sizes':sizes,
                                              'anchors':[row.anchor for row in rows],
                                              'overrides':[project.bar_overrides.get(row.anchor,0) for row in rows]}
                        self.status=f'{len(rows)} print lines ready.'
                self.start(task)
            elif action in ('remove', 'duplicate', 'undo', 'include', 'move', 'edit', 'save', 'export'):
                if not self.project:
                    raise ValueError('Capture lines or open a project first.')
                project = self.project
                if action == 'undo':
                    history = self.removed[self.mode]
                    if not history:
                        raise ValueError('No removed line to restore.')
                    index, line = history[-1]
                    index = min(index, len(project.lines))
                    project.lines.insert(index, line)
                    try:
                        project.save()
                    except Exception:
                        project.lines.pop(index)
                        raise
                    history.pop()
                    self.status = 'Line restored.'
                elif action == 'duplicate':
                    duplicate_line(project, int(data['index']))
                    self.status = 'Line duplicated. Move the copy to the desired position.'
                elif action == 'remove':
                    index = int(data['index'])
                    if not 0 <= index < len(project.lines):
                        raise ValueError('Select a score line first.')
                    line = project.lines.pop(index)
                    try:
                        project.save()
                    except Exception:
                        project.lines.insert(index, line)
                        raise
                    self.removed[self.mode].append((index, line))
                    self.status = 'Line removed. Use Undo to restore it.'
                elif action in ('include', 'move', 'edit'):
                    index = int(data['index'])
                    if not 0 <= index < len(project.lines):
                        raise ValueError('Select a score line first.')
                    if action == 'include':
                        project.lines[index].included = bool(data['included'])
                        project.save()
                    elif action == 'move':
                        target = index + int(data['direction'])
                        if 0 <= target < len(project.lines):
                            project.lines[index], project.lines[target] = project.lines[target], project.lines[index]
                            project.save()
                    else:
                        edit_line(project,index,data.get('crop'),bool(data.get('reset')),
                                  height_scale=data.get('heightScale'),all_heights=bool(data.get('allHeights')))
                        self.status = 'Line updated. You can edit again or restore the original.'
                else:
                    title = str(data.get('title', self.title))[:500]
                    self.title = project.title = title
                    key = uuid.uuid4().hex
                    suffix = '.drumscore' if action == 'save' else '.pdf'
                    destination = self.export_root/key/(safe_name(title)+suffix)
                    def task():
                        try:
                            if project.ai_score and data.get('aiLayout'):
                                from .ai_workspace import update_layout
                                update_layout(project, data['aiLayout'])
                            if action == 'save':
                                archive_project(project, destination)
                            else:
                                project.save()
                                page = dict(paper=data.get('paper', 'A4'), gap_mm=float(data.get('gap', 0)),
                                            left_margin_mm=float(data.get('left', 3)), right_margin_mm=float(data.get('right', 3)))
                                if project.ai_score:
                                    from .ai_workspace import export_ai
                                    export_ai(project, destination, **page)
                                else:
                                    export_pdf(project, destination, **page,
                                               top_margin_mm=float(data.get('top', 12)), bottom_margin_mm=float(data.get('bottom', 12)),
                                               title_size=float(data.get('titleSize', 12)),
                                               show_title=bool(data.get('showTitle', True)), page_numbers=bool(data.get('pageNumbers', True)))
                        except Exception:
                            destination.unlink(missing_ok=True)
                            if destination.parent.is_dir() and not any(destination.parent.iterdir()):
                                destination.parent.rmdir()
                            raise
                        with self.lock:
                            self.artifacts[key] = {'name': destination.name, 'kind': action, 'path': str(destination)}
                            self.status = f'Ready to save: {destination.name}'
                    self.start(task)
            else:
                raise ValueError('Unknown action.')
            self.revision += 1

    def ai_client(self, provider, data, folder):
        """A subscription/API client for one job, wired to this workspace's cancel, pause and progress."""
        from ai_score.providers import Client, PROVIDERS
        from ai_score.control import RequestGate
        model = str(data.get('model') or PROVIDERS[provider]['model'])
        key = str(data.get('apiKey', ''))
        if provider not in ('Codex', 'Claude CLI') and not key.strip():
            raise ValueError('Enter an API key for the selected provider.')
        client = Client(provider, model, key, folder, self.cancel, lambda msg: self.report(msg), budget=None, max_requests=None)
        self.ai_gate = client.gate = RequestGate()
        self.ai_usage = client.usage
        client.progress = self.report_ai
        return client

    def ai_command(self, action, data):
        from ai_score.providers import PROVIDERS, login_status, claude_login_status
        from .ai_workspace import create_project, update_layout, export_ai, pdf_images, apply_ai_edit
        provider = str(data.get('provider', 'Codex'))
        if provider not in PROVIDERS:
            raise ValueError('Choose a supported AI connection.')
        if action == 'ai-check':
            def task():
                if provider == 'Codex':
                    status = login_status()
                elif provider == 'Claude CLI':
                    status = claude_login_status()
                else:
                    status = f'{provider} uses a separate API key and API billing. The key is only kept in memory; connectivity is checked on extraction.'
                with self.lock:
                    self.ai_connection = self.status = status
            self.start(task)
        elif action == 'ai-extract':
            self.require_video()
            instrument = str(data.get('instrument', 'drums'))
            if instrument not in ('drums', 'bass', 'guitar', 'piano', 'chord'):
                raise ValueError('Choose a supported instrument.')
            bars = int(data.get('bars', 0))
            if not 0 <= bars <= 16:
                raise ValueError('Bars per line must be 1–16 or disabled.')
            method = str(data.get('method', 'notation'))
            if method not in ('images', 'notation'):
                raise ValueError('Choose an AI method.')
            capture_options = {key: data.get(key) for key in ('interval', 'threshold', 'start', 'end', 'overlap')}
            import hashlib
            from ai_score.pipeline import validate_crop
            selected_crop = validate_crop(data.get('crop'))
            job_identity = f'{self.video}:{instrument}'
            if selected_crop:
                job_identity += json.dumps(selected_crop)
            identity = hashlib.sha256(job_identity.encode()).hexdigest()[:16]
            folder = self.output/'ai-jobs'/identity
            client = self.ai_client(provider, data, folder/'responses')
            path, source, title = self.video, self.source, self.title
            def task():
                from ai_score.pipeline import extract as ai_extract, cancelled_draft
                from ai_score.providers import Cancelled as AICancelled, write_json
                if method == 'images':
                    from ai_score.hybrid import extract_images
                    try:
                        project = extract_images(client, str(path), instrument, folder, title, source, self.output,
                                                 selected_crop, options=capture_options)
                    except (Cancelled, AICancelled):
                        self.report('Cancelled before the score lines were captured. Retry to reuse the completed AI responses.')
                        return
                    with self.lock:
                        self.adopt('ai', project)
                        self.mode = 'ai'
                        self.notation = 'chord' if project.notation == 'free' else project.notation
                        self.title = project.title
                        self.status = f'{len(project.lines)} captured lines ready to review. AI check findings are in Extraction notes.'
                    return
                partial = False
                try:
                    _, _, score = ai_extract(client, str(path), instrument, folder, bars_per_line=bars,
                                            instructions=str(data.get('instructions', '')), full_frames=True,
                                            selected_crop=selected_crop, title=title)
                    check_cancel(self.cancel)
                except (Cancelled, AICancelled):
                    partial = True
                    score = cancelled_draft(client, bars)
                    if score is None:
                        self.report('Cancelled before any complete score batches were saved. Retry extraction to reuse completed AI responses.')
                        return
                    write_json(folder/'cancelled-draft.aiscore.json', score)
                self.report_ai('Preparing incomplete draft for review' if partial else 'Preparing AI score lines for review')
                if partial:
                    self.report('Cancelled. Preparing completed batches for review…')
                try:
                    project = create_project(score, self.output/('ai-score-'+uuid.uuid4().hex[:12]), source)
                except Exception:
                    if not partial:
                        raise
                    self.report(f'Cancelled. The incomplete draft could not be rendered; saved at {folder / "cancelled-draft.aiscore.json"}. Retry extraction to reuse completed responses.')
                    return
                with self.lock:
                    self.projects['ai'] = project
                    self.removed['ai'] = []
                    self.mode = 'ai'
                    self.notation = project.notation
                    self.title = project.title
                    self.status = (f'Cancelled. {len(project.lines)} incomplete draft lines available in Review & export. Retry with the same settings to reuse completed responses.'
                                   if partial else f'{len(project.lines)} AI score lines ready to review.')
            self.start(task, timed=True)
        elif action in ('ai-layout', 'ai-preview'):
            if not self.project or not self.project.ai_score:
                raise ValueError('Extract or open an AI score first.')
            import copy
            project = copy.deepcopy(self.project)
            mode = self.mode
            def task():
                update_layout(project, data.get('layout', {}))
                images = []
                if action == 'ai-preview':
                    self.report('Rendering PDF preview')
                    pdf = project.directory/'ai-preview.pdf'
                    export_ai(project, pdf, paper=data.get('paper', 'A4'),
                              left_margin_mm=float(data.get('left', 3)), right_margin_mm=float(data.get('right', 3)))
                    for image in pdf_images(pdf, 1.2):
                        with image:
                            buffer = io.BytesIO(); image.save(buffer, format='PNG')
                            images.append((buffer.getvalue(), image.size))
                with self.lock:
                    self.projects[mode] = project
                    self.title = project.title
                    if action == 'ai-preview':
                        self.print_images = [content for content, size in images]
                        self.print_preview = {'id': uuid.uuid4().hex, 'pages': True, 'widths': [1]*len(images),
                            'bars': [0]*len(images), 'notes': project.warnings, 'sizes': [size for content, size in images],
                            'anchors': [None]*len(images), 'overrides': [0]*len(images)}
                    self.status = 'AI PDF preview ready.' if images else 'Page settings saved. No AI request was needed.'
            self.start(task)
        elif action == 'ai-edit':
            if not self.project or not (self.project.ai_score or self.project.ai_check):
                raise ValueError('Extract or open an AI score first.')
            text = str(data.get('text', '')).strip()[:2000]
            if not text:
                raise ValueError('Describe the change you want.')
            import copy
            project = copy.deepcopy(self.project)
            mode = self.mode
            # Reuse the job's response cache when it is still on this machine.
            origin = project.ai_score or project.ai_check
            folder = Path(origin.get('job_folder') or self.output/'ai-jobs'/('edit-'+project.directory.name))
            client = self.ai_client(provider, data, folder/'responses')
            def task():
                self.report('Applying AI edit')
                if project.ai_score:
                    notes = apply_ai_edit(client, project, text)
                else:
                    from ai_score.hybrid import edit_lines
                    notes = edit_lines(client, project, text)
                with self.lock:
                    if project.ai_score:
                        self.projects[mode] = project
                    else:
                        self.adopt(mode, project)
                    self.title = project.title
                    self.ai_edit = notes
                    self.status = (f"AI edit applied: {len(notes['marks'])} bar(s) updated, {len(notes['reread'])} re-read, "
                                   f"{len(notes['unsupported'])} request(s) not applied.")
            self.start(task, timed=True)
        elif action == 'ai-line-transcribe':
            project = self.project
            if not project or not project.ai_check:
                raise ValueError('Extract with AI (keep video images) first.')
            index = int(data.get('index', -1))
            if not 0 <= index < len(project.lines):
                raise ValueError('Select a score line first.')
            folder = Path(project.ai_check.get('job_folder') or project.directory)
            client = self.ai_client(provider, data, folder/'responses')
            def task():
                from ai_score.hybrid import transcribe_line
                transcribe_line(client, project, index)
                with self.lock:
                    self.status = f'Line {index+1} engraved with AI. Use Edit crop → Restore original to go back to the capture.'
            self.start(task, timed=True)
        else:
            raise ValueError('Unknown AI action.')

    def require_video(self):
        if self.video is None:
            raise ValueError('Load a video first.')

    def adopt(self, mode, project):
        """Install a project in a mode slot. Excluded lines (older projects, AI checks)
        are presented as removed so Undo can bring them back under the current interaction."""
        self.projects[mode] = project
        visible, removed = [], []
        for line in project.lines:
            if line.included:
                visible.append(line)
            else:
                line.included = True
                removed.append((len(visible), line))
        project.lines = visible
        self.removed[mode] = removed

    def release_artifact(self, key):
        """Remove only this session's staged download, never the user's saved copy."""
        with self.lock:
            entry = self.artifacts.get(key)
            if entry:
                path = Path(entry['path']).resolve()
                if path.is_relative_to((self.output/'exports').resolve()):
                    path.unlink(missing_ok=True)
                    if path.parent.is_dir() and not any(path.parent.iterdir()):
                        path.parent.rmdir()
                self.artifacts.pop(key, None)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def respond(self, status, data, content_type='application/json'):
        payload = json.dumps(data, ensure_ascii=False).encode('utf-8') if content_type == 'application/json' else data
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(payload)

    def authorized(self, query):
        token = self.headers.get('X-Session-Token') or query.get('token', [''])[0]
        return secrets.compare_digest(token, self.server.token)

    def image_bytes(self, payload):
        value = self.headers.get('Range', '')
        if not value:
            return self.respond(200, payload, 'image/png')
        import re
        match = re.fullmatch(r'bytes=(\d*)-(\d*)', value)
        if not match or not any(match.groups()):
            return self.respond(416, {'error': 'Invalid range'})
        a, b = match.groups()
        size = len(payload)
        start = int(a) if a else max(0, size-int(b))
        end = min(size-1, int(b)) if a and b else size-1
        if start > end or start >= size:
            return self.respond(416, {'error': 'Invalid range'})
        self.send_response(206)
        self.send_header('Content-Type', 'image/png')
        self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
        self.send_header('Content-Length', str(end-start+1))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(payload[start:end+1])

    def file(self, path, download_name=None):
        size = path.stat().st_size
        start, end, partial = 0, size-1, False
        value = self.headers.get('Range', '')
        if value:
            import re
            match = re.fullmatch(r'bytes=(\d*)-(\d*)', value)
            if not match or not any(match.groups()):
                return self.respond(416, {'error': 'Invalid range'})
            a, b = match.groups()
            start = int(a) if a else max(0, size-int(b))
            end = min(size-1, int(b)) if a and b else size-1
            if start > end or start >= size:
                return self.respond(416, {'error': 'Invalid range'})
            partial = True
        self.send_response(206 if partial else 200)
        self.send_header('Content-Type', mimetypes.guess_type(path.name)[0] or 'application/octet-stream')
        self.send_header('Content-Length', str(end-start+1))
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('X-Content-Type-Options', 'nosniff')
        if partial:
            self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
        if download_name:
            from urllib.parse import quote
            self.send_header('Content-Disposition', "attachment; filename*=UTF-8''"+quote(download_name))
        self.end_headers()
        try:
            with path.open('rb') as stream:
                stream.seek(start)
                remaining = end-start+1
                while remaining:
                    chunk = stream.read(min(1024*1024, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
            return remaining == 0 and not partial
        except (ConnectionError, OSError):
            return False

    def do_GET(self):
        url = urlparse(self.path)
        query = parse_qs(url.query)
        workspace = self.server.workspace
        try:
            if url.path.startswith('/api/'):
                if not self.authorized(query):
                    return self.respond(403, {'error': 'Open the app using its launch link.'})
                if url.path == '/api/state':
                    state = workspace.state()
                    state['artifacts'] = {key: {k: v for k, v in entry.items() if k != 'path'} for key, entry in state['artifacts'].items()}
                    return self.respond(200, state)
                if url.path == '/api/video':
                    workspace.require_video()
                    return self.file(workspace.media)
                if url.path == '/api/print-row':
                    with workspace.lock:
                        current=workspace.print_preview
                        index=int(query['index'][0])
                        if not current or query.get('id',[''])[0] != current['id'] or not 0 <= index < len(workspace.print_images):
                            raise ValueError('Print preview expired. Preview the layout again.')
                        payload=workspace.print_images[index]
                    return self.respond(200,payload,'image/png')
                if url.path == '/api/image':
                    with workspace.lock:
                        project = workspace.project
                        if not project:
                            raise ValueError('No project loaded.')
                        index = int(query['index'][0])
                        if not 0 <= index < len(project.lines):
                            raise ValueError('Invalid score line.')
                        line = project.lines[index]
                        name = ((line.raw_source_path if project.background == 'original' else None) or line.source_path or line.original_path or line.path) if query.get('kind', [''])[0] == 'source' else line.path
                        path = project_file(project, name)
                        if query.get('kind', [''])[0] != 'source':
                            rendered = line_image(project,line)
                            buffer = io.BytesIO()
                            rendered.save(buffer, format='PNG')
                            return self.image_bytes(buffer.getvalue())
                    return self.file(path)
                if url.path == '/api/download':
                    entry = workspace.artifacts[query['id'][0]]
                    # Full browser downloads no longer need their staging copy after transfer.
                    # Electron also acknowledges completion/cancellation for interrupted transfers.
                    if self.file(Path(entry['path']), entry['name']):
                        workspace.release_artifact(query['id'][0])
                    return
                return self.respond(404, {'error': 'Not found'})
            path = (WEB / (unquote(url.path).lstrip('/') or 'index.html')).resolve()
            if not path.is_relative_to(WEB.resolve()) or not path.is_file():
                return self.respond(404, {'error': 'Not found'})
            return self.file(path)
        except (ValueError, KeyError, IndexError, OSError) as exc:
            self.respond(400, {'error': str(exc)})

    def do_POST(self):
        url = urlparse(self.path)
        if not self.authorized(parse_qs(url.query)):
            return self.respond(403, {'error': 'Invalid app session.'})
        try:
            length = int(self.headers.get('Content-Length', 0))
            if url.path == '/api/upload':
                if not 0 < length <= 4_000_000_000:
                    raise ValueError('Choose a file smaller than 4 GB.')
                original_name = Path(unquote(self.headers.get('X-Filename', 'video.mp4')))
                suffix = original_name.suffix.lower()
                ai_project = original_name.name.lower().endswith('.aiscore.json')
                if suffix not in ('.mp4', '.mkv', '.webm', '.mov', '.avi', '.drumscore') and not ai_project:
                    raise ValueError('Choose a video, .drumscore, or .aiscore.json project file.')
                path = self.server.workspace.output/'uploads'/uuid.uuid4().hex/(safe_name(original_name.stem)+suffix)
                path.parent.mkdir(parents=True, exist_ok=True)
                try:
                    with path.open('wb') as target:
                        while length:
                            chunk = self.rfile.read(min(1024*1024, length))
                            if not chunk:
                                raise ValueError('Upload interrupted.')
                            target.write(chunk)
                            length -= len(chunk)
                except Exception:
                    path.unlink(missing_ok=True)
                    raise
                return self.respond(200, {'path': str(path)})
            if url.path != '/api/command' or not 0 < length < 65536:
                raise ValueError('Invalid request.')
            data = json.loads(self.rfile.read(length))
            self.server.workspace.command(data.pop('action'), data)
            self.respond(200, {'ok': True})
        except (ValueError, KeyError, IndexError, TypeError, OSError, BadZipFile) as exc:
            self.respond(400, {'error': str(exc)})


def make_server(host='127.0.0.1', port=0, token=None, output=None):
    server = ThreadingHTTPServer((host, port), Handler)
    server.token = token or secrets.token_urlsafe(32)
    server.workspace = Workspace(output)
    return server


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=0)
    parser.add_argument('--open', action='store_true')
    args = parser.parse_args(argv)
    server = make_server(args.host, args.port, os.environ.get('DRUMSCORE_TOKEN'))
    host = '127.0.0.1' if args.host == '0.0.0.0' else args.host
    url = f'http://{host}:{server.server_port}/#{server.token}'
    print(json.dumps({'port': server.server_port, 'url': url}), flush=True)
    if args.open:
        import webbrowser
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.workspace.cancel.set()
        server.server_close()


if __name__ == '__main__':
    main()
