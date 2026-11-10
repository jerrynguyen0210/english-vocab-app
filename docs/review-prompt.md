# Review prompt

The Review screen follows the review states in
`Wordwell_Complete_With_Review_Preparation_Figma.svg`. It loads a fixed snapshot
from `GET /api/v1/reviews/session` using the source selected in preparation.

Each item includes a server-generated attempt ID, signed review token, a required
`prompt_sentence` and masked explanation/example fields. Typing is the default:
`GET /reviews/session?answer_mode=typing` returns no answer choices, target field
or correct-answer field. Four server-provided options (D16) are returned only
when multiple choice is explicitly requested.
The screen displays the current position and a rounded percentage, for example
**Word 3 of 12, 25% complete**, with a matching progress bar. The percentage uses
current position divided by snapshot size, as in the supplied design; loading and
empty states do not show a progress count.

Multiple choice and Typing share the same fill-in-the-blank sentence. Changing
mode clears the draft answer and preserves the prompt and progress. Choosing
Multiple choice loads only the current prompt’s options through
`POST /reviews/{word_id}/choices`, with its attempt ID and signed token in the
request body. Switching back to Typing discards those options. Small banks
use D16’s server-side dictionary fallback. The client labels the
returned options A–D, preserving their order, and enables Check answer only after
selection. It never invents options. Invalid server option payloads allow Typing
and disable multiple choice. Editing and mode changes are disabled while submitting
or retrying an unconfirmed submission.

## Masked sentences

Before serialization, the server replaces every occurrence of the target with
`_____`. Matching handles Unicode compatibility, case folding, and variable
whitespace in phrases. Substring matches are deliberately masked, including
targets inside compounds, to avoid exposing the answer.

The server uses the saved example when it contains the target. A missing, blank,
or unrelated example uses a definition-based fallback, such as
`“_____” means: A greeting.` The entire fallback is masked too, including its
connective wording. A pre-existing blank in an unrelated example is insufficient.
Stored words and examples remain unchanged.

The screen renders only `prompt_sentence` as the question body. The target is not
shown there in either answer mode, including after submission. Multiple-choice
options necessarily contain the target among distractors; no option is identified
as correct until feedback. No `word` or `correct_word` field is included in the
session response. Separate answer feedback may reveal the correct word. The next
prompt clears that feedback and the draft.

## Typing

The text field shows **Spelling matters · Enter to submit** and Check answer.
Autocorrect, auto-capitalisation, autocomplete and spell checking are off. The
field receives focus when a typing prompt loads, when switching to Typing and
when advancing to the next typing prompt. Enter and Check answer use the same
submission handler, which prevents duplicate or blank submissions. The original
draft is sent unchanged: no client normalization or spelling correction occurs.

D2 checking stays on the server: trim outer whitespace and case-fold for the
comparison, while preserving internal whitespace, punctuation, accents and
compatibility characters. The correct word appears only in submitted-answer
feedback for Typing. Explicit multiple-choice requests necessarily include it
among the four options without identifying which one is correct.

## Submission and verification

Submission uses D2 (case and outer whitespace ignored; otherwise exact spelling)
and records the original answer and elapsed time on the server. Correct feedback
shows **Correct answer!**, a **Correct word** label and the server-returned word.
Incorrect feedback shows **Incorrect answer**, with **Your answer** next to
**Correct word**; the comparison wraps on narrow layouts. Both modes use these
text labels in addition to colour. Each state offers **Next word**, which clears
feedback and the draft before showing the next masked prompt.
A persistent polite live region
announces the outcome and correct word on web/Android (also the user’s answer
when incorrect), and VoiceOver uses an explicit iOS announcement.
Finished sessions announce and display the correct-answer count.

The snapshot and every submission respect the daily cap across sessions/devices.
Only a confirmed answer increments totals. Network retries resend the same attempt
ID, signed token, answer and duration; the server returns the saved result without
recording or scheduling twice. Due times and day boundaries use the server clock.

Backend tests cover Unicode/phrase/repeated-target masking, fallback sentences,
HTTP serialization and unchanged stored examples. Screen-handler tests cover the
masked question in both modes, Word 3 of 12 at 25%, progression, retained drafts,
identical retry payloads, sign-in interruption, empty states and completion.
These tests do not emulate native layout or screen-reader speech.
