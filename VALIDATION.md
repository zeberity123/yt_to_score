# Validation

Verified in this Windows workspace on 2026-09-24.

- **16 automated tests passed** (`python -m pytest -q`).
- Desktop workflow passed: local video loading, frame preview, threaded extraction, review, project saving, and PDF export.
- Windows display scaling and visibility of Export PDF, progress, and Cancel were checked.
- An actual YouTube link was downloaded through the application's own downloader and exported as a PDF.
- All six supplied videos were downloaded and processed. PDF page counts and embedded line counts were checked. Representative rendered pages were visually inspected against the videos and supplied reference layouts.

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
