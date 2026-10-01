# 0.17.4 - Time taken in every mode, one-line preview buttons

The **Time taken** indicator at the bottom right now works in all three capture modes.

- **Automatic:** runs during extraction and stays afterwards, as in AI mode.
- **Manual:** shows the capture session, from the first **Add line** to the latest one.
- The time is kept per mode, so switching modes shows that mode's own value. Loading a
  new video or opening a project clears it. A Pause button left over from an earlier AI
  job no longer appears during an Automatic extraction.

**Preview print lines** and **Preview PDF** are single-line buttons that stretch across
the settings card instead of wrapping onto two lines.

## Validation

- Full Python suite: 266 passed, including
  `test_time_taken_is_reported_per_mode_for_automatic_and_manual`.
- Source Electron checks passed: `scripts/test-print-layout.cjs` and
  `scripts/test-desktop.cjs`. Button heights were measured in English, Korean and
  Japanese (40–43 px, one line).
- The portable EXE passed startup, bundled media conversion, capture, duplication,
  print defaults and shutdown cleanup (`scripts/test-portable.cjs`).
- Artifact: `dist/Video-Sheet-to-PDF-AI-0.17.4-win-x64.exe` (221,214,935 bytes). SHA-256:
  `8dbda3b3d975b032bd0168cf3e1608c672472fd959535258f861de8a5c71416f`.
