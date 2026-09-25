Video Sheet to PDF now runs as a standalone Windows x64 application. Download
`Video-Sheet-to-PDF-0.3.0-win-x64.exe` and double-click it. Python, FFmpeg, and Node.js
are bundled; no separate setup is required. Internet access is needed for YouTube downloads.

- New PDF defaults: 0 mm line gap and 3 mm left/right margins.
- **For print** applies a 0 mm gap and 12 mm left/right margins.
- Responsive Electron interface with the video on the left and compact controls on the right.
- Automatic extraction and manual capture of visible notation for any instrument.
- Crop or expand individual captured lines in Review & export.
- Audio playback, mute, volume, and speeds up to 3x; review audio is optional and off by default.
- Arrow keys select the previous/next captured line in Review & export.
- Title-named portable projects and PDF exports, with eight common paper sizes.

Working projects and cached videos are stored in `%APPDATA%/Video Sheet to PDF/output`.
**Save project** exports a portable `.drumscore` archive containing the source images
needed for later crop edits. This release captures visible notation; it does not
transcribe sound into notes. Standalone Android is not included in this release.

The executable is unsigned, so Windows may display an unknown-publisher warning.
`SHA256SUMS.txt` contains the download checksum. Dependency notices are included
in the application bundle.

Validation: 50 Python tests; packaged desktop extraction/edit/save/export checks;
packaged audio, review, keyboard, and responsive-layout checks; portable launcher
and video/audio conversion with no system Python, Node.js, or FFmpeg on PATH.
