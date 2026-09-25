"""Non-destructive line edits and portable, title-named project files."""
from dataclasses import asdict
from pathlib import Path
import re
import shutil
import tempfile
import uuid
from zipfile import ZipFile, ZIP_DEFLATED

from PIL import Image

from .extract import Extraction
from .vision import Region


def safe_name(title):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', title).strip('. ')[:100] or 'Sheet music'
    if name.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL', *[f'COM{i}' for i in range(10)], *[f'LPT{i}' for i in range(10)]}:
        name = '_' + name
    return name


def project_file(project, name):
    path = (project.directory / name).resolve()
    if not path.is_relative_to(project.directory.resolve()) or not path.is_file():
        raise ValueError('Missing project image or invalid image path.')
    return path


def edit_line(project, index, crop=None, reset=False, *, height_scale=None, all_heights=False):
    line = project.lines[index]
    old = asdict(line)
    old_heights = [item.height_scale for item in project.lines]
    new_path = None
    try:
        if reset:
            line.path = line.original_path or line.path
            line.crop = line.original_crop.copy() if line.original_crop else None
            line.height_scale = 1.0
        elif crop is not None and list(crop) != line.crop:
            region = Region(*crop)
            source = project_file(project, line.source_path or line.original_path or line.path)
            with Image.open(source) as image:
                w, h = image.size
                box = (int(region.left*w), int(region.top*h), int(region.right*w), int(region.bottom*h))
                if box[2]-box[0] < 2 or box[3]-box[1] < 2:
                    raise ValueError('Select an area at least 2 pixels wide and high.')
                name = 'edit_' + uuid.uuid4().hex[:12] + '.png'
                new_path = project.directory / name
                image.crop(box).save(new_path)
            if not line.original_path:
                line.original_path = line.path
                line.original_crop = [0, 0, 1, 1]
            line.path, line.crop = name, list(crop)
        if not reset and height_scale is not None:
            height_scale = float(height_scale)
            if not .25 <= height_scale <= 2:
                raise ValueError('Line height must be 25-200%.')
            for item in project.lines if all_heights else [line]:
                item.height_scale = height_scale
        project.save()
    except Exception:
        for key, value in old.items():
            setattr(line, key, value)
        for item, scale in zip(project.lines,old_heights):
            item.height_scale = scale
        if new_path:
            new_path.unlink(missing_ok=True)
        raise
    return line


def archive_project(project, destination):
    """Bundle all referenced images; the live working folder is kept intact."""
    project.save()
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    files = {'project.json'}
    for line in project.lines:
        files.update(p for p in (line.path, line.source_path, line.original_path) if p)
    with tempfile.NamedTemporaryFile(dir=destination.parent, suffix='.tmp', delete=False) as handle:
        temporary = Path(handle.name)
    try:
        with ZipFile(temporary, 'w', ZIP_DEFLATED) as bundle:
            for name in sorted(files):
                bundle.write(project_file(project, name), name)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def open_project(filename, destination):
    filename = Path(filename)
    if filename.suffix.lower() == '.json':
        project = Extraction.load(filename)
    else:
        directory = Path(destination) / ('import_' + uuid.uuid4().hex[:10])
        directory.mkdir(parents=True)
        try:
            with ZipFile(filename) as bundle:
                entries = bundle.infolist()
                if sum(entry.file_size for entry in entries) > 2_000_000_000 or len(entries) > 20000:
                    raise ValueError('Project is too large to open.')
                for entry in entries:
                    # Our bundles are flat. Reject traversal and links, never extract blindly.
                    if '/' in entry.filename or '\\' in entry.filename or ':' in entry.filename or entry.filename in ('.', '..'):
                        raise ValueError('Invalid project archive path.')
                    if entry.filename != 'project.json' and not entry.filename.endswith('.png'):
                        raise ValueError('Unexpected file in project archive.')
                    with bundle.open(entry) as source, (directory / entry.filename).open('wb') as target:
                        shutil.copyfileobj(source, target)
            project = Extraction.load(directory / 'project.json')
        except Exception:
            shutil.rmtree(directory)
            raise
    for line in project.lines:
        for name in (line.path, line.source_path, line.original_path):
            if name:
                project_file(project, name)
    return project
