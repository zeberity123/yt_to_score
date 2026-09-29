# AI Score 0.1 validation — 2026-09-28

## Source and contract checks

- 20 AI tests pass: all four instrument PDFs, chords and piano staff coverage, rhythmic validation, missing bars, schema rejection, paid-request guards, response caching, image payloads and response/usage parsing for all three API providers, short-video extraction, multi-measure-rest preservation, and dotted/tuplet rhythmic flags.
- The existing suite also passed (203 tests at that point: 190 existing tests plus the first 13 AI tests). Subsequent changes were confined to the new AI app and were checked with its expanded suite.
- The clean Ado example retains all 143 musical measures, combines 116–117 into one printed rest slot, places 118–121 on the following row, and has six vector PDF pages. It is derived from the earlier reviewed transcription; it is not presented as an automatic whole-song benchmark.

## Live Codex checks

- The installed Codex CLI authenticated using ChatGPT. A real vision request read the two rests at 116 and 117.
- The complete pipeline ran against a 12-second excerpt of the original Ado video (186–198 seconds), without receiving the reference transcription. It automatically read complete bars 112–120, validated/reviewed them, interpreted the formatting request, combined 116–117, and generated a vector PDF.
- All nine complete bars matched the reference transcription's string/fret choices, onsets and durations. This includes the distinct rhythms in bars 112, 114 and 118. Bar 121 is clipped in that excerpt and was omitted with a missing-bar report, rather than filled with invented notes.
- The completed resumed run took 221.7 seconds, with five new requests and two reused responses: 134,687 input tokens and 6,238 output tokens. This is **not** total first-run usage: the reused responses and earlier integration-debugging requests consumed additional subscription allowance.
- Remaining review notes include the absent time signature in the excerpt and slides with no printed destination. These are retained for inspection outside the PDF.

## Limits of these checks

This is not a full-song quality benchmark for the new pipeline. The full 143-bar polished example predates it. Automated piano and drum engraving has been exercised with structured fixtures; their live video transcription quality has not been benchmarked. Paid API transports were tested with controlled responses, not real account keys. No claim is made that Luna, DeepSeek Flash or Haiku match Astra's transcription accuracy.

Packaged-runtime smoke results and executable hashes are written under `output/ai-packaged-check` after the release build. The checks create bass, guitar, piano and drum PDFs with the bundled renderer, run bundled FFmpeg, and launch/close each edition's UI without making AI requests.
