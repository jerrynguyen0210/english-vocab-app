# Word

A `Word` is a vocabulary entry owned by one user.

| Field | Type | Meaning |
| --- | --- | --- |
| `id` | UUID, primary key | Application-generated on insertion. |
| `user_id` | UUID, required foreign key | Owner in `users.id`. |
| `word` | text, required | Exact text as typed, preserved for display. |
| `normalised_word` | text, required | Canonical value for duplicate checks and answer comparison. |
| `english_explanation` | text, required | English definition or explanation. |
| `example_sentence` | nullable text | Optional example sentence (D1). |
| `created_at` | timestamp with time zone, required | Database-generated creation time. |

`normalise_word` applies Unicode NFKC normalization, Unicode case folding, and
whitespace trimming/collapsing. Accents and punctuation remain significant.
Use the same function on submitted answers before comparing them with the stored
value. Setting `Word.word` through the ORM refreshes `normalised_word` while
preserving the original input. Direct SQL and bulk updates bypass this validator;
those callers must compute and supply the canonical value themselves and must
not overwrite it independently.

A database unique constraint on `(user_id, normalised_word)` rejects duplicate
entries for an owner, including concurrent insertions. Different users can save
the same word. Required text fields cannot be empty or space-only. No automatic
cascade deletion is configured; account soft deletion retains vocabulary.

Implementation: `backend/app/models/word.py`; migration: `0003_words`.
