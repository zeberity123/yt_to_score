import argparse
from pathlib import Path
import sys

from .extract import Extraction, extract
from .pdf import PAPER_SIZES, export_pdf
from .video import download
from .vision import Region


def main():
    parser = argparse.ArgumentParser(description="Extract visible sheet music from YouTube or local video.")
    parser.add_argument("source", nargs="?", help="YouTube link or local video; omit to launch desktop app")
    parser.add_argument("-o", "--output", type=Path, default=Path("output/drum-score.pdf"))
    parser.add_argument("--title")
    parser.add_argument("--mode", choices=["auto", "bottom", "page"], default="auto")
    parser.add_argument("--notation", choices=['staff', 'guitar', 'bass', 'piano'], default='staff', help='Drums, guitar TAB, bass notation/TAB, or paired piano staves')
    parser.add_argument("--crop", type=float, nargs=4, metavar=("LEFT", "TOP", "RIGHT", "BOTTOM"), help="Crop coordinates from 0 to 1")
    parser.add_argument("--interval", type=float, default=.5, help="Seconds between samples (default .5)")
    parser.add_argument("--threshold", type=float, default=.035, help="Lower values detect smaller notation changes")
    parser.add_argument("--start", type=float, default=0)
    parser.add_argument("--end", type=float)
    parser.add_argument("--gap", type=float, default=0, help="Gap between score lines in mm (default 0)")
    parser.add_argument("--paper", choices=list(PAPER_SIZES), default="A4")
    parser.add_argument("--left-margin", type=float, default=3, help="Left margin in mm, 0-40 (default 3)")
    parser.add_argument("--right-margin", type=float, default=3, help="Right margin in mm, 0-40 (default 3)")
    parser.add_argument("--project", type=Path, help="Re-export an existing project.json")
    parser.add_argument("--keep-overlap", action="store_true", help="Keep matching lines at page boundaries")
    parser.add_argument("--legacy-ui", action="store_true", help="Open the previous Tkinter interface")
    args = parser.parse_args()
    if not args.source and not args.project:
        if args.legacy_ui:
            from .gui import main as gui_main
            gui_main()
        else:
            from .server import main as browser_main
            browser_main(['--open'])
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
                              remove_overlap=not args.keep_overlap, notation=args.notation)
        pages = export_pdf(project, args.output, args.paper, args.gap, title=args.title,
                           left_margin_mm=args.left_margin, right_margin_mm=args.right_margin)
        print(f"Saved {args.output} ({pages} pages, {sum(line.included for line in project.lines)} lines)")
        print(f"Review project: {project.directory / 'project.json'}")
        for warning in project.warnings:
            print(f"Note: {warning}")
    except (ValueError, RuntimeError, OSError) as exc:
        parser.exit(1, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
