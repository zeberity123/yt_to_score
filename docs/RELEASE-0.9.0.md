# Video Sheet to PDF 0.9.0

- Add **Bars on this line** to the print preview. Keep the overall target at six
  while choosing three or four for dense passages, or any count from 1 to 16.
  Completed exception rows fill the page width so their notes remain readable.
  Select **Default** to remove an exception.
- Exceptions stay attached to their starting bar when earlier rows change.
  They are saved with the project and applied to PDF export. Existing captures
  work immediately; no re-extraction is needed.
- Increase the space between editor labels and number fields so focus outlines
  do not overlap the labels.
- Close the print preview by clicking outside it. Clicking its padding keeps it open.
- Keep the layout explanation visible even when bar arrangement is off.
- Shorten the Korean preview button to **미리보기**, with translated exception
  controls in Korean and Japanese.

On the saved reference video, dense-section exceptions preserve all 211 detected
bars. Short final lines and uncertain captures keep their existing handling.
Height corrections preserve exceptions; changing a source crop requires setting
exceptions again for the changed music.

Validation: 129 Python tests, PDF geometry and content preservation, project
save/reopen, translated desktop/mobile controls, and packaged Windows checks.

Download and double-click the portable Windows x64 EXE. Python, FFmpeg and Node.js
are included; no separate installation is needed.
