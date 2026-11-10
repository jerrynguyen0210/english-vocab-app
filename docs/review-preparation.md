# Review preparation

Flow: Home → Review preparation → Review → Review finished.
The client uses live authenticated data. Answer mode (multiple choice or typing)
is selected on the Review screen, after choosing a source and starting.

## Selection and count

`GET /api/v1/reviews/preparation` accepts:

- `source`: `time` or `recall` (default).
- `period`: `Yesterday`, `Weekly` (default), or `Monthly`.
- `include_overdue`: boolean, default true; applies only to recall.

Yesterday uses the user's stored IANA timezone and the previous calendar day;
DST days may have 23 or 25 hours. Weekly and Monthly use rolling 7 and 30 days
ending at the server's current instant. Recall includes all scheduled timestamps
before next local midnight; disabling overdue also requires a timestamp at or
after today's local midnight. Future times within today are eligible.

The response includes `count`, `matching_count`, `saved_count`, `due_count` and
`daily_remaining`. Saved and due totals are scoped to the current user; due
includes today and overdue words regardless of the selected filter. Count is the number ready for this
session, capped at 50 and at the user's remaining daily attempt allowance.
The client disables Start until the current count loads, while empty or after a
failure, and offers retry. Changing filters discards obsolete responses. Counts
refresh when returning to preparation. A session rechecks selection and allowance
at start, so its count may differ if another device changes data in the meantime.

## Deferred topic search

By topic remains visible as an unavailable option in Review preparation. It has
no search input, issues no requests and cannot start a review. Topic search is a
future backend operation; users do not enter topic tags when adding words.
The backend currently accepts only time and recall sources, and exposes no
saved-tag search endpoint or topic fields on word creation.

## Review sessions and answers

`GET /api/v1/reviews/session` accepts the same selection and returns a bounded
snapshot. Each prompt includes a masked fill-in-the-blank `prompt_sentence`,
masked explanation/example, `word_id`, `attempt_id` and `review_token`.
`answer_mode` defaults to `typing`, which returns no choices or correct word.
Explicit `answer_mode=choice` returns four unique options using D16, with the
target included once. The client starts with Typing and loads options for an
existing prompt only when Multiple choice is selected, using authenticated
`POST /reviews/{word_id}/choices` with its attempt ID and signed token in the
body. This preserves the snapshot, progress and attempt when changing mode.
The legacy `/reviews/next` endpoint remains typing-only and masks its hints.

Answers submit the prompt's `attempt_id` and `review_token`, `typed_answer`
(the selected option for choice mode), and `time_taken_ms` to the existing
`POST /reviews/{word_id}/answer`. Tokens expire after 24 hours, bind user, word,
attempt and prior scheduling state, and authorize selected practice even before
the word's due date. Forged, expired or stale tokens are rejected. Exact retries
return the persisted result without another attempt or scheduling change. The
server still enforces ownership and daily allowance under its existing locks.
A client retry retains the exact body and disables editing/mode changes.

Both modes and the supported sources update SM-2 state and attempt history. Binary grades
are 4 for correct and 1 for incorrect, with 10-minute relearning after failure.
D4 documents the full policy, based on the
[original SM-2 algorithm](https://super-memory.org/archive/english/ol/sm2.htm).
Migration `0010` introduced SM-2 state and topic-tag storage. Migration `0011`
removes the topic-tag table; existing SM-2 state, due dates and review history
remain unchanged. Apply migrations through the normal forward-only deployment
process.


## Empty states and Home

Home reads authenticated `GET /reviews/summary` for `saved_count`, `due_count`
and `daily_remaining`, replacing design sample values. It refreshes on focus,
including when returning after adding a word or finishing a review. Preparation
receives the same totals alongside its selection count and also refreshes on
focus. Loading and failed requests never appear as a successful empty result;
failures offer retry.

With no saved words, Home and preparation show **Empty word bank** with
**Add your first word** linking to Add word. With a saved bank and no due words,
they show **Nothing due** and **You're all caught up**, with an **Add word** link.
A daily cap with matching words is **Daily review limit reached**. A selection
with no matches while other words are due says **No words match this review**,
so changing a filter does not falsely imply that all reviews are done. These
states retain an Add word action. By topic remains deferred and does not display
an empty-data result.

Direct empty review sessions use preparation totals to show the same state and
Add word action, with a Back to Home link. No answer options or word contents
are included in the summary/count responses.
