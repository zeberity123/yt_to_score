import argparse
from pathlib import Path
import sys

from .extract import Extraction, extract
from .pdf import export_pdf
from .video import download
from .vision import Region


def main():
    parser = argparse.ArgumentParser(description="Extract visible drum sheet music from YouTube or local video.")
    parser.add_argument("source", nargs="?", help="YouTube link or local video; omit to launch desktop app")
    parser.add_argument("-o", "--output", type=Path, default=Path("output/drum-score.pdf"))
    parser.add_argument("--title")
    parser.add_argument("--mode", choices=["auto", "bottom", "page"], default="auto")
    parser.add_argument("--crop", type=float, nargs=4, metavar=("LEFT", "TOP", "RIGHT", "BOTTOM"), help="Crop coordinates from 0 to 1")
    parser.add_argument("--interval", type=float, default=.5, help="Seconds between samples (default .5)")
    parser.add_argument("--threshold", type=float, default=.035, help="Lower values detect smaller notation changes")
    parser.add_argument("--start", type=float, default=0)
    parser.add_argument("--end", type=float)
    parser.add_argument("--gap", type=float, default=1.5, help="Gap between score lines in mm")
    parser.add_argument("--paper", choices=["A4", "Letter"], default="A4")
    parser.add_argument("--project", type=Path, help="Re-export an existing project.json")
    parser.add_argument("--keep-overlap", action="store_true", help="Keep matching lines at page boundaries")
    args = parser.parse_args()
    if not args.source and not args.project:
        from .gui import main as gui_main
        gui_main()
        return
    def report(message, fraction):
        print(message, flush=True)
    try:
        if args.project:
            project = Extraction.load(args.project)
        else:
            region = Region(*args.crop) if args.crop else None
            path, title = download(args.source, args.output.parent/"cache", report)
            project = extract(path, args.output.parent, args.title or title, args.source, region, args.mode,
                              args.interval, args.threshold, args.start, args.end, report,
                              remove_overlap=not args.keep_overlap)
        pages = export_pdf(project, args.output, args.paper, args.gap, title=args.title)
        print(f"Saved {args.output} ({pages} pages, {sum(line.included for line in project.lines)} lines)")
        print(f"Review project: {project.directory / 'project.json'}")
        for warning in project.warnings:
            print(f"Note: {warning}")
    except (ValueError, RuntimeError, OSError) as exc:
        parser.exit(1, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
