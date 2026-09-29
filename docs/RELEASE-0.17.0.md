# 0.17.0 - Automatic / AI / Manual, AI-checked image capture, AI edit, printed marks

Capture now has three modes. **Automatic** is the frame-capture extractor with its
original controls (score layout, detect area, extraction settings, audio tempo and
timing recovery); Chords & lyrics is an instrument choice there, no longer a separate
mode. **AI** keeps its own project slot. **Manual** is unchanged. Saved projects reopen
in the mode that made them; the old `free` mode name is accepted as an alias.

AI mode has a **Method** choice. **Keep video images + AI check** (default) uses the
video's own score images: one overview request finds the score, the frame extractor
captures the rows, and a few line-check requests read printed bar ranges, hide
duplicate rows (recoverable with Undo), reorder rows only when printed numbering is
confident and non-overlapping, and flag clipped or obscured rows with ⚑ notes. No
notation is redrawn unless you press **Re-transcribe with AI** on one line; the
captured image remains the line's original. **Re-engrave notation with AI** is the
previous full transcription.

Review & export gains an **AI edit** box for AI projects. One short text request
changes page layout, tempo and rehearsal marks, rest merging and line breaks, and
lists what could not be applied. Asking about wrong notes in specific bars re-reads
those bars from cached video frames through the existing targeted review; notes are
never rewritten from text. For image-capture projects the same box excludes, moves
or engraves lines.

Engraving fixes from the drum transcription of `https://youtu.be/gOcU3kUdNp8`:

- Bars carry `tempo_bpm`, `rehearsal` and `multirest` instead of free text. Tempo prints
  once as a real metronome mark (♩ = 110) and is not repeated on the next bar; section
  letters print as boxed rehearsal marks; older projects and journals are converted.
- Measure numbers appear at line starts only, so directions no longer overlap them.
- The instrument label ("Drums") is no longer printed on every row.
- Printed multi-measure rest blocks are kept as the video shows them. With the
  bars-per-line override on, runs of whole-bar rests merge by default; a checkbox
  turns that off.
- The YouTube title is used as the score title; the model no longer invents one.

Changing transcription settings still invalidates the response cache, and the journal
version changed, so a re-run after this release starts fresh.

## Validation

- Full Python suite: 258 passed. New coverage: legacy mark lifting, multirest
  follow/override, once-only metronome and rehearsal output with no part label,
  TAB marks, title passthrough, mode routing, chord-as-instrument extraction, AI edit
  with layout/marks/re-read, hybrid capture with duplicate exclusion, reorder rules,
  cancellation during the line check, per-line engraving and restore, the
  image-project edit path, and the rest-merge toggle round trip.
- Source Electron integration (`scripts/test-ai-integrated.cjs`) passed: mode buttons,
  method default and switching, AI dispatch for every connection and both methods,
  page settings, rest merging on/off, vector export, portable project, responsive UI.
  It caught one regression before release: un-merging rests did not restore the
  hidden bars because a merged row remembered only its first bar number.
  `scripts/test-free-desktop.cjs` passed for chord capture inside Automatic mode.
- Live AI runs were not part of this release's validation; hybrid and edit flows are
  covered with fixture transports. One unintended real Codex request was made by an
  early test draft and the test suite now refuses any unpatched AI transport.
- The portable EXE passed startup, bundled media conversion, capture, duplication,
  print defaults and shutdown cleanup (`scripts/test-portable.cjs`).
- Artifact: `dist/Video-Sheet-to-PDF-AI-0.17.0-win-x64.exe` (221,213,910 bytes). SHA-256:
  `97e66cb921bd1bf94f726d93e8d4e01238c56c8313f1b0c2dab35bcc5553b897`.
