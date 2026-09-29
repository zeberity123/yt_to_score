# 0.16.3 — AI progress, selected area and cancelled drafts

AI mode now offers **Select score area**. When enabled, dragging in the video
defines a fixed crop used for overview, transcription and uncertain-bar review,
including chords/lyrics. Automatic area detection remains the default. Include
bar numbers, all staves and annotations; a fixed crop can cut off a moving score.
Loading an AI video now explains these controls. Switching to Manual preserves
the current video timestamp.

Extraction has a separate progress channel: the current phase, completed/total
batches, saved bars/rows and time since the last update. Provider authentication
and response-cache messages no longer replace the current extraction stage.
The progress bar reports progress within the named phase, not an overall ETA.
The elapsed timer remains at bottom right and freezes on completion or cancellation.

Cancel immediately shows that cancellation is pending. Successfully completed
in-flight batches are retained. Completed observations become an **INCOMPLETE
DRAFT** in Review & export, with a visible draft subtitle and warnings for missing
or conflicting readings. If no score batch completed, the status says so and the
app does not switch to an empty review. A previous project's rows are not presented
as a new extraction result. If partial engraving fails, the status identifies the
saved structured draft. Additional instructions may not have been applied.

Retrying unchanged inputs reuses compatible response caches. Changing the crop,
source, model/provider or reading instructions can require new requests. No extra
AI requests are made to recover or render cancelled drafts.

## Actual cancelled drum run

For `https://youtu.be/gOcU3kUdNp8` (255.97 seconds), the existing diagnostics showed:

- 129 sampled frames, planned as 19 transcription batches.
- Eight completed Astra batches, candidate readings for bars 1–62, and 38 bars
  with differing observations before targeted review.
- 196,158 input and 60,628 output tokens in completed responses. The final request
  counter also included two in-flight attempts beyond the UI's eight completed
  requests. These counts are not a monetary charge for the subscription connection.

Thus the reported 25-minute run was still doing transcription, with review work
remaining. Long visual transcription responses and dense polyphonic drum rhythms
can make this workflow slow. This release does not claim a measured whole-song
latency improvement or a guaranteed finish time.

A local-only crop experiment retained all 129 samples and restricted them to
the bottom 26% of the frame. Prepared pixels decreased from 103,441,920 with
automatic cropping to 69,598,080 (32.7% fewer). Preparation took 18.23 seconds.
This is an image-workload measurement, not a token or inference-speed benchmark.
Evidence: `output/current-debug/crop-measurement.json`.

The existing checkpoint was recovered locally into 11 review rows, with 68
warnings, a portable project and a PDF under
`output/current-debug/recovered-draft/`. These are unreviewed partial readings,
not a verified transcription. A separate replay used the original cached responses
and blocked all fresh inference calls, then exercised cancellation and draft creation
through Workspace. It recovered the same 62 bars with no provider inference.

## Validation

The full suite passed 234 tests. After adding cancellation draining for successful
in-flight batches, all 45 targeted AI tests passed. Coverage includes crop boundaries,
invalid crop rejection, progress preservation, cancellation before/after completed
batches, stale-checkpoint protection, parallel cancellation, and draft warnings.
Electron source checks passed for actual crop dragging, retained playback time,
extraction dispatch, progress presentation, page editing/export and responsive UI.
Packaged checks and artifact details are recorded after the build below.

Packaged Electron checks passed for crop dragging, timeline preservation, progress
display, review controls, PDF/project export and responsive layouts. A real packaged
extraction using the existing short Ado fixture completed with three cached responses,
zero new requests and three review rows; it showed extraction progress rather than
the video-load message and retained the elapsed timer. Its 5.69-second cache-only
runtime is not a model inference benchmark.

The final portable EXE passed startup, bundled video/audio conversion, manual
capture, duplication, print settings and shutdown cleanup with development tools
removed from PATH. Artifact: `dist/Video-Sheet-to-PDF-AI-0.16.3-win-x64.exe`
(221,190,742 bytes). SHA-256:
`9ae5390fbc58b25532ccde8a7285446921d5dd0fcc0d24e04f425d3ac60466e3`.
