# Project decisions

| ID | Decision | Options | Recommended default | Decide by |
| --- | --- | --- | --- | --- |
| D1 | Fields captured when adding a word | Word + English explanation only · plus example sentence · plus where you met it | Word + English explanation (required); example sentence optional | P0 |
| D2 | Answer checking rules | Exact match · ignore case and leading/trailing spaces · also ignore punctuation · allow small typos | Ignore case and leading/trailing spaces; otherwise exact spelling | P6 |
| D3 | Hints and retries | No hints · first letter / word length · one retry before revealing | No hints, one attempt, then reveal the correct word | P6 |
| D4 | Review scheduling (which words come back, and when) | Simple Leitner boxes · SM-2-style · FSRS | Leitner boxes driven by correct/incorrect (it fits pass/fail typed answers) | P6 |
| D5 | Session rules | Fixed count per session · all due words · daily cap | Due words first with a daily cap | P6 |
| D6 | Connectivity when offline | Online required · read-only cache · queue adds/answers locally and sync later | Online required for R0; explicit cache/queue decision before R1 | R0 implementation; before R1 scope |
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

## Review implementation log — 2026-11-10

Before the next UI changes, add backend unit coverage for these rules:

- D2: trim outer whitespace and case-fold; preserve internal whitespace,
  punctuation, accents and compatibility characters. Empty input is incorrect.
- D3: no hints, one recorded attempt per prompt. Retrying a submission after a
  lost response reuses its attempt ID and returns its recorded result.
- D4: correct answers advance one level, capped at 7, with intervals of
  1, 2, 4, 7, 14, 30 and 60 days. Incorrect answers reset to level 0 and are due
  in 10 minutes. All intervals start at server submission time.
- D5: snapshot currently due words at session start, oldest due first, up to the
  remaining 20-attempt daily allowance. Newly added words wait for the next
  session. Finish when that snapshot is exhausted, or the server reports that
  the daily cap was reached elsewhere. No client clock determines eligibility.

Nothing due is a distinct empty state. Authentication expiry preserves the
in-memory draft behind the existing sign-in overlay; signing into another account
clears it. Network retries preserve the exact answer, elapsed duration and attempt
ID, including when the first response was lost after the server committed.

## D6 — R0 connectivity and the pre-R1 decision

Status: R0 accepted; cache/queue decision required before R1 scope is finalized.

R0 requires an online server. Failed connections, 15-second request timeouts,
and unavailable gateways show “You're offline or the server is unreachable.
Check your connection and try again.” This deliberately does not claim to know
whether the device, network, or server is at fault. Validation errors and expired
sessions retain their separate handling. Retry is explicit; writes are not
queued or automatically replayed after connectivity failures.

Keep typed sign-in/sign-up fields, new-word fields, and review answers in memory
on failure. Clear new-word fields only after confirmed success. Review retries
reuse the original attempt ID, answer and elapsed duration, so a response lost
after commit does not record a second attempt. A failed add may already have
committed; a retry can return the existing duplicate-word message. Do not claim
that an unconfirmed write was saved. Session connectivity failures preserve
credentials and the mounted account's drafts. Reloading, closing the app, or
switching accounts may discard drafts; R0 does not persist them to disk.

Before R1, review actual R0 usage and record an explicit accept/defer decision:

| Option | Benefit | Additional work to justify |
| --- | --- | --- |
| Keep online-only | Smallest maintenance burden; server remains authoritative | Accept interruption during outages |
| Read-only local cache | Browse previously loaded words offline | Account isolation, stale-data labels, expiry, logout/deletion cleanup, storage/privacy tests |
| Durable write queue | Add words or answer without a connection | Idempotent adds, review eligibility and daily-cap conflicts, ordering, retries, account changes, sync status, failed-item recovery, schema upgrades |

Default for R1 planning: keep online-only unless repeated real offline usage
blocks learning. If the need is browsing, consider a read-only cache first.
Approve a queue only if offline creation/review is a demonstrated requirement
and its conflict/recovery behavior can be specified and tested. PostgreSQL
remains the source of truth for all options. The R1 planning checkpoint must
record observed outage frequency, affected workflows, chosen option, and why
its user benefit warrants the maintenance cost; no queue is approved by R0.

Manual acceptance checks on web and a device: disable connectivity while typing
an add or answer, submit, verify the message and unchanged input, reconnect and
retry. Repeat for sign-in and an unreachable server. Confirm a review retry
records one attempt, and that validation/credential errors are not reported as
offline. Also verify a timed-out request releases the busy state.

## Client storage — R0 / P3

Status: Accepted.

Persist only what is required to restore authentication and explicitly justified
minimal preferences. The current persistence inventory is:

| Data | Native | Web |
| --- | --- | --- |
| Refresh credential | One SecureStore entry: `wordrecall.refresh` | API-managed HttpOnly, Secure, SameSite=Strict cookie, scoped to `/api/v1/auth` |
| Access credential | Memory only | Memory only |
| Preferences | None persisted; appearance follows the OS | None persisted; appearance follows the browser/OS |
| Profile, words, review prompts/results, typed drafts/passwords | Memory only | Memory only |

Use the existing platform-specific refresh-storage adapter for native token
reads, rotation and deletion. Never fall back to plaintext if SecureStore fails.
Successful sign-out/account deletion and rejected refresh credentials clear the
native credential; transient connection failures retain it for retry. Web cookie
creation/rotation/expiry is handled by the API, never JavaScript. Secure cookies
are required for deployed HTTPS; the existing local HTTP exception is development
only. Do not store tokens in localStorage, sessionStorage, IndexedDB, AsyncStorage,
files, logs, URLs, or a vocabulary cache.

Native writes use `WHEN_UNLOCKED_THIS_DEVICE_ONLY` so iOS credentials are available
while unlocked and do not migrate to another device through backup restoration.
Keep the existing key/service; existing sessions get the updated protection on
their next successful token rotation. The Expo SecureStore plugin explicitly
configures Android backup exclusions. A native build is needed to apply plugin
configuration. iOS Keychain entries can survive uninstall/reinstall: do not treat
uninstall as logout or promise it erases credentials. These platform behaviors
follow the [Expo SDK 58 SecureStore documentation](https://docs.expo.dev/versions/v58.0.0/sdk/securestore/).

No new preference store is needed for R0. If a future feature requires a persisted
preference, document its key, type, default, purpose and cleanup behavior here
before adding it. Store only the minimal non-sensitive value; do not serialize
profiles or application state. Device/browser password managers are controlled
by the user and remain supported through autofill, separate from app persistence.
D6's pre-R1 cache/queue decision must explicitly revise this inventory before
any vocabulary data or pending writes are stored locally. PostgreSQL remains
the source of truth.
