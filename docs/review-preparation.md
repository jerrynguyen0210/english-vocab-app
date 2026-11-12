# Review preparation

Flow: Home → Review preparation → Review → Review finished.
The client uses live authenticated data. Answer mode (multiple choice or typing)
is selected on the Review screen, after choosing a source and starting.

## Selection and count

`GET /api/v1/reviews/preparation` accepts:

- `source`: `time`, `recall` (default), or `topic`.
- `topic`: required, nonblank, at most 200 characters when source is `topic`.
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
session, capped at 50 per session (10 for topics), with no daily attempt limit.
The client disables Start until the current count loads, while empty or after a
failure, and offers retry. Changing filters discards obsolete responses. Counts
refresh when returning to preparation. A session rechecks selection and allowance
at start, so its count may differ if another device changes data in the meantime.

## Semantic topic search

By topic searches the current user's saved words by meaning. Enter a topic and
select **Search** (or the keyboard Search key); typing alone sends no search.
Changing the text invalidates previous matches and disables Start. Searches and
counts refresh on focus, discard obsolete responses, and offer manual retry.
Before searching, the panel shows the saved-word bank total from `/reviews/summary`.

`GET /reviews/preparation?source=topic&topic=...` ranks the user's saved words with
NumPy cosine similarity against an Ollama topic embedding. It returns `count`
(up to 10) and `matching_count` (all words above the configured similarity
threshold), plus the existing summary totals. It reveals no words or answers.
`GET /reviews/session` uses the same selection and returns the top 10 signed,
masked review prompts in descending similarity order. Ties use word IDs. Topic
practice includes words regardless of due date and uses the same answer and
SM-2 scheduling flow as other practice. Selection is rechecked at session start.
No matches means no related saved words, even when nothing is due for recall.
Users do not need to assign topic tags.

### Embeddings and deployment

Migration `0016` adds nullable JSON embeddings, a model/revision key and a source
text hash to `words`. Old vocabulary and review history are preserved. Embeddings
are removed with their words during account erasure. Shipped migrations remain
unchanged; apply the new revision using the existing guarded forward migration
process (`python -m app.migrate`). Never downgrade or stamp a deployed database.

The `embedding-worker` service in both Compose stacks embeds each word together
with its explanation and optional example. It automatically indexes existing
words, newly saved words and model/revision changes in batches of 32. Saving a
word never waits on Ollama. Source edits invalidate stored embeddings. Updates
only persist if the source still matches; concurrent deletion cannot resurrect
data. Restarting resumes pending work without regenerating completed vectors.
Provider failures retry every 10 seconds and never log private vocabulary.

Install the configured model on the Ollama host first, for example:

```sh
ollama pull embeddinggemma
```

Configure the backend using these sanitized example settings:

```dotenv
EMBEDDING_MODEL=embeddinggemma
EMBEDDING_REVISION=1
EMBEDDING_TIMEOUT_SECONDS=10
EMBEDDING_INDEX_TIMEOUT_SECONDS=120
TOPIC_SIMILARITY_THRESHOLD=0.35
```

The model must support `/api/embed`; it is separate from `OPENROUTER_MODEL`, which
generates review sentences through OpenRouter. Both indexing and querying use `EMBEDDING_MODEL`.
Bump `EMBEDDING_REVISION` if weights are replaced under the same model name;
this queues a full reindex. The cosine threshold is an initial configurable
cutoff, not a validated confidence score; tune it with representative topics.

For a backend running outside Compose, start `python -m app.embedding_worker`.
To backfill once and exit after all pending words are indexed, run
`python -m app.embedding_worker --once` from `backend/`. A failed one-time run
exits nonzero and can safely be repeated. Compose and the deployment helper
start the worker automatically after API migrations.

While any current-user word is awaiting indexing, topic preparation/session
returns 409 with a retryable preparation message. Other users' pending words
do not block searches. Provider failures, malformed/zero/nonfinite vectors and
dimension mismatches return 503 instead of a false empty result. Embeddings
are persisted, and only the short query is embedded for each search/session.

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
server still enforces ownership and scheduling under its existing locks.
A client retry retains the exact body and disables editing/mode changes.

Both modes and all three sources update SM-2 state and attempt history. Binary grades
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
A selection
with no matches while other words are due says **No words match this review**,
so changing a filter does not falsely imply that all reviews are done. These
states retain an Add word action. A topic with no related saved words displays
No words match this review, independently of recall due counts.

Direct empty review sessions use preparation totals to show the same state and
Add word action, with a Back to Home link. No answer options or word contents
are included in the summary/count responses.

`daily_remaining` is deprecated and always returns 50 for older clients. It no
longer represents a daily allowance and never decreases after an answer.
