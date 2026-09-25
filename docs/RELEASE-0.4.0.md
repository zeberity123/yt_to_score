# Video Sheet to PDF 0.4.0

- English, Korean, and Japanese interface, with a persistent language menu immediately left of the boxed Open project button.
- Translated controls, accessibility labels, progress, crop editor, and extraction notes. Project titles and filenames stay unchanged when switching languages.
- PDF titles use font fallback for mixed Korean and Japanese text, including Japanese characters missing from the Windows Korean font.
- Guitar TAB mode detects six strings, preserves fret numbers and rhythm marks, and makes white TAB over dark footage printable on white paper.
- Moving playback boxes are filtered during comparison. Confidently matched horizontal overlaps join at barlines; original panels remain available in Edit crop.
- Non-actionable downloader diagnostics, including Python deprecation warnings, no longer replace progress messages. Fatal errors remain visible.

Choose **Notation → Guitar TAB (6 strings)** before loading or extracting a guitar video. **Standard / drums** remains the default. Review partial measures at panel edges: uncertain overlaps stay intact. Continuously scrolling notation, combined staff-plus-TAB systems, and other string counts may require manual capture.

The Windows x64 portable EXE includes its processing engine. No separate Python or FFmpeg installation is required. Existing `.drumscore` projects remain compatible.

Validation: 63 Python tests; packaged English/Korean/Japanese switching and persistence; drum extraction, editing, project/PDF saving, playback, keyboard shortcuts, and responsive layouts; both supplied guitar videos through extraction and PDF export. The full 205.5-second white-panel guitar example was also processed. Automatic extraction remains heuristic: check for partial, missed, or repeated material before printing.
