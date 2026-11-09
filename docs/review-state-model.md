# Review state

`ReviewState` stores the current review progress of a user-owned word. Ownership
is inherited through `words.user_id`; a second user ID is unnecessary.

| Field | Type | Meaning |
| --- | --- | --- |
| `word_id` | UUID, primary key and foreign key | References `words.id`; allows at most one state per word. |
| `level` | nonnegative integer | Box/level, initially 0 (new). |
| `due_at` | timestamp with time zone, required, indexed | Next review time; defaults to database current time (immediately due). |
| `correct_count` | nonnegative integer | Lifetime correct answers, initially 0. |
| `incorrect_count` | nonnegative integer | Lifetime incorrect answers, initially 0. |
| `last_reviewed_at` | nullable timestamp with time zone | Null until the first review. |

Migration `0004` initializes states for existing words. Future word creation must
insert a state in the same transaction. The foreign key and primary key enforce
valid ownership references and at most one state, but do not force every future
word insert to create a state. Hard deletion of a word cascades to its state;
account soft deletion retains it.

This is a persistence foundation, not a scheduling implementation. Leitner can
use `level` directly; SM-2 and FSRS need additional algorithm-specific state and
a defined grading/scheduling policy before implementation. No algorithm is
selected by this schema. Update counts, level, due time, and last-review time
atomically when implementing reviews to avoid lost updates.

Implementation: `backend/app/models/review_state.py`; migration: `0004_review_states`.
