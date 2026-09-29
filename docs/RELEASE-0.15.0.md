# Video Sheet to PDF 0.15.0

- Corrects bass staff grouping when one of the five ordinary staff rules is faint. The same staff can no longer become a competing four-string TAB group, which caused missing lines and separated rest-count annotations.
- Adds **Follow changing score position** under Extraction settings. It follows one complete system near the selected area at the existing sample interval, including paired bass/piano staffs, and trims spare margins using staff positions. It is off by default. Full pages keep their fixed area; numbered TAB uses its existing bar tracker. Select an initial area around one system. Large jumps, partial systems, and continuous scrolling still need review.
- Makes audio BPM detection, manual BPM, and optional timing recovery available for drums and piano as well as guitar and bass. Recovery requires countable complete measures; both component staffs must agree for a paired system. Empty partial trailing measures are rejected. Neighboring line durations must support the tempo. Pauses, tempo changes, and written repeats remain ambiguous.
- Shows **Checking identical repeats using timing** after normal scanning when that option is enabled. The extraction notes report how many inferred lines were added. **Recovering numbered TAB bars** is a separate visual recovery method and does not require BPM.

For `f5VnaleBDJM`, the saved BPM-enabled retries reported zero inferred repeats. The staff grouping/crop issue was independent of tempo. The new grouping keeps the lines around 183 and 189.5 seconds and attaches the “2” to its multimeasure rest. Flexible area adjustment follows the lowered final system.

Existing saved projects are unchanged. Re-extract to apply these changes, or open the supplied `screen_sample/f5VnaleBDJM_updated.drumscore` example.
