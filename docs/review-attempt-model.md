# Review attempt

`ReviewAttempt` is an append-only record of an answer submission. Multiple
attempts for the same word are allowed, each identified by an application-generated UUID.

| Field | Type | Meaning |
| --- | --- | --- |
| `id` | UUID, primary key | Unique attempt identity. |
| `word_id` | UUID, required | Reviewed word. |
| `user_id` | UUID, required | Word owner who submitted the answer. |
| `typed_answer` | text, required | Exact submitted answer; empty answers are allowed. |
| `normalised_answer` | text, required | Same normalisation as `Word.normalised_word`. |
| `result` | string, required | `correct` or `incorrect`, enforced by a check constraint. |
| `reviewed_at` | timestamp with time zone, required | Defaults to database current time. |
| `time_taken_ms` | nonnegative integer, required | Answer duration in milliseconds; zero is valid. |

A composite foreign key checks that the word belongs to the recorded user.
Attempts prevent hard deletion of their referenced word; soft deletion retains
history. Indexes support history lookup by word or user and review time.

ORM assignment to `typed_answer` computes `normalised_answer`. Direct SQL and
bulk inserts must supply the canonical value themselves. Result is stored as a
historical decision, not recalculated when a word is edited. Future review handling
must derive result server-side and insert the attempt and update review state in
one transaction. Authentication must derive user identity from the session.

ORM update/delete hooks reject history changes. Migration `0005` adds PostgreSQL
and SQLite triggers to reject SQL updates and deletes; PostgreSQL also rejects
TRUNCATE. Database administrators can still change schema or disable triggers;
these protections target routine application writes. Metadata-only `create_all`
does not install database triggers; deploy using migrations. Corrections and
retention/erasure workflows need an explicit future policy.

Implementation: `backend/app/models/review_attempt.py`; migration: `0005_review_attempts`.
