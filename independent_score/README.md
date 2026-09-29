# Independent Ado TAB test

Output: **Ado_independent_4_bars.pdf** — six A4 pages, 143 numbered measures,
four measures per system except the final three-measure system.

Source: https://youtu.be/wpme40lu_XE

This experiment does not use the application's extraction, detection, cleanup,
tracking, repeat recovery, or PDF-layout code. The cached original video was
read directly with OpenCV. Its numbered TAB was visually inspected in contact
sheets and individual frames. Fret positions, rests, durations, ties, slides,
hammer-ons, muted notes, slap/pop markings, and the ending vibrato were entered
into `transcription.py`. A separate ReportLab typesetter, `engrave.py`, draws
vector notation from those entries. No video pixels are embedded in the PDF.

The source's displayed tempo is quarter note = 145, in 4/4. The transcript's
G/D/A/E identifiers identify the four TAB rows from top to bottom; the PDF uses
TAB labels rather than claiming that the instrument's tuning was verified.

Validation:

- All bar numbers 1–143 occur exactly once and in order.
- Every transcribed bar totals four quarter-note beats.
- Tied continuations match the preceding string and fret.
- All six rendered pages were visually reviewed, with additional checks of
  dense sixteenth-note passages, high fret numbers, and the final tied note.
- No raster images are embedded; lines and notation remain sharp when zoomed.

This is a visual transcription, not an independently audio-verified score.
Beat-total and tie checks do not prove that every fret or duration was read
correctly. The cleaner appearance comes from re-engraving the notation and
does not by itself establish higher musical accuracy than screenshot capture.

Rebuild independently with the existing Python environment:

```powershell
.venv\Scripts\python.exe independent_score\engrave.py
```

`transcription.json` contains the same entered notes and source-frame references
for review. The application's code and existing extracted projects were not
used to supply the notes for this experiment.
