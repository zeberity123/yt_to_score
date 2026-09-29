# 0.16.2 — elapsed time and local preparation for AI

The visible title is **Video Sheet to PDF** again. The portable filename retains
AI to distinguish the AI release series. Both bar-count buttons explicitly show
`Override bars per line: ON/OFF`, with the same neutral appearance in either state.

**Time taken** appears at the bottom right during extraction and remains after
completion, cancellation or failure. It includes local preprocessing, provider
waiting, transcription, review, engraving and preparation of the review rows.
Unrelated connection checks, PDF previews and exports do not reset it. The next
extraction starts a fresh timer; the display is elapsed time, not a completion ETA.

## Reducing waiting

The previous version was already a mixed system: AI read video frames, while
local code validated the music and rendered the PDF. This version also uses the
project's existing staff detection and notation cleanup to prepare the evidence:

- Crop vertical background around **all detected staffs**, keeping full width,
  generous annotation margins, and paired piano staffs. Uncertain frames and
  chord/lyric sheets retain the full frame. AI sees original-color pixels, not a
  reconstruction of faint notes by the cleanup algorithm.
- Use eight-frame batches with one shared observation instead of six-frame
  batches with two shared observations; omit redundant final overlap-only batches.
- Deduplicate only exactly matching consecutive cleaned numbered observations,
  retaining hold boundaries and observations at least every six seconds. No global
  image deduplication; unnumbered identical repeats retain every sampled moment.
- Omit irrelevant note properties from AI output, restoring those defaults locally
  before validating and rendering. Rhythm, pitch/string/fret, voices, staves and
  technique marks remain represented.
- Review up to three nearby ambiguous measures together using shared full frames.
- Process at most two independent numbered batches concurrently in the integrated
  app. Unnumbered scores remain sequential with previous-measure context. Printed
  numbering is required for parallel ordering; differing readings still trigger
  review. Completed worker responses are cached and their usage is aggregated.
  Clients with explicit request/spend guards remain sequential.

Reasoning effort was not silently lowered. Provider latency, lengthy notation,
uncertainty and provider/account limits can still make full songs slow. No promise
is made that Luna, DeepSeek or another inexpensive model finishes faster than Astra.

## Measurements and limits

Local planning on the complete 239.5-second Ado video:

| Measurement | Previous | Updated |
| --- | ---: | ---: |
| Sampled/retained moments | 121 | 121 |
| Planned transcription calls | 31 | 18 |
| Total prepared image pixels | 250,905,600 | 112,131,840 |

Local preparation took 45.84 seconds. 118 of 121 frames were cropped. The smaller
instrument-specific representation used 116,302 characters versus 154,391 for the
reviewed 143-bar transcription (~25% smaller serialized data; not measured tokens).
These are workload reductions, not measured whole-song speedup claims. The live
excerpt below used one batch and therefore did not exercise parallel calls.

A fresh Astra/high subscription test of the existing 186–198 second Ado excerpt,
with blank additional instructions, finished in **201.6 seconds**: three requests,
94,131 input tokens, 5,927 output tokens, no cache hits. All nine complete bars
(112–120) matched the reference in string/fret, onset and duration. Clipped bar 121
remained omitted with a review note. This short test does not establish full-song
runtime or quality for other videos/instruments. The older 221.7-second run had
different requests, formatting instructions and cache reuse, so it is not a
controlled before/after comparison.

Evidence: `output/ai-speed-benchmark/summary.json`,
`output/ai-optimized-live/summary.json` and the corresponding vector PDF.

## Another PC/account

The EXE is not tied to this PC or account. On another Windows PC, install the
official Codex CLI, run `codex login`, sign in with that person's account with
Codex access, and select Codex in the app. Its available models and allowance
depend on that account. Credentials are not bundled with the EXE.
[Official authentication instructions](https://learn.chatgpt.com/docs/auth).

Claude CLI likewise requires its own native CLI installation and subscription
login on that PC; API connections instead use that provider's API key and billing.

## Validation

The full suite passed 226 tests after local preprocessing/timer changes. The
expanded AI tests subsequently cover the two-worker limit, independent response
caches and aggregated usage, as well as crop fallback, paired staves, preservation
of unnumbered repeats, compact-contract round trips and cancellation timing.
UI checks cover unhighlighted ON/OFF buttons, restored title, timer placement,
extraction dispatch, review and vector PDF output without paid model calls.

All 37 targeted AI tests passed after the parallel-batch addition. Packaged UI
checks passed. A real packaged extraction with the same saved Astra responses
completed in 9.47 seconds, with three cache hits and zero new requests, produced
three review rows, switched to Review automatically and retained its final timer.
CLI discovery was disabled during that test so a cache miss could not silently
spend allowance. This cache-only runtime is not an AI inference speed benchmark.

Final portable-launch checks passed: bundled conversion, manual capture,
duplicate and shutdown cleanup with development tools removed from PATH.
Artifact: `dist/Video-Sheet-to-PDF-AI-0.16.2-win-x64.exe` (221,193,282 bytes).
SHA-256: `a02fe492460792e4661e7a43921b1409703ad439a49ee2547c12567ca303e461`.
