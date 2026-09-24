from dataclasses import asdict, dataclass
import json
from pathlib import Path
import uuid
import random

import numpy as np
from PIL import Image

from .video import check_cancel, frames, metadata, preview
from .vision import Region, auto_region, clean_score, difference, signature, split_systems, staffs, system_signature


@dataclass
class ScoreLine:
    path: str
    time: float
    view: int
    included: bool = True


@dataclass
class Extraction:
    directory: Path
    title: str
    source: str
    region: Region
    lines: list[ScoreLine]
    warnings: list[str]

    def save(self):
        data = {"version": 1, "title": self.title, "source": self.source,
                "region": asdict(self.region), "lines": [asdict(line) for line in self.lines],
                "warnings": self.warnings}
        temp = self.directory / "project.tmp"
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(self.directory / "project.json")

    @classmethod
    def load(cls, filename):
        filename = Path(filename)
        data = json.loads(filename.read_text(encoding="utf-8"))
        if data.get("version") != 1:
            raise ValueError("Unsupported project version.")
        return cls(filename.parent, data["title"], data["source"], Region(**data["region"]),
                   [ScoreLine(**line) for line in data["lines"]], data.get("warnings", []))


def extract(path, destination, title="Drum score", source="", region=None, mode="auto",
            interval=.5, threshold=.035, start=0, end=None, progress=lambda *args: None, cancel=None,
            remove_overlap=True):
    _, _, duration = metadata(path)
    end = duration if end is None else min(end, duration)
    if not 0 <= start < end:
        raise ValueError("Invalid start/end time.")
    if not 0 < threshold < 1:
        raise ValueError("Change threshold must be between 0 and 1.")
    if region is None:
        candidates = []
        for t in (start, start+(end-start)*.1, start+(end-start)*.3):
            frame = preview(path, t)
            crop = auto_region(frame, mode)
            candidates.append((len(staffs(clean_score(crop.crop(frame)))), crop))
        region = max(candidates, key=lambda item: item[0])[1]
    directory = Path(destination) / ("score_"+uuid.uuid4().hex[:10])
    directory.mkdir(parents=True)
    project = Extraction(directory, title, source or str(path), region, [], [])
    current = None
    view_number = 0
    rejected = 0
    rng = random.Random(0)
    previous_systems = []
    overlap_count = 0

    def flush():
        nonlocal current, view_number, rejected, previous_systems, overlap_count
        if current is None:
            return
        if current["count"] < 2:
            rejected += 1
            current = None
            return
        image = np.median(np.stack(current["samples"]), axis=0).astype(np.uint8)
        if np.mean(image < 110) < .003:
            rejected += 1
            current = None
            return
        strips = split_systems(image)
        if strips:
            view_number += 1
            systems = [system_signature(strip) for strip in strips]
            overlap = 0
            if remove_overlap and len(strips) > 1 and len(previous_systems) > 1:
                for size in range(min(len(systems), len(previous_systems)), 0, -1):
                    pairs = zip(previous_systems[-size:], systems[:size])
                    if all(a is not None and b is not None and difference(a, b) < .035 for a, b in pairs):
                        overlap = size
                        break
            elif remove_overlap and len(strips) == 1 and previous_systems:
                a, b = previous_systems[-1], systems[0]
                if a is not None and b is not None and difference(a, b) < .035:
                    overlap = 1
            overlap_count += overlap
            previous_systems = systems
            for strip in strips[overlap:]:
                name = f"line_{len(project.lines)+1:04d}.png"
                Image.fromarray(strip).save(directory / name)
                project.lines.append(ScoreLine(name, current["time"], view_number))
        current = None

    iterator = frames(path, interval, start, end, cancel)
    try:
        for t, frame in iterator:
            check_cancel(cancel)
            gray = clean_score(region.crop(frame))
            sig = signature(gray)
            if current is not None and difference(current["signature"], sig) <= threshold:
                current["count"] += 1
                # A small reservoir spreads the median across the entire stable view.
                if len(current["samples"]) < 9:
                    current["samples"].append(gray.copy())
                else:
                    index = rng.randrange(current["count"])
                    if index < 9:
                        current["samples"][index] = gray.copy()
            else:
                flush()
                if staffs(gray):
                    current = {"signature": sig, "samples": [gray.copy()], "count": 1, "time": t}
            progress(f"Scanning {t:.1f}s / {end:.1f}s · {len(project.lines)} lines", (t-start)/(end-start))
        flush()
    finally:
        iterator.close()
    if not project.lines:
        raise ValueError("No stable score lines found. Adjust the crop, choose another preview time, or lower the sample interval.")
    if rejected:
        project.warnings.append(f"Skipped {rejected} unstable sampled views (transitions or views shorter than two samples). Review for missing lines; use a smaller sample interval if needed.")
    if overlap_count:
        project.warnings.append(f"Removed {overlap_count} matching lines at consecutive page boundaries. Disable page-overlap removal if these are intentional repeats.")
    project.warnings.append("Review the lines before printing. Continuous scrolling, animated notation, and identical consecutive score views may need manual capture or editing.")
    project.save()
    progress(f"Ready: {len(project.lines)} lines from {view_number} score views", 1)
    return project
