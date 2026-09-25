# Windows release

Build on Windows x64 with Node.js and the project's Python environment installed.

```powershell
.\.venv\Scripts\python -m pip install -r requirements-build.txt
npm ci
npm run build:win
```

`scripts/build-windows.cjs` prepares assets and notices, freezes the Python server
with PyInstaller, and packages an Electron portable executable with electron-builder.
It downloads the license for the exact Node.js runtime being bundled if the local
installation does not contain it. Packaging tools and Electron may require downloads.

The output is `dist/Video-Sheet-to-PDF-0.7.0-win-x64.exe`. The unpacked application
is also available at `dist/win-unpacked/Video Sheet to PDF.exe` for verification.
The portable application extracts at launch and stores working data under Electron's
user-data folder (`%APPDATA%/Video Sheet to PDF/output`), outside the temporary app.

Run the normal UI checks against the packaged application:

```powershell
$env:SCORE_TEST_EXECUTABLE = (Resolve-Path 'dist/win-unpacked/Video Sheet to PDF.exe').Path
npm run test:desktop
npm run test:playback
npm run test:languages
npm run test:instruments
Remove-Item Env:SCORE_TEST_EXECUTABLE
npm run test:portable
```

Tests use isolated profiles in `diagnostics/`. The desktop workflow test expects
the reference video `samples/kgNjaXTh0rU.mp4`; the playback test generates synthetic
media. The portable check launches the final single EXE with only Windows system
tools on PATH and tests video/audio conversion using the bundled FFmpeg. Build
directories, diagnostics, samples, cached downloads, and private
projects are excluded from source control and the release.

`npm run test:guitar` additionally checks the three supplied guitar reference videos
stored as `diagnostics/guitar/t_dHA1lgeAU-av.mp4` and
`diagnostics/guitar/UDdLxCuqRQ8-av.mp4`, plus the duplicate-capture regression
`diagnostics/duplicates/_iF6NXbkCws-av.mp4`. They are local test inputs and are not
distributed. Automated Python tests cover synthetic six-string TAB, white ink
on moving dark backgrounds, changing fret numbers, playback boxes, and barline
overlap matching without external media.

`npm run test:instruments` checks the eight supplied bass and piano examples stored
under `diagnostics/instruments/<YouTube-ID>-av.mp4`. It verifies automatic capture,
crop editing, translations, PDF export, saved notation modes, and narrow layouts.
These videos are local test inputs and are not distributed. Python tests cover
four-string detection, combined staff/TAB systems, paired piano staves, preserved
left-hand changes, playback cursor cleanup, page overlap, and later repeats.

Duplicate regression tests additionally cover barline-confirmed panel nudges in
Drums, Bass and Piano, changed drum pitches/noteheads/rhythm, changed bass frets,
both hands of a piano system, new notation at panel edges, gradual scrolling,
four-string TAB overlap joins, and original-panel recovery after joining.

No signing certificate is configured. Release binaries are unsigned. Publish the
portable EXE as a GitHub Release asset rather than adding it to Git history, and
include its SHA-256 checksum alongside it.
