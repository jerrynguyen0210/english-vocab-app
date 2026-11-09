# Project decisions

## D11 — App identity

Status: Accepted

| Field | Value |
| --- | --- |
| Display name | WordRecall |
| Expo slug | `wordrecall` |
| iOS bundle identifier | `com.jerrynguyen.wordrecall` |
| Android package name | `com.jerrynguyen.wordrecall` |

The slug is derived from the display name in lowercase. These values are configured in `client/app.json`.

## D12 — Validation, duplicate words, and account isolation

Status: Accepted

Reject duplicate words with HTTP 409 rather than allowing a warning/override.
The database enforces uniqueness on `(user_id, normalised_word)`, including
concurrent inserts. Normalization applies Unicode NFKC, case folding, and
collapsed whitespace. Accents and punctuation remain significant. Another
account can save the same word. Explanations do not participate in uniqueness;
a rejected duplicate changes neither the word nor its review schedule.

Required request fields and limits (measured in Unicode characters, before
trimming) are:

| Request | Fields |
| --- | --- |
| Register/sign-in | Valid email up to 320; password 12–128, preserved verbatim |
| Create word | Word 1–200; English explanation 1–5000; both must be nonblank and are trimmed |
| Submit answer | Typed answer 0–200; time_taken_ms is a strict integer from 0 to 2147483647 |
| Native refresh/logout | Refresh token 32–256 when supplied; a missing credential is unauthorized |
| Review queue | Limit 1–50, default 1 |

An empty/whitespace answer is an intentional failed recall and is recorded as
incorrect. A missing answer is invalid. JSON request schemas reject unexpected
fields, including caller-supplied user_id, result, and scheduling values.
Missing fields, nulls, wrong types, invalid UUIDs and out-of-range values return
422; failed authentication returns 401. Web refresh/logout use the HttpOnly
cookie instead of a JSON token.

All product reads and writes derive ownership from the authenticated session.
Word and review lookups include the signed-in user's ID; review-state deletion
uses that user's word IDs. Account erasure targets only that user and their
sessions, attempts and vocabulary. A missing review and a review belonging to
another user both return 404 without revealing the answer or recording an
attempt. Authentication necessarily resolves accounts by validated credentials
or opaque tokens before a user is signed in. Shared IP rate-limit housekeeping
is infrastructure data and has no account owner.
