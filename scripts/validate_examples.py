"""Optional real-video validation; run after placing the six videos in samples/."""
from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from drumscore.extract import extract
from drumscore.pdf import export_pdf


EXAMPLES = [
    ("kgNjaXTh0rU", "地球最後の告白を"),
    ("4K47HiVS1_o", "裸の勇者"),
    ("nlAG7LyzshM", "閃光"),
    ("23xBxqLPHa0", "夜咄ディセイブ"),
    ("wR5gXlibmTg", "ヒバナ"),
    ("RfXr5bDboyI", "それがあなたの幸せとしても"),
]


def main():
    report = []
    destination = Path("output/examples")
    for video_id, title in EXAMPLES:
        source = Path("samples") / (video_id+".mp4")
        if not source.exists():
            print(f"Skip {video_id}: local sample not found", flush=True)
            continue
        print(f"Extracting {video_id}", flush=True)
        project = extract(source, destination, title=title, source="https://youtu.be/"+video_id)
        pdf = destination / (title+".pdf")
        pages = export_pdf(project, pdf)
        item = {"video_id": video_id, "title": title, "lines": len(project.lines), "pages": pages,
                "pdf": str(pdf), "project": str(project.directory / "project.json"), "warnings": project.warnings}
        report.append(item)
        (destination/"validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Done {video_id}: {len(project.lines)} lines, {pages} pages", flush=True)


if __name__ == "__main__":
    main()
