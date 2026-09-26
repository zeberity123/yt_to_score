# Validation

## Chord backgrounds and cropped TAB arrangement — 2026-09-26

- All **145 Python tests passed**, including reversible White/Black/Original
  background rendering, faint string preservation, archive round trips, and
  complete-column measure partitioning with a margin after the final barline.
- The user-provided `screen_sample/tuki_test1.drumscore` contains 29 two-bar
  captures. All 58 measures now arrange into 15 rows at four bars per row
  (the last row has two), with no unconfirmed-boundary warnings. White and
  black PDFs each have two pages; stored captures remain unchanged.
- Re-exported the supplied chord project with white and black backgrounds;
  each PDF has five pages. Reviewed rendered PDF pages and the sample's
  Japanese glyphs after background removal. Outputs and editable projects
  are in `output/review-updates/`.
- Packaged desktop checks passed Chord naming in all three languages,
  White/Black/Original review rendering, the Extraction settings button and
  chevron, crop editing, undo, mode isolation, mobile layout, and the actual
  tuki project's four-bar black-background print preview.
- Removed the requested reference-video paragraph from the published GitHub
  README in commit `1026c5e7e54b9d921b59e2d0cf4ad0f0e82776b7` and verified the
  reference is absent. The same paragraph is removed in the local README.
- Built `dist/Video-Sheet-to-PDF-0.11.0-win-x64.exe`; its SHA-256 is saved in
  the adjacent `.exe.sha256` file.

## Free chord/lyric capture — 2026-09-26

- Built `dist/Video-Sheet-to-PDF-0.10.0-win-x64.exe` (211,970,697 bytes).
  The packaged Free-mode test passed capture, editing, undo, mode isolation,
  translations, and mobile layout. The final single EXE passed the portable
  test with only Windows system tools on PATH, including bundled video/audio
  conversion, capture, and shutdown cleanup. Its SHA-256 is saved beside it
  in `Video-Sheet-to-PDF-0.10.0-win-x64.exe.sha256`.
- Added Free as a third capture mode with a manually drawn region and automatic
  detection of outlined blue chord rows and white lyric rows. Original colors
  and full source frames remain available for crop editing and portable projects.
- The supplied `screen_sample/test1.png` detects four rows. Synthetic video
  regressions cover one/two/four rows, moving bright backgrounds, actual chord
  changes, consecutive overlap, later repeats, blank intervals, cancellation,
  crop restore, PDF export, and independent mode/undo state.
- The full Python suite passed (136 tests); after the final detector refinements,
  the focused Free/API suite passed (16 tests). Electron's
  `npm run test:free` passed extraction from four rows to one, crop editing,
  remove/undo, mode switching, English/Korean/Japanese labels, and mobile layout.
- Downloaded `7JNB7yOfx9E` and processed **371–625 seconds**, at 0.5-second
  intervals, with crop `(0, 300/1080, 1, 745/1080)`: **100 rows from 30 accepted
  views**, exported to **5 PDF pages**. Four unstable sampled views were skipped;
  16 repeated boundary rows were removed. The example `.drumscore` archive
  reopens in Free mode with all source images.
- Example outputs: `output/free-example/Chords and lyrics.drumscore` and
  `output/free-example/Chords and lyrics.pdf`. These are reviewable automatic
  results: a compression-dependent duplicate remains near 6:40. Small chord
  diagrams or blue annotations inside the rectangle remain in the original
  images; Capo4 and the bottom score panel are outside this crop.

## Earlier validation

Verified in this Windows workspace on 2026-09-24.

- **20 automated tests passed** (`python -m pytest -q`), including exact manual crops, repeated captures, click order, save failure recovery, playback speed/pause/seek, end-of-video replay, and decoder cleanup.
- Desktop workflow passed: local video loading, frame preview, threaded extraction, review, project saving, and PDF export.
- Windows display scaling and visibility of Export PDF, progress, and Cancel were checked.
- An actual YouTube link was downloaded through the application's own downloader and exported as a PDF.
- All six supplied videos were downloaded and processed. PDF page counts and embedded line counts were checked. Representative rendered pages were visually inspected against the videos and supplied reference layouts.
- Manual mode was checked with the cached `1y9UCfJrATc` video: 11 captures of a top-of-screen rectangle, including a capture during 2x playback, saved and exported successfully. Captured PNGs matched the displayed crops pixel for pixel. Play/pause, seeking, mode switching, and control visibility at 960x720 and 1180x860 were checked. This did not change or retest automatic detection for that video.

| Video | Score | Extracted lines | PDF pages |
| --- | --- | ---: | ---: |
| kgNjaXTh0rU | 地球最後の告白を | 45 | 4 |
| 4K47HiVS1_o | 裸の勇者 | 32 | 4 |
| nlAG7LyzshM | 閃光 | 58 | 5 |
| 23xBxqLPHa0 | 夜咄ディセイブ | 26 | 3 |
| wR5gXlibmTg | ヒバナ | 43 | 5 |
| RfXr5bDboyI | それがあなたの幸せとしても | 23 | 2 |

PDFs, editable extraction projects, and `validation.json` are in `output/examples/`. These outputs were generated from the videos, not copied from the reference PDFs. The original references were only read.

This validates the workflow, not note-for-note transcription accuracy. Dense annotations can attach to a neighboring staff, faint marks can be affected by video quality, and transitions can produce duplicates or omissions. The app provides crop adjustment, sample/threshold controls, exclusion/reordering, and manual insertion for review and correction. Exported notation remains a raster image rather than editable musical notation.
