# Video Sheet to PDF 0.14.0

## Four-bar layout

Fixed numbered recovery losing its confirmed bar boundaries during PDF layout.
The previous formatter detected barlines again in the cleaned image. A broken
barline could merge two musical bars, allowing five bars into a row counted as four.
New numbered captures store their verified boundaries, bar numbers, and staff
alignment. Review/PDF layout uses those boundaries in White, Black, and Original
modes. Metadata survives saving, reopening, and duplication. A crop that changes
the original rectangle falls back to visual barline detection.

Also fixed an intermittent print-preview race: an older status response can no
longer cancel the UI's wait for a newly requested preview.

## Clearer numbered TAB

Recovery chooses darker source patches within each aligned bar, rather than
choosing entire vertical strips. Repeated observations filter transient background
fragments; bright occlusions cannot vote to erase a note. Antialiased notation
keeps a generous color tolerance to preserve strokes over colored footage.
A denser second pass revisits possible gaps.

These changes reduce artifacts but do not transcribe or redraw musical symbols.
Persistent highlights and notation hidden in every usable view can remain unclear.
Missing bars and uncertain endings still require review/manual capture.

## Off — original capture

Automatic extraction now stores source-color images alongside cleaned notation.
Off shows those colors in review and PDF output. Numbered recovery shows the same
source patches used to assemble its bars, so this can be a mosaic of video frames.
Cropping, Duplicate, and project archives preserve access to these source colors.
Manual and Chord captures already retained their original colors.

Older automatic projects often contain only cleaned pixels. A notice now explains
why Off cannot restore their video background. Re-extract the video with this
version to obtain source colors and verified numbered-bar layout metadata.
New automatic project archives may be larger because they retain color sources.

All BPM and Duplicate features from 0.13.0 are included.
