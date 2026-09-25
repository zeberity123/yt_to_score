# Video Sheet to PDF 0.5.0

- Renamed **Standard / drums** to **Drums** in English, Korean, and Japanese.
- Added **Bass** for four-string TAB and paired standard notation plus TAB.
- Added **Piano**, keeping both hands together with dynamics and pedal markings.
- Detects bass and piano score panels at either edge of a video and groups complete systems on pages.
- Filters moving playback cursors and retains source frames for crop editing.
- Saved projects restore their notation mode when reopened.

Choose the instrument under **Notation** before loading the video. Check the crop,
extract, and review the lines before printing. Tested capture windows from all five
supplied bass videos and all three piano videos. Extraction is image-based;
reflowed/overlapping partial measures and continuous scrolling may need manual edits.
Bass TAB with five/six string rules and piano systems with more than two staves
currently need Manual mode.

Download the portable Windows x64 EXE and double-click it. Python, FFmpeg, and Node.js
are included. Existing `.drumscore` projects remain supported. This release is unsigned.

Validation: 77 Python tests passed. Packaged desktop checks passed for all eight
bass/piano reference videos, both guitar examples, the existing drum workflow,
English/Korean/Japanese, crop editing, project/PDF saving, audio playback, keyboard
controls, and responsive layouts. Reference-video checks use capture windows,
not note-for-note verification of entire songs.
