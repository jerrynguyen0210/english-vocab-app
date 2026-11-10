# Project decisions

| ID | Decision | Options | Recommended default | Decide by |
| --- | --- | --- | --- | --- |
| D1 | Fields captured when adding a word | Word + English explanation only · plus example sentence · plus where you met it | Word + English explanation (required); example sentence optional | P0 |
| D2 | Answer checking rules | Exact match · ignore case and leading/trailing spaces · also ignore punctuation · allow small typos | Ignore case and leading/trailing spaces; otherwise exact spelling | P6 |
| D3 | Hints and retries | No hints · first letter / word length · one retry before revealing | No hints, one attempt, then reveal the correct word | P6 |
| D4 | Review scheduling (which words come back, and when) | Simple Leitner boxes · SM-2-style · FSRS | Leitner boxes driven by correct/incorrect (it fits pass/fail typed answers) | P6 |
| D5 | Session rules | Fixed count per session · all due words · daily cap | Due words first with a daily cap | P6 |
| D6 | Connectivity when offline | Online required · read-only cache · queue adds/answers locally and sync later | Online required for R0; revisit before R1 | P3/P7 |
| D7 | Auth method | Email + password · email magic link · OAuth/social | Email + password or magic link through your own FastAPI auth | P3 |
| D8 | Backend hosting | VPS/Docker host · managed container platform · BaaS for the database only | Docker on a host you're comfortable with; check pricing when you choose | P10 |
| D9 | First platform you use daily | Android phone · iPhone · web | The phone you carry every day; web for desktop | P2 |
| D10 | iOS build path | Mac + Xcode locally · cloud builds (Expo Build) · skip iOS for now | Depends on Mac access and the Apple account (see Platform realities) | Before P8 iOS testing |
| D11 | App name, bundle ID / package name | App name: **WordRecall**<br>iOS bundle ID: `com.jerrynguyen.wordrecall`<br>Android package name: `com.jerrynguyen.wordrecall` | Choose before the first native build | P2 |
| D12 | How friends get the app | Web link · Android APK · Play internal/closed testing · TestFlight | Web link + Android internal first | P10 |

## D11 — App identity

Status: Accepted

| Field | Value |
| --- | --- |
| Display name | WordRecall |
| Expo slug | `wordrecall` |
| iOS bundle identifier | `com.jerrynguyen.wordrecall` |
| Android package name | `com.jerrynguyen.wordrecall` |

The slug is derived from the display name in lowercase. These values are configured in `client/app.json`.

## D14 — Validation, duplicate words, and account isolation

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

## D13 — Immutable migrations and forward-only deployment

Status: Accepted

Alembic revisions are versioned and immutable after shipping. All revisions
already present in the PR base or previous push are protected by CI: only new
files may be added to `backend/migrations/versions/`. Fix schema mistakes with a
new revision, never by editing history, downgrading or stamping deployed databases.

The Docker entrypoint runs `python -m app.migrate` before starting the API and
exits on failure. Non-container deployments run the same command in their release
step. The runner requires one head, upgrades only to head, and uses a PostgreSQL
session advisory lock on the same connection used by Alembic to serialize
concurrent deploys. Re-running at head is a no-op. CI checks forward upgrades,
model/schema agreement, and a repeated upgrade; it never downgrades a database.
Existing historical downgrade functions remain unchanged.

Rolling releases require compatible schema changes: add first, transition app
usage, then remove obsolete schema in a later revision. Production backup and
retention policies remain the deployment operator's responsibility.

## D2, D3 and D5 — Typed recall and session completion

D2 compares the typed answer and saved word after trimming outer whitespace and
Unicode case folding. Internal whitespace, punctuation, accents, spelling and
Unicode compatibility characters remain significant. This is intentionally
stricter than D14's duplicate-word normalization; normalized attempt text remains
available for history, but does not determine correctness.

D3 permits one recorded answer per presented prompt; blank input records an
incorrect recall. The server records the original answer, result and elapsed time
and updates the schedule in the same transaction. Feedback is shown before the
user advances to the next prompt.

D5 uses due-time order and a cap of **20 attempts per user-local day**, confirmed
by the user. Both correct and incorrect attempts count across sessions/devices.
The cap is enforced on queue reads and submissions; rejected submissions do not
record an attempt or change the schedule. It resets at local midnight according
to the account's saved IANA timezone (UTC by default). `REVIEW_DAILY_CAP` is a
server configuration override, default 20. No schema migration is required.

A session ends when the queue is empty or the daily cap is reached. Its finish
screen displays the number of correct answers out of attempts completed in that
screen session; reopening Review starts a new screen-session total while retaining
the server's daily cap usage.
