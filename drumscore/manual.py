"""Manual capture keeps exactly what the user selected, including repeated lines."""
from pathlib import Path
import uuid

import cv2
from PIL import Image

from .extract import Extraction, ScoreLine


def new_manual_project(destination, title, source, region):
    directory = Path(destination) / ("manual_"+uuid.uuid4().hex[:10])
    directory.mkdir(parents=True)
    project = Extraction(directory, title, source, region, [], [])
    project.save()
    return project


def append_line(project, frame, region, seconds):
    """One click = one original-resolution crop; no staff detection or deduplication."""
    if frame is None:
        raise ValueError("Load a video and show a frame first.")
    crop = region.crop(frame)
    name = "manual_"+uuid.uuid4().hex[:10]+".png"
    path = project.directory / name
    Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)).save(path)
    source_name = "source_"+uuid.uuid4().hex[:10]+".png"
    try:
        Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)).save(project.directory / source_name)
    except Exception:
        path.unlink(missing_ok=True)
        (project.directory / source_name).unlink(missing_ok=True)
        raise
    bounds = [region.left, region.top, region.right, region.bottom]
    line = ScoreLine(name, seconds, 0, source_path=source_name, crop=bounds,
                     original_path=name, original_crop=bounds.copy())
    previous_region = project.region
    project.lines.append(line)
    project.region = region
    try:
        project.save()
    except Exception:
        project.lines.pop()
        project.region = previous_region
        path.unlink(missing_ok=True)
        (project.directory / source_name).unlink(missing_ok=True)
        raise
    return line
