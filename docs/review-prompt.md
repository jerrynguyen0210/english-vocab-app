# Review prompt

The Review screen follows screens 6–9 of `Wordwell_Unified_Figma_Import.svg`.
It loads a fixed due-word snapshot from `GET /api/v1/reviews/session`. Each item
includes a server-generated attempt ID for safe retries.
The prompt contains `word_id`, `english_explanation`, and nullable
`example_sentence` (D1). Missing examples do not render an empty section.

Before serialization, the server replaces every occurrence of the target with
`_____` in both hint fields. Matching handles Unicode compatibility, case folding,
and variable whitespace in phrases. Substring matches are deliberately masked,
including targets inside compounds, to avoid exposing the answer. Hints without
the target remain readable; the stored word and hints are not modified.

The answer and normalized answer are never included in the prompt response.
The prompt stays masked after submission. Separate answer feedback can reveal the
correct word, as in screens 7–8. The next prompt clears that feedback and input.

Submission uses D2 (case and outer whitespace ignored; otherwise exact spelling)
and records the original answer and elapsed time on the server. Empty answers
are allowed as failed recall. Incorrect feedback places the entered answer next
to the correct word; narrow layouts wrap these columns. A persistent polite live
region announces feedback on web/Android, and VoiceOver uses an explicit iOS
announcement. Finished sessions announce and display the correct-answer count.

The snapshot and every submission respect D5's 20-attempt daily cap across sessions/devices.
The client increments totals only after a successful server response and blocks
concurrent submissions. An already-reviewed item can be skipped; a cap conflict ends the session
without counting an unconfirmed attempt. New words wait for the next session.
Network retries resend the same attempt ID, answer and duration; the server
returns the saved result without recording or scheduling twice. The client uses
a monotonic elapsed timer; due times and day boundaries come only from the server.

Verification: backend rule tests were written before this UI revision and run
against extracted scheduling/normalization functions. API tests cover replay after
a lost response and owner isolation. Screen-handler tests cover retained drafts,
identical retry payloads, sign-in interruption, empty sessions and snapshot
completion. These tests do not emulate native layout or screen-reader speech.
