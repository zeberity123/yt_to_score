# Video Sheet to PDF 0.8.0

- Optional **Arrange TAB bars** in Review & export combines captured guitar or
  standalone bass TAB measures into longer print lines. Choose a target of
  **4–16 bars**, starting at 6. **Preview print lines** shows the arrangement.
- **Line height (%)** in Edit crop corrects stretched notation, with a live result
  preview and **Apply height to all lines**. 100% preserves the original ratio;
  75% reduces height by one quarter. Restore original resets the selected line.
- Both settings work on existing captures and are saved with the project.
  Source images remain intact. The captured-line sidebar keeps its original order.
- Short final rows retain a sensible size. Uncertain bar boundaries and combined
  staff/TAB remain intact; preview notes identify lines that could not be arranged.
- English, Korean and Japanese controls, including responsive layouts.

The improved duplicate detection remains on by default for new extractions.
Re-extraction is needed only to apply detection changes to old captures; the new
print layout and height controls do **not** require re-extraction.

On the saved `_iF6NXbkCws` reference captures, using A4, 3 mm side margins and
0 mm gap: original layout **15 pages**; six bars **6 pages**; six bars with 75%
height **5 pages**; eight bars at original height **4 pages**. The arrangement
preserves captured image content rather than re-engraving music. Review ties,
annotations and partial measures at line breaks, and choose a readable size.

Validation: 121 Python tests, saved-project layout/ratio round trips, PDF geometry,
all three UI languages, and desktop/mobile workflow checks passed.

Download and double-click the portable Windows x64 EXE. Python, FFmpeg, and Node.js
are included. No separate installation is needed. The EXE is unsigned.
