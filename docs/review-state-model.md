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

Migration `0010` adds SM-2 `repetitions` (initially 0), `interval_days`
(initially 0), and `ease_factor` (initially 2.5, minimum 1.3). Existing due dates,
counts, levels, and history are preserved; subsequent answers use the new SM-2
state. Level is retained for compatibility, but does not determine the interval.
See [D4](decisions.md) and [Review preparation](review-preparation.md).

Updates to scheduling state and immutable attempts occur in one transaction
under the user/word locks. Session authorization binds to the prior scheduling
state so another device's review invalidates stale prompts.
