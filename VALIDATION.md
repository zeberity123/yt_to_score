# Validation

## Flexible score area and all-instrument timing — 2026-09-28

- Reproduced the missing 183-second bass system and detached rest-count “2”
  in cached `f5VnaleBDJM`. A faint fifth rule was detected as a four-string
  TAB subset at a second threshold, creating overlapping system groups.
- Excluding that subset restores both 183 and 189.5-second systems and keeps
  the rest-count annotation with the 196-second system, with timing disabled.
- Full 260.28-second video extraction with optional flexible area, 0.5-second
  sampling, and timing disabled produced 34 lines. Visually inspected lines
  25–28 and 34: the missing line is present, the “2” remains above the rest,
  and the lowered final TAB staff is complete. First ten lines were also
  inspected for annotation clipping. This is not note-for-note verification.
- Full extraction took 308 seconds with other validation running concurrently;
  this is not an isolated performance comparison. Flexible area remains opt-in.
- Saved `screen_sample/f5VnaleBDJM_updated.drumscore` and a five-page PDF, plus
  `screen_sample/f5VnaleBDJM_fixed_lines.png` for visual review. User originals
  and application projects were only read.
- **190 Python tests passed**, including faint-rule grouping, shifted paired
  staff crops and source coordinates, full-page preservation, incomplete bars,
  and drum/piano timing recovery. The existing SPYAIR held-line fixture still
  recovers exactly one repeat at 50.5 seconds, yielding 23 lines.
- Desktop workflow verified all four notation types expose BPM and optional
  flexible-area controls; Chord hides them. Fresh extraction of 176–204 seconds
  produced four lines, with zero timing copies at 145 BPM. Korean/Japanese
  translations and mobile layout passed.
- Repeated the new workflow against the packaged 0.15.0 backend and UI.
  Packaged Ado regression checks also passed: four-bar layouts, source-color
  Off mode, matching PDF-preview geometry, Black/White switching, and the
  older-project notice.
- Built `dist/Video-Sheet-to-PDF-0.15.0-win-x64.exe` (212,693,073 bytes).
  SHA-256: `3560358ea1c21af78f562b895db78e7d95473646ce70b667d6237bb12b342e29`.
  The finished single EXE passed bundled conversion, capture, Duplicate,
  print-default/preset, and shutdown tests with system-only PATH.

## Numbered-bar layout and reversible source colors — 2026-09-28

- Reproduced the reported five-bar print rows 2, 17, and 26 from the user's
  latest Ado extraction, copied read-only from the application workspace into
  diagnostics. Broken barlines caused the print formatter to merge adjacent
  musical bars while counting each merged span as one.
- Numbered extraction now stores confirmed column boundaries, bar numbers,
  and staff alignment. Print layout uses that metadata instead of detecting
  the damaged pixel barlines again. It survives archive/open and Duplicate.
- Automatic captures preserve separate source-color images. Review, crop
  preview, and PDF Original mode use matching raw geometry. Tests cover actual
  API pixels, archive round trips, independent duplicate crops, and original
  colors from ordinary automatic extraction as well as numbered composites.
- Old automatic projects show a notice when source colors were never stored.
  Existing manual/Chord captures remain directly reversible.
- Compared real Ado bars while developing patch selection and temporal noise
  rejection. A tighter neutral-color cutoff damaged tinted antialiased stems;
  it was reverted and a regression test now protects those strokes. Cleanup
  uses source patches plus repeated clear observations, retaining bright-frame
  uncertainty. Persistent background objects and missing bars remain unresolved.
- The Electron interface check passed confirmed four-bar reflow, source-color
  Off, consistent White/Black/Original print geometry, and the old-project notice.
- A packaged UI check exposed a stale status-response race that could leave the
  print preview closed. Responses from polls begun before a command are now
  discarded. The interface test deliberately delays such a response and verifies
  that the preview still opens.
- Final Python validation: **182 tests passed**. The packaged app also passed
  a fresh extraction of Ado's first 45 seconds, checking stored bar identities,
  source-color images, crop detection, extraction warnings, and print preview.
- Final full Ado extraction recovered **131 numbered bars** plus an uncertain
  ending. Four-bar printing produces **33 four-bar rows and one short final row**
  (four PDF pages). Visually checked print rows 2, 17, and 26 and compared captures
  around bars 73–76 and 122–125 to confirm the relaxed filter preserves stems.
  Bars 9, 21, 22, 43, 44, 78, 108, 109, 137, and 138 remain missing; background
  artifacts still remain in several captures. Reviewable final files are
  `screen_sample/ado_cleanup_v014.drumscore` and `ado_cleanup_v014.pdf`.
- Built `dist/Video-Sheet-to-PDF-0.14.0-win-x64.exe` (212,685,685 bytes).
  SHA-256: `31e064e84223fbc26b05e32285d624dc4cd0312eeb9d6f6e17a5714bb251fa30`.
  The final packaged interface test passed, including a deliberately delayed
  status response. The final portable EXE passed conversion, capture, Duplicate,
  print defaults, and shutdown cleanup with only Windows system tools on PATH.

## BPM and timing-assisted repeats — 2026-09-28

- All **175 Python tests passed**. New coverage includes noisy audio pulses at
  three tempos, silence, cancellation, invalid settings, incomplete/combined TAB,
  two-bar lines, multiple identical passes, wrong tempo/meter, source gaps,
  first/final holds, and independently editable archived copies.
- Audio analysis of the cached original SPYAIR video estimates **113.0 BPM**,
  consistent across three sections. Ado's sections disagree and the UI marks its
  estimate uncertain. Estimates are editable and show half/double alternatives.
- Full SPYAIR extraction through the Electron interface, with manual **113 BPM**,
  **4 beats per bar**, and timing recovery enabled, yields **23 lines**. It adds
  exactly one copy after line 05 at **50.5s**, preserving lines 02/03 and shorter
  two-bar lines. The first/final holds do not create extra copies. Inferences
  are explicitly reported in project warnings; timing is not proof of a repeat.
- The interface test passed BPM detection, manual override, print preview,
  Korean/Japanese translations, a 390-pixel mobile layout, resetting settings
  when loading another video, and the uncertainty message for Ado.
- `screen_sample/spyair_timing_recovered.drumscore` and the corresponding
  two-page PDF contain the automatically inferred result. Originals are untouched.
- Numbered recovery continues to take priority over timing. No song IDs or
  per-song exceptions are present in extraction. Without readable bar numbers,
  irregular scrolling remains dependent on ordinary visual overlap matching.
- Built `dist/Video-Sheet-to-PDF-0.13.0-win-x64.exe` (212,716,494 bytes).
  SHA-256: `0ebadf131cf056d7f0015487039c71cb471a9cab03cc1ef10b5db6755b6bb997`.
  The packaged app passed the same full SPYAIR/BPM interface test. The final
  single-file EXE passed bundled audio/video conversion, capture, Duplicate,
  print defaults and shutdown cleanup with only Windows system tools on PATH.

## Bass repeats and numbered-bar recovery — 2026-09-27

- Added Duplicate beside Exclude. API and archive checks cover insertion order,
  independent crop/height edits and print identities, save failure rollback,
  removal/undo, and print-preview invalidation. The Electron check passed in
  English, Korean, and Japanese, including a 390-pixel-wide viewport.
- Inspected both supplied archives and the cached original 1080p videos. SPYAIR
  holds the same notation from about 42 to 59 seconds without a visible repeat
  boundary. Automatic extraction still returns 22 lines; no timing-based repeat
  guess was added. `screen_sample/spyair_restored.drumscore` explicitly duplicates
  line 05 after itself (23 lines). The copy's approximate time is 50.5 seconds.
  Its PDF has two pages. The supplied archive is untouched.
- Tightened standalone white bass TAB cropping while preserving chord labels
  and rhythm stems. The Ado crop changes from approximately y=662–1026 to
  y=732–984 in the 1920×1080 video; horizontal width remains intact.
- Ado's scrolling transitions can last a single frame. The new specialized
  path checks bar positions at source frame rate, verifies adjacent numbers,
  reuses confirmed widths when footage hides a boundary, and chooses clearer
  vertical slices of each bar. Sparse or backward numbering falls back to
  ordinary extraction. No external OCR model or service is required.
- The full Ado validation recovered **132 numbered bars**, assembled into 35
  lines, plus an explicitly unconfirmed ending capture beginning at bar 142
  through the closing double bar (**36 lines**, five PDF pages). Reviewable
  outputs: `screen_sample/ado_recovered.drumscore` and `ado_recovered.pdf`.
  **This is a partial recovery, not a clean complete score:** bars 21, 22, 43,
  44, 78, 108, 109, 137, and 138 were not recovered. Bright-background warnings
  flag 12, 18, 33, 46, 51, 54, 56, 62, 81, 89, 94, 103, 117, and 120. Other
  background fragments remain visible too. Reviewed contact sheets and the
  rendered PDF; the warnings are retained in the portable project.
- Synthetic regressions cover unchanged notes in different numbered measures,
  cursors, missing boundaries, clearer alternate positions, numbering resets,
  unnumbered openings, uncertain endings with source-frame access, archive
  round trips, and gap reporting.
- Final validation: **157 Python tests passed**. The final Electron Duplicate
  check also passed, including selecting the copy when duplicating the last line.
- Built `dist/Video-Sheet-to-PDF-0.12.0-win-x64.exe` (212,690,116 bytes).
  SHA-256: `3d049b10a1f336da51bfd8f2b859cd651377541a140369239d54655679a01427`.
  The checksum is also saved in the adjacent `.exe.sha256` file.
- The packaged Duplicate check passed independent editing, removal/undo,
  last-line selection, translations, and mobile layout. The packaged bass check
  processed Ado's first 45 seconds and passed tighter cropping, numbered recovery,
  review warnings, and print preview. That shorter window recovered 25 bars and
  reported its remaining gaps; full-video source validation is described above.
- The final portable EXE passed with only Windows system tools on PATH:
  bundled video/audio conversion, manual capture, Duplicate, print defaults,
  and shutdown cleanup while retaining working projects. No GitHub release
  was published.

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
