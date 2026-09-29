# Video Sheet to PDF AI 0.16.1

- Fixed Extract with AI silently doing nothing. The removed API budget field had
  `min=0.1`, `step=0.5`, and `value=2`, which is an invalid HTML step value. The
  Extract handler checked that hidden field in subscription mode and returned
  before submitting a request. Authentication was not the cause.
- Removed Usage limits and the integrated app's per-job request/spend caps.
  Usage accounting and cancellation remain available.
- Additional instructions is empty with no example placeholder.
- Capture and Review use an accessible toggle button next to a compact bar-count
  input. Off still follows source row breaks.
- Play/pause uses drawn icons instead of font characters. Playback no longer has
  a step number.
- Fixed the extra page scrollbar by positioning the scrolling sidebar, keeping
  its hidden accessibility labels inside its scroll container. Before the fix,
  a 779-pixel viewport had an 882-pixel document; afterward both were 779 pixels.
- Added AI to the visible app name and EXE filename. The existing app data folder
  is retained, so cached videos and projects remain in the same location.

Regression checks click Extract with blank instructions/default controls for all
five connections and intercept the request before it reaches an AI service.
They also exercise the bar toggle, pause icon, desktop scroll height, review,
preview/export, portable projects, and piano/drum/chord previews. These UI tests
do not consume provider quota. Provider/backend tests and playback regressions
are also run before packaging.

Validation: 27 AI/provider/backend tests passed, as did the playback regression
and the integrated UI checks against both source and packaged builds. The packaged
check used the real signed-in Codex login check, then verified Extract dispatch
with empty instructions while intercepting before the AI service call.

The final portable EXE launch check passed with development tools removed from
PATH, including bundled conversion, manual capture, duplicate and shutdown cleanup.
Artifact: `dist/Video-Sheet-to-PDF-AI-0.16.1-win-x64.exe` (221,192,766 bytes).
SHA-256: `3892ab817c1f13d4b3677da57414aaf5de71b7dc530264f30ce95e0fd1166804`.
