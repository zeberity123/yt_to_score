# 0.17.5 - Duplicate rows on scrolling drum pages

Automatic extraction now handles drum pages whose viewport moves in steps while
showing several overlapping score rows, including `CSyB2EIFNqs` and `PivrPuH1NrA`.
The same fixes apply to the capture stage of AI's **Keep video images + AI check**
method. They do not change full AI notation transcription.

Two causes combined to produce duplicates. Titles and credits attached to the
first visible row disappeared when the page scrolled, so that row stopped matching
its earlier capture. Also, staff rules sometimes remained visible at a screen edge
while the stems or flags above/below them were clipped. One failed row comparison
prevented removal of the whole overlapping block.

Row comparison now excludes distant page headings while keeping the nearby
notation, row numbers and directions. The original printable row still retains
its title and credits. Edge-clipped rows are deferred until a complete view is
available. Confident printed row-number readings provide additional evidence that
identical rhythms belong to different occurrences. Ambiguous labels fall back to
musical matching; compression noise does not establish a different row number.
Consecutive matching still preserves later page returns.
Disabling overlap removal retains the unfiltered captures for manual editing.

## Video checks

With the same default half-second sampling:

| Video | Before | After |
| --- | ---: | ---: |
| `CSyB2EIFNqs` | 156 rows | 38 rows |
| `PivrPuH1NrA` | 130 rows | 37 rows |

The second extraction used the selected area saved in the supplied
`ヒューマノイド_ドラム.drumscore`. Its 37 rows match the reference's complete
sequence of printed row-start numbers, including changes in the bar range around
the multi-measure rests. This is a count/order comparison; the user's manual crop
and page-spacing adjustments are not copied into the new extraction.

Evidence: `diagnostics/drum-scroll/{baseline,fixed}/`, their `summary.json` files,
and `diagnostics/drum-scroll/reference-label-comparison.png`. The final automatic
area checks, validation results and artifact details are recorded below.

Automatic area detection also produced 38 and 37 rows respectively, without a
manual rectangle, BPM input or timing recovery. The final matching rules replayed
all 53 and 50 saved stable views with the same counts. Results are recorded in
`diagnostics/drum-scroll/verified-auto/` and `replay-summary.json`.

Corrected portable projects are under `output/drum-duplicate-fix/`. The original
project in Downloads was only read. Both projects retain editing sources and
original-colour images.

Five new regression tests cover heading disappearance, clipped high/low stems,
capture of whole rows after scrolling, overlap-removal disabling, different bar
numbers on identical rhythms, later page returns, thin serif digit fragments and
rejection of a text label. Existing notehead, pitch, rhythm, TAB and piano matching
tests are also included in validation.

The final targeted capture/matching suite passed 72 tests, and the full Python
suite passed 271 tests. The packaged checks are recorded below. No AI inference was
used for the drum-video tests.

The packaged application extracted the first 45 seconds of `PivrPuH1NrA` into
eight complete rows with Automatic area detection in 40.75 seconds, matching the
full-run row sequence at that endpoint. This real packaged regression uses the
source video rather than mocked extraction responses. It can be run with
`node scripts/test-drum-scroll.cjs` after downloading the supplied test video
into `diagnostics/drum-scroll/cache/`.

The final portable executable passed startup, bundled media conversion, manual
capture, duplication, print defaults and shutdown cleanup with development tools
removed from PATH. Artifact: `dist/Video-Sheet-to-PDF-AI-0.17.5-win-x64.exe`
(221,229,161 bytes). SHA-256:
`aa4975e2f9eb1f61026eed49f71f80b933e211fafb6068b44ab0509e9b3ec433`.
