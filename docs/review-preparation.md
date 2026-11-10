# Review preparation

Flow: Home → Review preparation → Review → Review finished.
The client uses live authenticated data. Answer mode (multiple choice or typing)
is selected on the Review screen, after choosing a source and starting.

## Selection and count

`GET /api/v1/reviews/preparation` accepts:

- `source`: `time`, `recall` (default), or `topic`.
- `period`: `Yesterday`, `Weekly` (default), or `Monthly`.
- `include_overdue`: boolean, default true; applies only to recall.
- `topic`: saved tag search, maximum 100 characters; required for topic source.

Yesterday uses the user's stored IANA timezone and the previous calendar day;
DST days may have 23 or 25 hours. Weekly and Monthly use rolling 7 and 30 days
ending at the server's current instant. Recall includes all scheduled timestamps
before next local midnight; disabling overdue also requires a timestamp at or
after today's local midnight. Future times within today are eligible.
Topic selection searches normalized saved tags using a literal substring,
ignoring case and compatibility/whitespace differences. Multiple matching tags
on one word do not duplicate that word.

The response is `{count, matching_count}`. Count is the number ready for this
session, capped at 50 and at the user's remaining daily attempt allowance.
The client disables Start until the current count loads, while empty or after a
failure, and offers retry. Changing filters discards obsolete responses. Counts
refresh when returning to preparation. A session rechecks selection and allowance
at start, so its count may differ if another device changes data in the meantime.

## Saved topic tags

`POST /api/v1/words` accepts optional `topics`, up to 10 nonblank tags of at most
100 normalized characters. Tags are normalized, deduplicated and stored in
`word_topics`. Add word provides a comma-separated topic input applied to saved
search results. Existing untagged words remain untagged; no topic is inferred.
`GET /api/v1/words/topics?q=...` returns up to 20 matching saved tags for the
current user. Topic tags are included in operator exports and removed on erasure.

## Review sessions and answers

`GET /api/v1/reviews/session` accepts the same selection and returns a bounded
snapshot. Each prompt includes masked explanation/example, `word_id`,
`attempt_id`, `review_token` and shuffled `choices`. Choices include the answer
and up to three other owned saved words, without identifying the correct option.
A one-word bank returns no choices, so typing remains available. The legacy
`/reviews/next` endpoint remains typing-only and selects currently due instants.

Answers submit the prompt's `attempt_id` and `review_token`, `typed_answer`
(the selected option for choice mode), and `time_taken_ms` to the existing
`POST /reviews/{word_id}/answer`. Tokens expire after 24 hours, bind user, word,
attempt and prior scheduling state, and authorize selected practice even before
the word's due date. Forged, expired or stale tokens are rejected. Exact retries
return the persisted result without another attempt or scheduling change. The
server still enforces ownership and daily allowance under its existing locks.
A client retry retains the exact body and disables editing/mode changes.

Both modes and all sources update SM-2 state and attempt history. Binary grades
are 4 for correct and 1 for incorrect, with 10-minute relearning after failure.
D4 documents the full policy, based on the
[original SM-2 algorithm](https://super-memory.org/archive/english/ol/sm2.htm).
Migration `0010` adds topic and SM-2 storage, preserving existing due dates and
history. Apply it through the normal forward-only deployment process.
