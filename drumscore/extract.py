from dataclasses import asdict, dataclass
import json
from pathlib import Path
import uuid
import random

import numpy as np
from PIL import Image

from .video import check_cancel, frames, metadata, preview
from .vision import Region, auto_region, clean_score, clean_tab, difference, signature, tab_signature, split_systems, staffs, system_signature
from .notation import NOTATIONS, clean_notation, system_groups, split_notation, system_fingerprint, notation_signature
from .matching import aligned_difference, measure_anchors


@dataclass
class ScoreLine:
    path: str
    time: float
    view: int
    included: bool = True
    source_path: str | None = None
    crop: list[float] | None = None
    original_path: str | None = None
    original_crop: list[float] | None = None


@dataclass
class Extraction:
    directory: Path
    title: str
    source: str
    region: Region
    lines: list[ScoreLine]
    warnings: list[str]
    notation: str = 'staff'

    def save(self):
        data = {"version": 1, "title": self.title, "source": self.source,
                "region": asdict(self.region), "lines": [asdict(line) for line in self.lines],
                "warnings": self.warnings, "notation": self.notation}
        temp = self.directory / "project.tmp"
        try:
            temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            temp.replace(self.directory / "project.json")
        finally:
            temp.unlink(missing_ok=True)

    @classmethod
    def load(cls, filename):
        filename = Path(filename)
        data = json.loads(filename.read_text(encoding="utf-8"))
        if data.get("version") != 1:
            raise ValueError("Unsupported project version.")
        return cls(filename.parent, data["title"], data["source"], Region(**data["region"]),
                   [ScoreLine(**line) for line in data["lines"]], data.get("warnings", []), data.get('notation', 'staff'))


def extract(path, destination, title="Sheet music", source="", region=None, mode="auto",
            interval=.5, threshold=.035, start=0, end=None, progress=lambda *args: None, cancel=None,
            remove_overlap=True, notation='staff'):
    if notation not in NOTATIONS:
        raise ValueError('Unknown notation type.')
    rules = {'guitar':6,'bass':4}.get(notation,5)
    paired = notation in ('bass','piano')
    clean = clean_tab if notation == 'guitar' else lambda frame:clean_notation(frame,notation)
    find_groups = (lambda gray:system_groups(gray,notation)) if paired else lambda gray:staffs(gray,rules)
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
            crop = auto_region(frame, mode, notation)
            candidates.append((len(find_groups(clean(crop.crop(frame)))), crop))
        region = max(candidates, key=lambda item: item[0])[1]
    directory = Path(destination) / ("score_"+uuid.uuid4().hex[:10])
    directory.mkdir(parents=True)
    project = Extraction(directory, title, source or str(path), region, [], [], notation)
    current = None
    view_number = 0
    rejected = 0
    rng = random.Random(0)
    previous_systems = []
    overlap_count = 0
    tab_panel = None
    tab_joins = 0
    def compare_systems(a,b):
        first, anchors_a = a
        second, anchors_b = b
        if first is None or second is None:
            return 1.0
        return aligned_difference(first,second,fine=current['fine'],stable=current['stable'],
                                  anchors=None if notation == 'guitar' else (anchors_a,anchors_b))

    def flush():
        nonlocal current, view_number, rejected, previous_systems, overlap_count, tab_panel, tab_joins
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
        segments = split_notation(image,notation,with_bounds=True) if paired else split_systems(image, with_bounds=True, rules=rules)
        strips = [strip for strip, bounds in segments]
        if strips:
            view_number += 1
            systems = [(system_fingerprint(strip,notation) if paired else system_signature(strip,rules),
                        measure_anchors(strip,rules=rules,paired=paired)) for strip in strips]
            overlap = 0
            if remove_overlap and len(strips) > 1 and len(previous_systems) > 1:
                for size in range(min(len(systems), len(previous_systems)), 0, -1):
                    pairs = zip(previous_systems[-size:], systems[:size])
                    if all(compare_systems(a,b) < .035 for a,b in pairs):
                        overlap = size
                        break
            elif remove_overlap and len(strips) == 1 and previous_systems:
                a, b = previous_systems[-1], systems[0]
                if compare_systems(a,b) < .035:
                    overlap = 1
            overlap_count += overlap
            # Keep the accepted anchor when discarding a nudged single panel.
            # Otherwise repeated tiny shifts could hide a genuinely scrolling view.
            if not (overlap == 1 and len(systems) == 1):
                previous_systems = systems
            if len(segments) != 1:
                tab_panel = None
            if notation in ('guitar','bass') and remove_overlap and not overlap and len(segments) == 1:
                from .guitar import overlap_cut
                panel, bounds = segments[0]
                if tab_panel is not None and project.lines:
                    previous_panel, previous_left = tab_panel
                    cut = overlap_cut(previous_panel,panel,rules)
                    if cut and cut[0] > previous_left:
                        previous_line = project.lines[-1]
                        Image.fromarray(previous_panel[:, previous_left:cut[0]+1]).save(directory/previous_line.path)
                        previous_line.crop[2] = previous_line.crop[0] + (cut[0]+1-previous_left)/current['frame'].shape[1]
                        previous_line.original_crop = previous_line.crop.copy()
                        segments[0] = (panel[:, cut[1]:], (bounds[0]+cut[1], bounds[1], bounds[2], bounds[3]))
                        tab_panel = (panel, cut[1])
                        tab_joins += 1
                    else:
                        tab_panel = (panel, 0)
                else:
                    tab_panel = (panel, 0)
            context_name = f"source_{view_number:04d}.png"
            fh, fw = current["frame"].shape[:2]
            rx, ry = int(region.left*fw), int(region.top*fh)
            context = clean_score(current['frame'])
            if notation != 'staff':
                context[ry:ry+image.shape[0], rx:rx+image.shape[1]] = image
            Image.fromarray(context).save(directory / context_name)
            for strip, bounds in segments[overlap:]:
                name = f"line_{len(project.lines)+1:04d}.png"
                Image.fromarray(strip).save(directory / name)
                x0, y0, x1, y1 = bounds
                crop = [(rx+x0)/fw, (ry+y0)/fh, (rx+x1)/fw, (ry+y1)/fh]
                project.lines.append(ScoreLine(name, current["time"], view_number,
                                              source_path=context_name, crop=crop,
                                              original_path=name, original_crop=crop.copy()))
        current = None

    iterator = frames(path, interval, start, end, cancel)
    try:
        for t, frame in iterator:
            check_cancel(cancel)
            gray = clean(region.crop(frame))
            sig = notation_signature(gray,notation) if paired else tab_signature(gray) if notation == 'guitar' else signature(gray)
            if current is not None and difference(current["signature"], sig, fine=current['fine'], stable=current['stable']) <= threshold:
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
                if find_groups(gray):
                    tab_only = notation == 'guitar' or (notation == 'bass' and not staffs(gray))
                    current = {"signature": sig, "samples": [gray.copy()], "count": 1, "time": t,
                               "frame": frame.copy(),
                               # Translucent white-on-video TAB needs the same
                               # speckle tolerance as moving drum-score panels.
                               "fine": tab_only and np.mean(region.crop(frame) > 200) > .55,
                               # HD retains enough pixels to reject narrow noise
                               # while still checking individual fret changes.
                               "stable": tab_only and gray.shape[1] >= 1500}
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
    if tab_joins:
        project.warnings.append(f"Joined {tab_joins} overlapping TAB views at matching barlines. Original panels remain available in Edit crop.")
    if notation in ('guitar','bass'):
        project.warnings.append('Check partial measures at TAB panel edges. Uncertain overlaps are kept; use Edit crop to adjust them. Continuously moving TAB may require manual capture.')
    project.warnings.append("Review the lines before printing. Continuous scrolling, animated notation, and identical consecutive score views may need manual capture or editing.")
    project.save()
    progress(f"Ready: {len(project.lines)} lines from {view_number} score views", 1)
    return project
