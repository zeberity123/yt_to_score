# AI Score 0.1 — Personal and API editions

These are separate apps; the existing Video Sheet to PDF app is unchanged. Both editions support visual bass/guitar TAB, drum notation and two-staff piano. They read printed notation in video frames, not music from audio. This is a first release: inspect the review report and compare difficult passages against the video.

## Start

Run `AI-Score-Personal-0.1.0.exe` or `AI-Score-API-0.1.0.exe`. Paste a YouTube URL or choose a local video, select the instrument, set 1–8 bars per line, and add optional instructions. Select **Transcribe / resume**. Open the PDF when complete. Output is under `%LOCALAPPDATA%/AI Score/<edition>/jobs` by default. You may choose another folder.

Personal requires the official Codex CLI installed separately and signed in using `codex login` with ChatGPT. **Check login** verifies this. It uses your subscription's Codex allowance, subject to your plan's limits; it is not unlimited or an API-billing workaround. API-key authentication is rejected by the personal edition. CLI auth is never copied or bundled. The CLI runs ephemeral, read-only requests with isolated prompts and schema-constrained output. The app does not run AI-generated scripts.

API edition supports OpenAI, DeepSeek and Anthropic. Enter a key belonging to that provider; it stays in process memory and is not saved in settings, projects, caches or logs. It is sent only to the selected provider's fixed HTTPS endpoint. Frames and prompts leave the PC for processing in both editions. Each provider's data policies and your account settings apply.

## Quality workflow

1. Inspect representative full frames for instrument, numbering and score location.
2. Read overlapping groups of high-resolution frames. Use printed bar numbers and time context to preserve distinct repeated bars.
3. Validate measure coverage, rhythm totals, staff/voice coverage and TAB fret/string ranges.
4. Re-read missing, conflicting or uncertain bars using denser full-frame samples.
5. Produce deterministic vector notation and a separate review report. Unresolved readings are not silently called correct.

Full-frame mode is recommended for scores that move or change size. Turning it off uses a padded score rectangle proposed by the model. Two-second samples are the default; use one second for fast transitions or dense music. Smaller frames-per-request values reduce output truncation at the cost of more requests. Unnumbered music remains harder: occurrence order and repeated measures always need review. A model can also make confident mistakes that rhythm validation will not detect.

The renderer produces 4–7-string TAB with chords, rhythmic stems/beams, ties, slides, hammer-ons, slap/pop and vibrato. Piano/drums use MusicXML and Verovio, including chords, independent voices, ties, triplets and percussion noteheads. Unsupported notation (for example complex repeat endings, arbitrary grace-note groups or independent polyphonic TAB voices) requires review rather than silently promising a complete transcription. PDF layout can fail when a dense bar cannot fit; lower bars per line and reformat the saved project.

## Formatting without re-transcription

Use **Reformat saved score** and select `score.aiscore.json`. Existing musical data is reused; only a small text request interprets new instructions. With blank instructions, bars-per-line changes need no AI request.

Defaults are a first-page-only title, no subtitle, no metadata line and no footer. Example:

> Set the title to Ado | Bass TAB on the first page only. Remove all subtitles, source text and footers. Merge whole-rest bars 116 and 117 into one two-measure rest. Keep four printed slots per line.

This preserves all musical measures. The row contains 113, 114, 115 and 116–117 (rest count 2); the next contains 118–121. Only consecutive, validated full-measure rests with the same meter can be combined. It never deletes a measure of time. Source numbering is preserved. Explicit line breaks are supported. Unsupported text requests are shown in the report. Natural-language note corrections are not yet an automatic editor; the editable JSON project retains the complete structured transcription.

The `independent_score/ai_example` example comes from the earlier manually reviewed transcription, not a benchmark proving that the new extraction pipeline reproduces it automatically.

## Cost, caching and limits

The UI reports current-run input, cached input, output tokens, elapsed time, requests and estimated API USD. Reasoning tokens are included in output totals when the provider reports them. Existing completed responses are reused without another AI call, including when resuming after a cancellation or limit. Cache identity includes images, prompt, schema and model. Changing transcription settings may create a separate job. Project files and frames contain source material; delete the chosen output folder when no longer needed.

The spend guard reserves a conservative estimate before each request. It is **not a provider-enforced billing cap**: image token accounting, rate changes, failures and in-flight requests can differ. Configure provider-side budgets too if you require a strict account limit. No automatic paid retry is made after a timeout, because the provider may already have processed it. Cancellation waits for the active HTTP request to finish or time out; it cannot refund it. Limits apply per run, not to the lifetime of a resumed project. `usage-latest.json`, response-cache usage and project usage support inspection.

Standard short-context rates checked 2026-09-28, USD per million tokens:

| Model | Input | Cached input | Output |
|---|---:|---:|---:|
| GPT-6 Luna | 0.10 | 0.01 | 0.50 |
| DeepSeek V4.1 Flash (`deepseek-flash`) | 0.30 | 0.006 | 1.20 |
| Claude Haiku 4.5 | 1.00 | 0.10 | 5.00 |
| GPT-6 Sol | 2.00 | 0.20 | 10.00 |
| GPT-6 Astra | 10.00 | 1.00 | 50.00 |

Luna is the lowest listed standard price among the requested models and the API default. DeepSeek off-peak prices are lower than its peak table; this app conservatively estimates peak pricing. OpenAI long-context/premium service pricing can differ. Cached-image/token treatment depends on provider. These prices do not establish transcription quality: compare the same difficult bars before relying on a cheaper model. Personal defaults to Astra high for the quality-oriented workflow. Live paid API quality was not benchmarked without user-configured keys.

Official references: [Codex authentication](https://learn.chatgpt.com/docs/auth), [non-interactive Codex](https://learn.chatgpt.com/docs/non-interactive-mode), [OpenAI pricing](https://developers.openai.com/api/docs/pricing), [Luna](https://developers.openai.com/api/docs/models/gpt-6-luna), [DeepSeek pricing](https://api-docs.deepseek.com/quick_start/pricing/), [Claude pricing](https://platform.claude.com/docs/en/about-claude/pricing).

## Development

Install `requirements-ai.txt` in the existing virtual environment. Run `.venv/Scripts/python.exe desktop/ai_personal.py` with the repository on PYTHONPATH, or the API entry point. Run `.venv/Scripts/python.exe -m pytest tests/test_ai_score.py`. Build both portable Windows executables with `powershell -ExecutionPolicy Bypass -File scripts/build-ai.ps1`. Bundled components include Python/Tk, OpenCV, FFmpeg, yt-dlp, Node, ReportLab, Verovio and SVG libraries; license notices accompany the bundle. Codex CLI and account credentials are not redistributed.

For an offline packaged-runtime check, run either executable with `--self-test <output-folder>`; it renders all four instruments and checks the bundled FFmpeg. `--smoke-test` opens and automatically closes the UI. Neither option sends an AI request. The live integration scripts in `scripts/test-ai-live.py` and `scripts/test-ai-e2e.py` use the signed-in subscription and must be run explicitly.
