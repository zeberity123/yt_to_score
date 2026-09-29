# Video Sheet to PDF 0.12.0

- Added **Duplicate** beside **Exclude line**. Copies retain crop and height
  settings, can be edited independently, and survive project save/reopen.
- Tightened automatic cropping for standalone white bass TAB over footage.
- Added recovery for moving bass TAB with readable consecutive bar numbers.
  It checks scrolling positions at video frame rate, chooses clearer portions
  of each numbered bar, and joins them four at a time. Uncertain numbering
  falls back to ordinary extraction. Gaps and bright backgrounds are flagged.
- Preserved an uncertain ending through its visible closing barline for review.

Identical notation held across two musical repetitions still requires Duplicate
or Manual capture because there is no visible repeat boundary. The supplied
SPYAIR project was restored to 23 lines by duplicating line 05.

The Ado example remains a partial recovery: 132 numbered bars plus an uncertain
ending capture, arranged into 36 lines. Bars 21, 22, 43, 44, 78, 108, 109, 137,
and 138 need manual capture. Some captured bars still have background artifacts.
The recovered sample projects are separate from the portable application.

The Windows portable EXE includes Python, Node.js, and FFmpeg.
