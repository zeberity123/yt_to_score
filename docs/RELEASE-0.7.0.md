# Video Sheet to PDF 0.7.0

- Extends small-panel-shift duplicate handling to Drums, Bass and Piano. Matches
  require consistent barline movement; moving a note alone does not establish a
  panel shift. Both piano staves and combined bass staff/TAB are compared together.
- Standalone four-string bass TAB gets higher-resolution fret comparison,
  suppression of highlighted string fragments, and conservative overlap joins
  at matching barlines. Original panels remain available in **Edit crop**.
- Tightly cropped four-string TAB stays detectable after splitting into lines,
  including panels with little blank space above or below the strings.
- Drums now shares thin colored playback-cursor cleanup with Bass and Piano.
- Retains later returns to a passage, uncertain overlaps, and newly exposed
  notation at panel edges. Combined bass notation and piano use complete-system
  matching; partial-measure joins are limited to standalone TAB.

Regression coverage includes individual fret changes, drum pitch/notehead/rhythm
changes, either piano hand, moving highlights, gradual panel drift, and restoring
the original capture after an overlap join. Reference comparisons cover the first
26 seconds of five bass, three piano, and three drum videos. The bass example
`QsCv8s5nTmo` now joins two repeated measure sections at matching barlines.
All 103 Python tests passed. Desktop checks also passed for all eight bass/piano
examples and all three guitar examples, including crop editing, project/PDF
export, translations, and mobile layouts.

Select the appropriate notation mode and **re-extract** to use these changes.
Existing project captures and manual capture behavior remain unchanged. Opaque
overlays, continuous scrolling, and unusual layouts can still need manual review.

Download and double-click the portable Windows x64 EXE. Python, FFmpeg, and Node.js
are bundled; no separate installation is needed. The EXE is unsigned.
