# 0.17.2 - Preview PDF for captured images

Image-capture projects (Automatic, AI-checked capture and Manual) have a **Preview PDF**
button next to **Preview print lines**. It renders the exact pages **Export PDF** would
write with the current paper, line gap, left/right and top/bottom margins, title size,
title and page-number toggles and the title typed in the box, and shows them two-up so
page breaks and gaps are visible at a glance. Change a setting, preview again, and
export when it fits.

A preview does not save the title and does not create a download. AI-engraved scores
keep the Preview PDF button in their own page settings.

## Validation

- Full Python suite: 261 passed, including the new preview coverage
  (`test_preview_pdf_renders_the_pages_for_the_current_settings`).
- Source Electron checks passed: `scripts/test-print-layout.cjs` (now opens Preview PDF
  and checks the page grid) and `scripts/test-desktop.cjs`.
- The portable EXE passed startup, bundled media conversion, capture, duplication,
  print defaults and shutdown cleanup (`scripts/test-portable.cjs`).
- Artifact: `dist/Video-Sheet-to-PDF-AI-0.17.2-win-x64.exe` (221,219,208 bytes). SHA-256:
  `978b0751b54b0c865efd894ee5461b07a3d67682b81a703da34ed24278b181fd`.
