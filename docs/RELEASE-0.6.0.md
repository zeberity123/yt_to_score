# Video Sheet to PDF 0.6.0

- Charcoal and teal studio theme inspired by Click's interface, including Capture,
  Review & export, crop editing, loading, and phone layouts. Score images and PDFs
  stay on white paper.
- Fewer duplicate guitar TAB captures caused by moving highlights, interrupted
  string rules, and small panel shifts.
- Automatic guitar cropping retains the full panel width and upper annotations.
- Better matching of overlapping horizontal TAB views at common barlines;
  complete source panels remain available in Edit crop.
- Tests cover small shifts, real fret changes, later repeats, and false string
  detection caused by dense annotation rows.

For the supplied `_iF6NXbkCws` video, select **Guitar TAB (6 strings)**, detect the
area again, and re-extract. Existing saved captures are not rewritten. Review
startup selection boxes and uncertain partial measures at panel edges.

Full-video comparison (246.6 seconds, identical full-width crop, 0.5-second
sampling and 0.035 threshold): **110 captures in 0.5.2 → 54 in 0.6.0**, with
49 overlapping views joined at matching barlines. This is a reduction in
captures, not a claim of note-for-note equivalence. Some startup/edge artifacts
can still need review. All 83 Python tests passed. Packaged checks also passed
for all three guitar examples, capture/edit/export, languages and restart
persistence, loading, audio/playback, mobile layouts, and standalone EXE startup.

Download the portable Windows x64 EXE and double-click it. Existing projects remain
compatible. Python, FFmpeg, and Node.js are bundled. The EXE is unsigned.
