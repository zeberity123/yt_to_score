# Integrated AI workflow (0.17.0)

AI is part of the existing Capture and Review & export interface. Capture offers
**Automatic** (frame capture), **AI** and **Manual**; Chords & lyrics is an instrument
option in every mode. Version 0.17.0 adds the AI **Method** choice (keep video images
with an AI check, or re-engrave), the **AI edit** box, and printed tempo/rehearsal/
multi-measure-rest marks. See [the release notes](RELEASE-0.17.0.md).

Version 0.16.2 adds local score-image preparation, compact AI responses, grouped
review and up to two concurrent numbered batches. See the
[measurements and changes](RELEASE-0.16.2.md). The bottom-right elapsed timer
continues while AI is working and remains after completion or cancellation.
Version 0.16.3 adds optional AI area selection, phase/batch progress and cancelled
draft recovery. See [the release notes](RELEASE-0.16.3.md).
Version 0.16.4 adds Pause/Resume, saved review checkpoints, smaller targeted
reviews and grace-note rendering. See [the release notes](RELEASE-0.16.4.md).

1. Load a YouTube link or local video and select Drums, Bass TAB, Guitar TAB,
   Piano, or Chords & lyrics.
2. Select **AI**, then a connection and model.
3. Choose a **Method**. **Keep video images + AI check** keeps the video's own
   score images and uses the AI only to find the score, check bar order, hide
   duplicates and flag broken rows (minutes, few requests). **Re-engrave notation
   with AI** reads every bar and draws new notation (many requests, editable).
4. For re-engraving, leave **Override bars per line: OFF** to preserve visible
   source row breaks, or enable it and enter a count, and add any reading
   instructions. For image capture, **Extraction settings** apply instead.
5. Optionally enable **Select score area** and drag a rectangle, then select
   **Extract with AI**.
6. Review the rows. Duplicate, exclude, undo, reorder and, for image capture,
   **Re-transcribe with AI** on a single flagged line are available.
7. Edit title, first-page-only title, subtitle, song information, footer, page
   numbers, bars per line and rest merging, or describe a change in **AI edit**.
   Preview and export the PDF, or save a portable `.drumscore` project. Existing
   `.aiscore.json` projects can also be opened.

AI reconstructs notation from video frames and produces vector PDF notation;
it is not audio-to-MIDI transcription. Selecting the instrument helps interpretation.
Unclear readings, missing bars, and unsupported instructions appear as review
notes. These checks cannot detect every plausible but wrong note.
If source row breaks cannot be read, the detected typical count (or four) is
used with a review warning. Image crop editing applies to Manual/classic projects;
AI rows are edited through their musical layout, rather than cropping preview images.

Page text and row edits use saved data and make no further AI requests. Remove
subtitle/footer text to omit it, or disable song information. Song information
supports three explicit lines and the footer four. AI engraving determines row
spacing; the image-capture line-gap control is hidden for AI projects.

## Printed marks and rests (0.17.0)

Transcriptions record a bar's printed tempo, boxed section label and multi-measure
rest block as data. The score prints one metronome mark (♩ = N) where the tempo
changes, boxed rehearsal letters, measure numbers at line starts only, and no
instrument label. Rest blocks print as the video shows them. With the bars-per-line
override on, **Merge consecutive rest bars** (default on) also merges runs of
whole-bar rests into one counted block. Older projects that stored "A tempo ♩=110"
as text are converted when opened. The video title is the default score title.

## AI edit (0.17.0)

**AI edit** in Review & export sends one short text request through the connection
chosen in Capture: page layout, tempo and rehearsal marks, removing printed words,
rest merging and line breaks. Unsupported requests are listed under the box, never
silently applied. A request about wrong notes in specific bars re-reads those bars
from cached video frames (a few image requests) with the same targeted review used
during extraction; this needs the original job folder and video on this machine.
For image-capture projects the box can exclude, move or engrave lines.

## Keep video images + AI check (0.17.0)

The default AI method sends one overview request, captures rows with the frame
extractor using the AI's score rectangle (or your selection), then checks batches of
row images: printed bar ranges, duplicates, clipped or obscured rows and ordering
confidence. Duplicate rows are hidden and can be restored with Undo. Rows are
reordered only when every kept row has a confident, non-overlapping printed range;
otherwise a note asks you to verify the order. Flagged rows show ⚑ and their notes
under the preview. **Re-transcribe with AI** engraves one row from its captured
image; **Edit crop → Restore original** returns to the capture. Cancelling during
the check keeps the captured rows with a note.

## Connections

- **Codex:** install the official Codex CLI and run `codex login` with ChatGPT.
  Extraction consumes subscription allowance; this connection does not fall back
  to an API key. Astra/high is the quality default.
- **Claude CLI:** install a current Claude Code native CLI and run
  `claude auth login` with a Claude subscription. Uses structured, image-bearing
  CLI requests with tools disabled. Tested command format with CLI 2.1.278;
  account limits and the account's extra-usage settings apply.
- **OpenAI / DeepSeek / Anthropic:** enter a provider API key. API billing is
  separate from subscriptions. Keys stay in memory and are not put in projects.
  The integrated app has no per-job request or spending limit. Provider billing
  is authoritative. Completed responses are cached for reuse; Cancel stops the job.

Codex and Claude Code must be installed separately on a new PC. Neither CLI nor
the user's credentials is bundled in the EXE. API modes need no separate CLI.
Frames and instructions are sent to the selected AI service.

## Luna versus Astra: local sample

On September 28, 2026, Luna/high was given the same six full frames from the
186–198 second Ado excerpt used in the earlier Astra workflow. Luna returned
eight complete bars (113–120), omitted bar 112, and matched the reference exactly
in string, fret, onset, and duration for only bars 113, 116 and 117. The other
five returned bars contained string-placement or rhythm errors. The earlier
Astra workflow matched all nine complete bars (112–120).

This is a small practical comparison, not an identical-prompt controlled model
benchmark: the integrated prompt/schema adds source-row information. It does
not establish an error rate for other videos or instruments. Luna is a cheaper
option but did not reproduce Astra's quality here. Use Astra for the demonstrated
quality level and review every result.

Luna request usage: 30,060 input tokens, 5,571 output tokens, no cached tokens;
it used the signed-in subscription, not a paid API request. Evidence is in
`output/ai-connections/Codex/`. The live Claude request reached the installed
CLI but failed on expired OAuth credentials; no API fallback was attempted.
Run `claude auth login` before trying that connection. Paid provider transports
are tested with fixtures; no live API requests were made for this integration.

## Area selection, progress and cancellation (0.16.3)

Enable **Select score area** to drag a fixed rectangle in AI mode. All AI evidence
(including overview and uncertain-bar review) uses that rectangle. Include bar
numbers, annotations and every staff; leave it off when the score moves outside
a fixed area. Switching to Manual preserves playback position.

The bottom status shows the current phase, completed/total transcription or review
batches, and saved bars/rows. The progress bar describes that phase, not a whole-job
ETA. Time since the last phase update remains visible during long provider waits.

Cancel retains completed batches as an **INCOMPLETE DRAFT** in Review & export,
with unresolved readings and missing bars listed in Extraction notes. If no batch
finished, the status says so and the app stays in Capture. Retry with the same
video, provider/model, crop and reading instructions to reuse compatible responses.
Changing those inputs can require new requests. Drafts have not completed review
or necessarily applied additional instructions. Save project to keep a portable copy.

## Pause and faster review (0.16.4)

Click **Pause** beside Cancel to stop launching new AI requests. Requests already
running finish first; the status changes from **Pausing** to **Paused** when none
remain. Click **Resume** to continue the same job, and keep the application open
while paused. Fully paused time is excluded from the elapsed timer. Cancel works
while paused and retains completed work for a later retry.

Numbered-bar review requests only uncertain musical readings, confirms unchanged
bars with short responses, and runs up to two independent groups concurrently.
Engraving limitations remain in review notes. Stable checkpoints preserve completed
review decisions across retries with unchanged inputs. Older compatible response
caches are also reused. Exact repeated bars may use a compact response format;
local expansion keeps all their separate occurrences in the score.

These changes reduce unnecessary work, but completion time still depends on the
video and provider. The progress bar remains specific to the current phase.
