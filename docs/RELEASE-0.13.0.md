# Video Sheet to PDF 0.13.0

Includes the Duplicate button, tighter bass crop, and numbered-bar recovery from 0.12.0.

## BPM and identical repeats

In Automatic mode, choose Bass or Guitar TAB and open Extraction settings:

1. Click **Detect BPM from audio**, or enter **BPM (quarter notes)** manually.
2. Set **Quarter-note beats per bar**. Use 4 for 4/4, 3 for 3/4 or 6/8. For compound meter, convert a dotted-quarter tempo to quarter-note BPM before entering it.
3. Enable **Recover identical repeats using timing**, then extract again.

Audio analysis estimates the pulse from three sections of the video using spectral
onsets and autocorrelation. Estimates can be half or double the intended tempo;
the interface shows these alternatives and flags disagreement between sections.
Loading another video clears the tempo and recovery checkbox.

Timing recovery requires a single stationary TAB line, visible complete barlines,
a duration close to 2–4 full passes, and at least three nearby single-pass lines
whose durations agree with the BPM and meter. It ignores first/last lines, gaps,
combined staff/TAB panels, and uncertain bar counts. Added copies are independently
editable and have estimated playback timestamps. Every inferred repeat is reported
for review. Pauses, tempo changes, and repeat signs can still invalidate the inference.

The SPYAIR sample estimates **113.0 BPM**. Its line 05 holds from 42 to 59 seconds,
twice the approximately 8.5 seconds expected for four bars of 4/4. With timing recovery
enabled, extraction produces **23 lines**, adding the repeat at **50.5 seconds**.
The initial hold, shorter two-bar lines, and separate lines 02/03 are preserved.
With the option off, the ordinary visual extraction remains unchanged.

## Other videos and the Ado sample

No URL or song identity is hardcoded into extraction. The tighter bass crop applies
to similar standalone TAB overlays. Numbered-bar recovery applies when consecutive
bar numbers and matching bar boundaries are readable; uncertain tracking falls back
to ordinary visual extraction. Numbered recovery takes priority over timing recovery.

Videos without bar numbers use visual line/overlap matching. Timing recovery can help
stationary unnumbered lines, but does not reconstruct arbitrary irregular scrolling.
White scenery that completely hides notation cannot be recovered from that frame.
The Ado sample remains a partial recovery with gaps and background artifacts, as
documented in 0.12.0. Its inconsistent audio estimates are explicitly marked uncertain.

Older projects open normally. Re-extract the source video to apply timing recovery;
opening a saved project alone does not add lines. Original sample projects are unchanged.
