Download `Video-Sheet-to-PDF-0.3.1-win-x64.exe` and double-click it. Python,
FFmpeg, and the YouTube JavaScript runtime are bundled. Existing projects remain compatible.

- Space plays/pauses in Capture and Review & export, including with buttons or thumbnails focused. Text fields still accept spaces.
- Selected score lines use one focus outline when navigating with arrow keys.
- Exclude line removes the line from the list and export. Undo restores removed lines with their edits and position.
- Review audio defaults on for new videos and Manual mode. Automatic extraction pauses playback and switches review audio off.
- YouTube HTTP 403 recovery requests fresh media URLs and tries alternate clients, preserving notation resolution and audio.
- Completed/cancelled downloads and desktop shutdown clean up export staging files. Failed project writes clean up their `.tmp` files.

Validated the reported YouTube URL after exporting a score in the same session,
including recovery from a reproduced HTTP 403. Automated checks cover removal/undo,
legacy exclusions, temporary-file cleanup, audio, keyboard navigation, extraction,
project save/reopen, and PDF export.

Normal PDF defaults remain a 0 mm gap and 3 mm side margins; **For print** uses a
0 mm gap and 12 mm side margins. The Windows x64 executable is unsigned.
