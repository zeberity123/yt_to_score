# 0.17.3 - Guitar staff + TAB on score panels that change height

Automatic capture (and the AI method that keeps video images) now handles guitar videos
whose bottom panel shows a staff with a six-string TAB under it and resizes for every
line, such as `https://youtu.be/Wu-cyW2YopY`.

- **Guitar TAB with a staff above it is one system.** The score area, the line split and
  the follow option all use the staff + TAB pair, so chord names, section boxes and bar
  numbers above the staff stay with the line. A TAB without a staff behaves as before.
  Five of six strings are no longer mistaken for a staff, and a staff with a row of ledger
  notes is no longer mistaken for a TAB.
- **Follow changing score position follows the panel.** On a white panel the crop now
  ends at the panel's top and bottom edges instead of a fixed margin around the TAB, which
  used to cut off the staff above and could let moving footage in below. Guitar strings,
  frets or shelves in the footage are not treated as a neighbouring staff, and the crop is
  never narrower than the selected area, so a short final system prints at the same scale
  as the full-width ones.
- **A resizing or sliding white panel is detected automatically.** For Guitar TAB, Bass TAB
  and Piano the extractor samples the video first; when a white panel's top edge moves it
  follows the panel without the checkbox and says so in the extraction notes. Notation
  drawn directly over footage keeps its fixed area.
- **A wide playback cursor no longer splits a line.** Some arrangements print repeated
  strums in grey and turn them solid while a translucent cursor band is over them. The
  cursor band is now left out of the "has the view changed" comparison, so lines full of
  repeated strums are captured once instead of being discarded as unstable.

## Evidence from the example video

Before: with a fixed area, chord names were clipped on taller panels; with the follow
option only the TAB was kept. After the pairing and follow fixes alone, 30 lines were
captured with bars 45, 69–76 and 113–118 missing, three lines duplicated and 81 samples
discarded. With the cursor fix: 32 lines at even intervals for bars 1–123 (31 four-bar
lines and the two-bar line at 117), all 1920 px wide, 5 transition samples discarded,
no duplicates. Tempo and "Solo" marks that the video itself clips at the panel edge
stay clipped. Capture took about 3 minutes for the 3-minute video.

Eight bass and piano sample videos give the same line counts as before with and without
the follow option, with one intended difference: a bass video whose panel slides into
place during the intro (`21XgHm-Oyhc`) used to capture its first line twice, the first
copy mid-slide with its stems cut off; it is now captured once, whole.

## Validation

- Full Python suite: 265 passed, including four new tests with a synthetic staff + TAB
  panel (`tests/test_guitar_pair.py`): pairing and ledger rows, panel-edge following and
  width, cursor masking, and end-to-end extraction of a resizing panel.
- Source Electron checks passed: `scripts/test-instruments-desktop.cjs` (eight bass/piano
  videos), `scripts/test-flexible.cjs`, `scripts/test-guitar-desktop.cjs` and
  `scripts/test-desktop.cjs`. The first two were updated for the current interface
  (Chords & lyrics as an instrument, "Bass TAB" label), which they predated.
