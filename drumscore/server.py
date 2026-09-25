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

from .editing import archive_project, edit_line, open_project, project_file, safe_name
from .extract import extract
from .manual import append_line, new_manual_project
from .pdf import export_pdf
from .print_layout import print_rows, validate_bars, validate_bar_override
from .video import Cancelled, audio_codec, check_cancel, download, ffmpeg_path, metadata, preview
from .vision import Region, auto_region
from .notation import NOTATIONS, clean_notation, split_notation

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / 'web'


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
        self.projects = {'automatic': None, 'manual': None}
        self.video = None
        self.video_id = None
        self.media = None
        self.duration = 0
        self.has_audio = False
        self.source = ''
        self.title = 'Sheet music'
        self.region = Region()
        self.artifacts = {}
        self.removed = {'automatic': [], 'manual': []}
        self.print_preview = None
        self.print_images = []

    @property
    def project(self):
        return self.projects[self.mode]

    def state(self):
        with self.lock:
            project = self.project
            return {'busy': self.busy, 'status': self.status, 'error': self.error,
                    'progress': self.progress, 'revision': self.revision, 'mode': self.mode,
                    'title': self.title, 'video': bool(self.media), 'videoId': self.video_id,
                    'projectId': project.directory.name if project else None, 'duration': self.duration,
                    'hasAudio': self.has_audio, 'notation': self.notation,
                    'canUndo': bool(self.removed[self.mode]),
                    'barsPerLine': project.bars_per_line if project else 0,
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

    def start(self, task):
        if self.busy:
            raise ValueError('Wait for the current operation or cancel it first.')
        self.busy, self.error, self.progress = True, None, 0
        self.status = 'Working…'
        self.cancel.clear()
        def run():
            try:
                task()
                with self.lock:
                    self.progress = 1
            except Exception as exc:
                with self.lock:
                    self.error = None if isinstance(exc, Cancelled) else str(exc)
                    self.status = 'Cancelled.' if isinstance(exc, Cancelled) else str(exc)
            finally:
                with self.lock:
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
                return
            if self.busy:
                raise ValueError('Wait for the current operation or cancel it first.')
            self.error = None
            if action in ('load','open','mode','extract','capture','add-view','remove','undo','include','move','edit','print-settings'):
                self.print_preview=None
                self.print_images=[]
            notation = self.notation
            if action in ('load','detect','extract'):
                notation = str(data.get('notation', self.notation))
                if notation not in NOTATIONS:
                    raise ValueError('Unknown notation type.')
            if action == 'load':
                source = str(data['source']).strip()
                mode = self.mode
                def task():
                    path, title = download(source, self.output/'cache', self.report, self.cancel)
                    _, _, duration = metadata(path)
                    sound_codec = audio_codec(path)
                    media = self.browser_media(path, sound_codec)
                    region = auto_region(preview(path, 0 if mode == 'manual' else min(20, duration*.1)), data.get('layout', 'auto'), notation)
                    check_cancel(self.cancel)
                    with self.lock:
                        self.video, self.media, self.source = path, media, source
                        self.video_id = uuid.uuid4().hex
                        self.duration, self.title, self.region = duration, title, region
                        self.has_audio = sound_codec is not None
                        self.notation = notation
                        self.projects = {'automatic': None, 'manual': None}
                        self.removed = {'automatic': [], 'manual': []}
                        self.status = 'Video ready. Drag on the video to select your score.'
                self.start(task)
            elif action == 'mode':
                if data['mode'] not in self.projects:
                    raise ValueError('Unknown capture mode.')
                self.mode = data['mode']
                if self.project and self.project.notation in NOTATIONS:
                    self.notation = self.project.notation
            elif action == 'title':
                self.title = str(data['title'])[:500]
                if self.project:
                    self.project.title = self.title
                    self.project.save()
            elif action == 'region':
                self.region = Region(*data['crop'])
            elif action == 'detect':
                self.require_video()
                self.region = auto_region(preview(self.video, float(data['time'])), data.get('layout', 'auto'), notation)
                self.notation = notation
            elif action == 'extract':
                self.require_video()
                region = self.region
                def task():
                    project = extract(self.video, self.output, self.title, self.source, region,
                                      interval=float(data.get('interval', .5)), threshold=float(data.get('threshold', .035)),
                                      start=float(data.get('start', 0)), end=float(data['end']) if data.get('end') not in ('', None) else None,
                                      remove_overlap=bool(data.get('overlap', True)), progress=self.report, cancel=self.cancel,
                                      notation=notation)
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
                    notation = self.project.notation
                    crop_frame = self.region.crop(frame)
                    if notation in ('bass','piano'):
                        cleaned = clean_notation(crop_frame,notation)
                        segments = split_notation(cleaned,notation,with_bounds=True)
                    else:
                        cleaned = clean_tab(crop_frame) if notation == 'guitar' else clean_score(crop_frame)
                        segments = split_systems(cleaned,with_bounds=True,rules=6 if notation=='guitar' else 5)
                    if not segments:
                        raise ValueError('No staff lines found in this crop.')
                    source_name = 'source_' + uuid.uuid4().hex[:12] + '.png'
                    h, w = frame.shape[:2]
                    rx, ry = int(self.region.left*w), int(self.region.top*h)
                    context = clean_score(frame)
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
                project = open_project(data['path'], self.output)
                self.projects = {'automatic': project, 'manual': None}
                self.removed = {'automatic': [], 'manual': []}
                # Older projects stored exclusions in the list. Present them as removed,
                # while allowing Undo to bring them back under the new interaction.
                visible = []
                for line in project.lines:
                    if line.included:
                        visible.append(line)
                    else:
                        line.included = True
                        self.removed['automatic'].append((len(visible), line))
                project.lines = visible
                self.mode, self.title = 'automatic', project.title
                self.notation = project.notation if project.notation in NOTATIONS else 'staff'
                self.video = self.media = None
                self.video_id = None
                self.duration = 0
                self.has_audio = False
                self.status = 'Project opened. Your crops and original images are available.'
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
            elif action in ('remove', 'undo', 'include', 'move', 'edit', 'save', 'export'):
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
                            if action == 'save':
                                archive_project(project, destination)
                            else:
                                project.save()
                                export_pdf(project, destination, paper=data.get('paper', 'A4'),
                                           gap_mm=float(data.get('gap', 0)), left_margin_mm=float(data.get('left', 3)),
                                           right_margin_mm=float(data.get('right', 3)))
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

    def require_video(self):
        if self.video is None:
            raise ValueError('Load a video first.')

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
                        name = (line.source_path or line.original_path or line.path) if query.get('kind', [''])[0] == 'source' else line.path
                        path = project_file(project, name)
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
                if suffix not in ('.mp4', '.mkv', '.webm', '.mov', '.avi', '.drumscore'):
                    raise ValueError('Choose a video or .drumscore project file.')
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
