# Integrated AI 0.16.0 validation — September 28, 2026

- Full Python suite: **217 passed**, including source-row preservation, explicit
  bar counts, portable AI project round trips, duplicate/reorder/exclusion,
  vector PDF output, metadata/footer text, chord/lyric alignment, provider
  payloads, spending guards, caching and request usage accounting.
- The AI extraction bridge is tested with a controlled transcription: selected
  instrument, disabled bar override and additional instructions reach the
  pipeline; API keys do not enter workspace state or saved project data.
- Claude CLI transport fixtures verify structured output, disabled tools,
  subscription-only environment, usage accounting and expired-login errors.
- Found and fixed a Verovio resource-path issue across successive worker threads.
  Piano and drum PDFs are now tested from separate worker threads, with Verovio
  initially imported on the main thread.
- `node scripts/test-ai-integrated.cjs` passed both from source and against the
  packaged `dist/win-unpacked/Video Sheet to PDF.exe`. It checks provider/model
  controls, key clearing, default source rows, page settings, PDF preview,
  duplication/exclusion, bar-count changes, completed PDF/project downloads,
  narrow layouts, and successive piano/drum/chord previews. No AI requests are
  made by this UI test. Screenshots: `diagnostics/ai-integrated/`.
- Packaged playback/manual-capture and Duplicate regression scripts passed.
  These cover audio, review playback, keyboard/input guards, saved legacy
  projects, independent crop edits, undo, translations and narrow layouts.
- Final portable EXE smoke test passed with development tools removed from PATH:
  bundled FFmpeg conversion, manual capture, duplicate, print defaults and shutdown
  cleanup. Existing working projects were preserved.

Release: `dist/Video-Sheet-to-PDF-0.16.0-win-x64.exe` (221,187,807 bytes).
SHA-256: `2299ee7d9d0ff833aa061ee22b19631529cb304ef6720caf9cf5139925733118`.
The adjacent `.sha256` file contains the same checksum.

The live Luna excerpt comparison and Claude authentication result are described
in [the integrated AI guide](AI-INTEGRATED.md#luna-versus-astra-local-sample).
Luna did not match the reference quality on this sample. The comparison used
the same source frames but not an identical prompt/pipeline; it is not a general
model benchmark. Claude requires renewed login before its live extraction can
be fully tested. API modes have fixture coverage, not paid live-provider checks.

The integrated app has not yet been quality-benchmarked on complete new drum,
piano, or chord/lyric videos. Rendering support is verified; transcription
accuracy still depends on the selected model and source visibility.
