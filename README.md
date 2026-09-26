# Video Sheet to PDF

A Windows Electron app that turns the **sheet music already visible in a YouTube video** into a printable PDF. Its responsive web interface connects to a local Python processing engine. It captures and arranges the score images; it does not transcribe the audio or produce editable MusicXML.

The workspace uses a charcoal and teal studio theme, with white score previews
and print output. Capture, review, crop editing, and phone layouts share the same controls.

## Start

For Windows x64, download `Video-Sheet-to-PDF-0.9.1-win-x64.exe` from the
[GitHub release](https://github.com/zeberity123/yt_to_score/releases/tag/v0.9.1)
and double-click it. This portable executable includes Python, FFmpeg, and Node.js;
no separate installation is needed. The first launch extracts the bundled app.
Working projects and cached videos are stored under
`%APPDATA%/Video Sheet to PDF/output`. Use **Save project** to keep a portable copy
wherever you choose. This release is unsigned, so Windows may display an unknown-publisher warning.

To run from source instead:

Install Python 3.11 or newer (with “Add Python to PATH”) and Node.js LTS, download or clone this repository, and run `setup.bat` once. Then **double-click `run.bat`** to open the Electron app. Without Node/Electron, the launcher opens the same interface in your browser instead. Keep its terminal running while using the browser version.

If dependencies are already installed in this workspace, you can go straight to `run.bat`. FFmpeg is installed as a Python dependency if there is no system FFmpeg. Internet access is needed to download dependencies and YouTube videos.

1. Paste a YouTube video link, or choose a local MP4/MKV/WebM/MOV/AVI.
2. Click **Load video**. The green rectangle marks the detected score area.
3. Check the preview. Drag a rectangle to adjust the crop if needed. The time slider updates the displayed frame immediately. Include tempo markings, section letters, and symbols above/below the staff.
4. In **Automatic** mode, click **Extract score lines** in the right sidebar of **Capture**. The video and timeline occupy the left side. Expand **Extraction settings** for sampling, change threshold, and start/end options. The controls column keeps its width when switching modes.
5. In **Review & export**, select lines to inspect them. **Exclude line** removes a line from the list and PDF; **Undo** restores it. Move a selected line up/down, or click **Edit crop** to crop or expand it.
6. Set the PDF title, paper size, line gap, and left/right margins, then click **Export PDF**.

The default line gap is 0 mm, with 3 mm left and right margins. **For print** sets the gap to 0 mm and both side margins to 12 mm (1.2 cm). Images retain their aspect ratio and lines never split across PDF pages. **Export PDF** opens a desktop save dialog; the browser version downloads the PDF. **Save project** creates a portable `.drumscore` file using the **PDF & project title**, including original source images and edits.

Paper sizes: A4 (default), A3, A5, B4 and B5 (ISO), Letter, Legal, and Tabloid. **Save project** sits immediately to the left of **Export PDF**.

Choose **English**, **한국어**, or **日本語** from the language menu immediately left of **Open project**. Controls, progress, review notes, and crop editing update immediately. The desktop app remembers the language across launches. Your project titles and filenames stay as entered.

Choose an instrument under **Notation** before loading or extracting:

- **Drums** (default): the existing five-line staff workflow.
- **Guitar TAB (6 strings)**: six-string TAB, including white notation over dark footage.
- **Bass**: four-string TAB, either by itself or paired with standard notation above it. A paired staff and TAB stay together as one score line.
- **Piano**: paired treble and bass staves stay together, including dynamics and pedal markings.

Bass and Piano detect score panels at the top or bottom of the video and complete systems on score pages. Check the detected crop before extracting, especially when the layout changes. Projects remember their notation mode; the `.drumscore` extension remains compatible with existing projects.

Guitar extraction handles stationary panels that advance in steps. It ignores moving playback boxes and joins confidently matched overlapping panels at barlines; full panels remain available through **Edit crop**. Check partial measures at panel edges: uncertain overlaps are retained, and continuous scrolling, combined staff-plus-TAB systems, or other string counts may need manual capture. This is image capture, not editable tablature or audio transcription.

Guitar comparison masks string-rule fragments and tolerates small panel nudges,
so moving highlights and minor shifts create fewer duplicate captures. Automatic
cropping keeps the full panel width and upper annotations. Real fret changes and
later returns to a passage remain part of the score. A transient selection box
at the start of an editor recording can still create an extra initial line;
remove it in Review, or set the extraction start after that transient.

Drums, Bass and Piano also tolerate small panel nudges when barlines confirm that the whole panel moved. Both piano hands and combined bass staff/TAB remain part of the comparison. Changed noteheads, pitches, rhythm marks and new notation exposed at panel edges prevent an uncertain alignment from discarding a capture. Thin colored playback cursors and light washes are filtered; an opaque cursor hiding notes can still require review.

Standalone four-string Bass TAB uses finer fret comparison and masks highlighted string fragments. Confident horizontal overlaps join at common barlines, with full panels retained for **Edit crop**. Combined bass notation and Piano use complete-system matching instead of partial-measure joins. All modes work best with stationary panels that advance in steps. Reflowed or uncertain overlaps can remain and need **Exclude line** or **Edit crop**. Bass TAB with five or six string rules and piano layouts with more than two staves per system currently need manual capture.

Left and right margins can each be set from 0 to 40 mm, including decimal values. Smaller margins enlarge the score lines to fill the available width; top and bottom margins stay at 12 mm. White space inside a captured image is controlled by the score-area crop. Choose side margins that fit your printer's printable area.

## Manual mode

Use this when you want to choose every line yourself, including scores at the top of a video or layouts that automatic extraction misses.

1. Select **Manual** in the **Capture settings** panel of the **Capture** tab and load your video. Starting a manual session returns the preview to the beginning.
2. Drag a rectangle around **one complete score line**, wherever it appears on screen.
3. Press **Play**. Choose **0.5x**, **1x**, **1.5x**, **2x**, **2.5x**, or **3x** from the speed menu. **Pause** stops at the displayed frame. Playback includes sound when the source has an audio track; use **Mute** or the volume slider to control it. These playback controls are available in both modes.
4. Click **Add line** in the right sidebar each time you want to capture the line currently shown. Playback continues, the counter increases, and the capture is saved immediately.
5. Open **Review & export** when finished. Remove unwanted captures or reorder them, then export the PDF as usual. **Undo** restores the last removed line, including its crop edits.

Every click appends one original-resolution image of the selected rectangle in click order. Manual mode does not detect staffs, filter similar lines, change colors, or remove repeated lines. Automatic extraction is not required first. Drag the seek slider to jump to another time; the crop stays in place. Adjusting the crop pauses playback. **Audio in Review & export** defaults on for a new video and Manual mode, so playback continues across tabs. Automatic extraction pauses playback and turns review audio off. You can enable it again in review or press **Space** to start playback. Review shares the capture player's position, speed, and volume.

Automatic results and manual captures are kept separately while the current video is loaded. Switching modes restores that mode's list. Loading another video starts a fresh session; existing captures remain saved under `output/manual_*/project.json` and can be reopened for review/export.

## Supported layouts

- A score strip beneath performance footage.
- Full-screen score pages, separated into individual staff systems.
- Pages that scroll in steps and retain some lines from the preceding view.
- Light colored playback highlights, colored drum noteheads, and many translucent score backgrounds.
- Six-string guitar TAB on white panels or in white over dark footage, using **Guitar TAB** mode.
- Four-string bass TAB and paired standard-notation/TAB systems, using **Bass** mode.
- Piano grand staffs at either edge of the video or on full pages, using **Piano** mode.

Each stable view is sampled over time. The extractor uses a median of sampled images to reduce moving highlights. Automatic extraction removes matching lines at successive page boundaries; **later returns to a previous passage are kept**. Use manual capture for intentional repeated lines at a page boundary, or the CLI's `--keep-overlap` option.

## Review and recovery

Use **Down/Right** to select the next captured line and **Up/Left** for the previous line. Selection stops at the first or last line, and the selected thumbnail stays visible. Arrow keys retain their normal behavior in text fields, number inputs, menus, and the crop editor.

**Space** plays/pauses in either tab, including when a button or thumbnail has focus. Text fields still accept spaces normally. **Exclude line** removes the selected line immediately; **Undo** restores removals in reverse order for the current project's session. Removed lines are omitted from saved projects. Exclusions in older projects open hidden and can be restored with Undo.

**Edit crop** opens the retained original frame for a selected line. Drag a corner outward to recover more notation, inward to crop, or drag inside to move the selection. You can also enter exact percentage edges. **Apply crop** saves a new image; **Cancel** discards the pending crop. **Restore original** restores the first captured line, including the automatic extractor's original cleanup. Automatic edits use the retained cleaned source frame; the initial automatic line uses the median of sampled frames.

New captures keep their complete source frame, so crop expansion still works after saving and reopening a `.drumscore` project without the video. Older `project.json` files are supported, but their editor can only recover pixels inside the original stored line image. It cannot reconstruct pixels that were never saved.

### Compact TAB printing and height correction

In **Review & export**, enable **Arrange TAB bars** for guitar or standalone
four-string bass TAB, then choose a **Target bars per line** from 4 to 16 (starts
at 6). **Preview print lines** shows the resulting rows before PDF export.
Captured lines remain unchanged in the sidebar. Measures keep their order and
all image columns are retained. Double barlines count as one boundary. Uncertain
or combined staff/TAB lines stay intact and are listed in the preview notes.
Short final rows are not stretched to fill the page. Turning the option off
returns to one captured image per print line.

For dense passages, use **Bars on this line** in the print preview to choose
1–16 bars for that individual row. Try 3 or 4 instead of 6 when the notes become
too small. A completed exception row uses the full print width. Select **Default**
to remove the exception. Exceptions follow their starting bar when earlier rows
change, and are saved with the project and used in the PDF. Changing a source
crop requires setting its exceptions again; height changes preserve them.
Click outside the preview or press Escape to close it.

In **Edit crop**, adjust **Line height (%)** to correct vertically stretched
notation. 100% is the original ratio; 75% reduces only the height. The range is
25–200%. Use **Apply height to all lines** for a consistent correction across the
score, or leave it off to edit one line. The result preview updates immediately.
**Restore original** resets that line's crop and height. Source images stay intact,
and repeating a height edit replaces the percentage instead of compounding it.
Height correction works with every instrument and with captured or arranged rows.

Both settings are saved in projects and work on existing captures without
re-extracting. Duplicate-detection improvements remain the default for all new
automatic extractions; existing captures are never silently re-extracted.

Extraction is heuristic. Review the result before printing, especially dense annotations, transitions, partial lines at screen edges, and translucent overlays. Closely packed text can be associated with the neighboring line.

- **Missed short views:** reduce “Sample every” from `0.5` to `0.25` seconds. A view must survive at least two samples.
- **Similar lines merged:** lower the change threshold (for example, `0.02`). Lower values can also produce more duplicates.
- **Too many duplicates:** check that the crop excludes moving footage. Exclude unwanted lines in the review list; increase the change threshold cautiously.
- **Missing line:** adjust the automatic crop, sampling interval, or time range and extract again. For layouts that automatic extraction misses, use Manual mode to capture the required lines. Automatic and manual lists are separate.
- **Continuous scrolling or animated notation:** automatic extraction may miss or repeat material. Capture stable views manually or use a different source video. A score that stays visually identical across consecutive repetitions cannot reveal those repetition boundaries.
- **Low-resolution source:** PDF quality is limited by the video. The downloader requests video up to 1080p, preferring H.264 for decoder compatibility.

The original reference PDFs are never modified. Every extraction gets a new working directory under `output/` containing lossless line PNGs, retained source frames, and `project.json`. Inclusion/order/crop edits are saved there. **Save project** exports a title-named `.drumscore` bundle; use **Open project** to reopen it. The desktop file picker also accepts legacy `project.json` files (keep their PNGs together). Browser users can upload `.drumscore` bundles or local videos; videos are processed on the computer running the Python server.

YouTube downloads are cached in `output/cache/`. If YouTube rejects a download, update the downloader with:

```powershell
.\.venv\Scripts\python -m pip install -U "yt-dlp[default]"
```

New YouTube downloads request both video and audio. To get sound for a previously downloaded video-only source, load its original YouTube URL again; the app uses a separate cache for downloads with audio. Local files without an audio track remain silent.

If YouTube rejects a media URL with HTTP 403, the downloader requests fresh URLs and tries alternate clients while preserving the available resolution and audio. This recovery runs within the current app session. YouTube restrictions can still prevent some downloads.

Export staging copies are removed after a successful download, or when a desktop download is cancelled. Desktop shutdown removes that session's remaining export staging files. Saved `.drumscore` files, PDFs, working projects, and source images are retained.

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

# Export for screen viewing with no left or right page margin
.\.venv\Scripts\python -m drumscore --project "output/score_XXXXXXXXXX/project.json" --left-margin 0 --right-margin 0 -o "output/screen.pdf"
```

Other options: `--title`, `--start`, `--end`, `--threshold`, `--paper A4|A3|A5|B4|B5|Letter|Legal|Tabloid`, and `--keep-overlap`. Link timestamps are not used to trim the song; specify `--start`/`--end` explicitly.

Use `--notation guitar`, `--notation bass`, or `--notation piano` for the corresponding instrument. `--notation staff` remains the compatible CLI name for **Drums** (default). Non-actionable downloader warnings are hidden from workspace progress; final download failures still appear.

## Development and checks

```powershell
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\.venv\Scripts\python -m pytest -q
npm install
npm run test:desktop
npm run test:playback
```

Build the standalone Windows executable on Windows x64:

```powershell
.\.venv\Scripts\python -m pip install -r requirements-build.txt
npm ci
npm run build:win
```

The executable is written to `dist/`. The build includes the processing engine,
web UI, FFmpeg, a Node.js runtime for YouTube challenges, and dependency notices.
Only application files are bundled; samples, cached downloads, and user projects
are excluded. See [release build details](docs/BUILD.md).

`npm start` opens Electron. `python -m drumscore` opens the browser interface; `python -m drumscore --legacy-ui` opens the previous Tkinter UI. The CLI extraction/export commands above remain supported. Electron/browser playback uses supported original MP4/WebM codecs; other formats get a cached compatible preview with audio preserved. When only the audio needs conversion, the video is copied without re-encoding. Extraction and manual captures keep using the original-resolution source. The legacy Tkinter preview remains silent.

The desktop shell uses an isolated, sandboxed renderer with Node integration disabled, following [Electron's security guidance](https://www.electronjs.org/docs/latest/tutorial/security). The Python API binds to loopback by default and requires a random per-session token. Close Electron to stop its local processing engine. No account or remote service is used for score processing.

## Android direction

The interface adapts to phone widths and supports touch crop handles. `web/` contains the shared interface and `web/api.js` isolates platform communication. **This release is a desktop/browser app, not a standalone Android APK.** Python processing still runs on the host computer. The intended next platform is standalone Android: it needs an on-device video/extraction/export adapter and native file storage, rather than a connection to a desktop server. See [the Android implementation notes](docs/ANDROID.md).

The tests exercise synthetic video decoding through extraction and PDF export, stable-view deduplication, later repeated passages, overlap removal, single-note changes, colored noteheads, cropping, compact page segmentation, invalid input, project persistence, and cancellation.

For the supplied real-world examples, `scripts/validate_examples.py` reads videos named by YouTube ID from `samples/` and creates PDFs and a machine-readable report in `output/examples/`. This script does not download videos. Videos, reference PDFs, generated PDFs, and local validation artifacts are not included in the repository. The report records extraction results, not a claim of note-for-note equivalence to a reference score.
