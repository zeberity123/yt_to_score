# 0.17.1 - Page-fit PDF options and a larger crop editor

Image-capture projects (Automatic, AI-checked capture and Manual) gain a second row of
PDF settings under Paper: **Top** and **Bottom** margins (0–40 mm), **Title size**
(6–36 pt), **Print title** and **Page numbers**. The defaults reproduce the previous
output (12 mm, 12 pt, both on). With page numbers on, at least 6 mm stays free under the
last line so the number never touches it. AI-engraved scores keep their own page
settings; these fields are hidden for them.

Example: a 21-line drum capture that needed three A4 pages at the default margins
(the third page held one line) fits two pages at 5 mm top and bottom; changing only the
title size or the page-number toggle was not enough for that project.

The **Edit crop** dialog now fills the window height. The source frame takes all spare
space, the edited-line preview has a fixed height so the frame no longer shifts under
the cursor while a crop is dragged taller or shorter, and Left/Top/Right/Bottom, Line
height and **Apply height to all lines** sit in one row. The explanatory texts were
removed.

## Validation

- Full Python suite: 260 passed, including new page-fit coverage (`test_pdf_page_fit_options`)
  and the export payload mapping (`test_export_passes_page_fit_settings_to_the_image_exporter`).
- Source Electron checks passed: `scripts/test-desktop.cjs` (now also asserts the crop editor
  keeps its size when the crop changes), `scripts/test-print-layout.cjs`,
  `scripts/test-duplicate.cjs` and `scripts/test-ai-integrated.cjs`. They caught one
  regression before release: a `display:flex` rule on the editor dialog kept the closed
  dialog on screen and blocked every click; it is now scoped to the open dialog.
- The portable EXE passed startup, bundled media conversion, capture, duplication,
  print defaults and shutdown cleanup (`scripts/test-portable.cjs`).
- Artifact: `dist/Video-Sheet-to-PDF-AI-0.17.1-win-x64.exe` (221,217,893 bytes). SHA-256:
  `1298ee9b77b8b6d1df0677f92396862d8a61167ecb30d2ea23f0632d95959231`.
