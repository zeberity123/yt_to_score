# Drum Sheet Extractor

A Windows desktop app that turns the **drum notation already visible in a YouTube video** into a printable PDF. It captures and arranges the score images; it does not transcribe the audio or produce editable MusicXML.

## Start

Install Python 3.11 or newer (including Tcl/Tk and “Add Python to PATH”), download or clone this repository, and run `setup.bat` once. Then **double-click `run.bat`** to open the app.

If dependencies are already installed in this workspace, you can go straight to `run.bat`. FFmpeg is installed as a Python dependency if there is no system FFmpeg. Internet access is needed to download dependencies and YouTube videos.

1. Paste a YouTube video link, or choose a local MP4/MKV/WebM/MOV/AVI.
2. Click **Load video**. The green rectangle marks the detected score area.
3. Check the preview. Drag a rectangle to adjust the crop if needed. Use the time slider and **Show frame** to inspect another point. Include tempo markings, section letters, and symbols above/below the staff.
4. Click **Extract score lines** at the upper-right of the **Score area** tab, above the preview.
5. In **Review & export**, select lines to inspect them. Include/exclude lines or move a selected line up/down.
6. Set the PDF title, paper size, and line gap, then click **Export PDF**.

The default line gap is 1.5 mm. Images retain their aspect ratio and lines never split across PDF pages. The PDF opens automatically after export on Windows.

## Supported layouts

- A score strip beneath performance footage.
- Full-screen score pages, separated into individual staff systems.
- Pages that scroll in steps and retain some lines from the preceding view.
- Light colored playback highlights, colored drum noteheads, and many translucent score backgrounds.

Each stable view is sampled over time. The extractor uses a median of sampled images to reduce moving highlights. Matching lines at successive page boundaries can be removed; **later returns to a previous passage are kept**. Disable “Remove overlapping lines when pages scroll” if a boundary match is an intentional repeated line.

## Review and recovery

Extraction is heuristic. Review the result before printing, especially dense annotations, transitions, partial lines at screen edges, and translucent overlays. Closely packed text can be associated with the neighboring line.

- **Missed short views:** reduce “Sample every” from `0.5` to `0.25` seconds. A view must survive at least two samples.
- **Similar lines merged:** lower the change threshold (for example, `0.02`). Lower values can also produce more duplicates.
- **Too many duplicates:** check that the crop excludes moving footage. Exclude unwanted lines in the review list; increase the change threshold cautiously.
- **Missing line:** after extraction, select the insertion position in the review list. Return to Score area, move the slider, click Show frame, adjust the crop, and click **Add this view**. New lines are inserted after the selected line.
- **Continuous scrolling or animated notation:** automatic extraction may miss or repeat material. Capture stable views manually or use a different source video. A score that stays visually identical across consecutive repetitions cannot reveal those repetition boundaries.
- **Low-resolution source:** PDF quality is limited by the video. The downloader requests video up to 1080p, preferring H.264 for decoder compatibility.

The original reference PDFs are never modified. Every extraction gets a new directory under `output/` containing lossless line PNGs and `project.json`. Inclusion/order edits are saved there. Use **Open project** to resume reviewing or exporting a saved extraction. Keep its PNGs together with the JSON file.

YouTube downloads are cached in `output/cache/`. If YouTube rejects a download, update the downloader with:

```powershell
.\.venv\Scripts\python -m pip install -U "yt-dlp[default]"
```

For current YouTube challenges, a supported JavaScript runtime may be needed. The app automatically enables installed Node.js or Deno. See the upstream [yt-dlp JavaScript runtime guide](https://github.com/yt-dlp/yt-dlp/wiki/EJS). Private, restricted, or unavailable videos may require supplying a local video file instead.

## Command line

```powershell
# YouTube input, automatically detect the layout
.\.venv\Scripts\python -m drumscore "https://youtu.be/kgNjaXTh0rU" -o "output/my-score.pdf"

# Full-page video with compact spacing
.\.venv\Scripts\python -m drumscore "https://youtu.be/wR5gXlibmTg" --mode page --gap 1 -o "output/hibana.pdf"

# Local video with an explicit crop (left, top, right, bottom; each 0 to 1)
.\.venv\Scripts\python -m drumscore "video.mp4" --crop 0.02 0.78 0.98 1 --interval 0.25 -o "output/score.pdf"

# Export saved inclusion/order edits without scanning the video again
.\.venv\Scripts\python -m drumscore --project "output/score_XXXXXXXXXX/project.json" -o "output/revised.pdf"
```

Other options: `--title`, `--start`, `--end`, `--threshold`, `--paper A4|Letter`, and `--keep-overlap`. Link timestamps are not used to trim the song; specify `--start`/`--end` explicitly.

## Development and checks

```powershell
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\.venv\Scripts\python -m pytest -q
```

The tests exercise synthetic video decoding through extraction and PDF export, stable-view deduplication, later repeated passages, overlap removal, single-note changes, colored noteheads, cropping, compact page segmentation, invalid input, project persistence, and cancellation.

For the supplied real-world examples, `scripts/validate_examples.py` reads videos named by YouTube ID from `samples/` and creates PDFs and a machine-readable report in `output/examples/`. This script does not download videos. Videos, reference PDFs, generated PDFs, and local validation artifacts are not included in the repository. The report records extraction results, not a claim of note-for-note equivalence to a reference score.
