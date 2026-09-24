# Validation

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
