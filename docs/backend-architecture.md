# Backend architecture

This describes the backend source currently in this repository, including
migrations through `0015` and the deployment helper. It describes the local
Docker Compose setup; it does not claim that a running deployment has been updated.

## 1. Processes and external dependencies

The backend has one shared application codebase, an HTTP API process, and a
background worker process. Both processes use the same PostgreSQL database.
Queue administration and user export run as occasional commands.

```mermaid
flowchart TB
    browser["Browser client"]
    native["iOS / Android client"]
    operator["Operator"]

    subgraph api_process["API process: Uvicorn / FastAPI"]
        http["app.main:app<br/>CORS and /api/v1 routing"]
        boundary["Schemas, authentication dependencies<br/>and HTTP error translation"]
        services["Auth, accounts, words<br/>and review services"]
        dictionary["Local dictionary service<br/>WordNet + LemmInflect"]
        http --> boundary --> services
        services --> dictionary
    end

    subgraph worker_process["Background worker process"]
        loop["app.prompt_worker<br/>Polling loop"]
        jobs["services/prompt_jobs/worker.py<br/>Claim, generate, finish"]
        loop --> jobs
    end

    subgraph commands["On-demand commands"]
        admin["app.prompt_jobs<br/>Status and explicit retry"]
        export["app.export_user<br/>Private user-data export"]
    end

    db[("PostgreSQL<br/>Accounts, sessions, vocabulary,<br/>review state, history and prompt jobs")]
    ollama["Configured Ollama server<br/>Sentence generation"]
    corpus[("Installed WordNet corpus<br/>Local files")]
    archive["Private export file"]

    browser -->|"HTTP; bearer access token; refresh cookie"| http
    native -->|"HTTP; bearer access token; native refresh token"| http
    services <-->|"SQLAlchemy sessions and transactions"| db
    dictionary --> corpus
    jobs <-->|"Claim and completion transactions"| db
    jobs <-->|"HTTP outside database transactions"| ollama
    operator --> admin
    operator --> export
    admin <-->|"Counts, failure metadata, retry reset"| db
    export -->|"Read-only consistent snapshot"| db
    export --> archive
```

The API never calls Ollama while saving a word or serving a review. Local
dictionary search does not use a network service. The queue is a database table;
there is no separate message broker. The current worker processes one job at a
time, but multiple PostgreSQL workers can claim different jobs.

## 2. Code organization and dependency direction

```mermaid
flowchart TB
    main["main.py<br/>Application assembly"]
    routes["api/router.py + api/routes/<br/>HTTP endpoints"]
    transport["api/auth_transport.py<br/>Cookies and browser/native transport"]
    deps["api/dependencies.py<br/>DB session, current user, auth guard"]
    schemas["schemas/<br/>Validated requests and responses"]
    errors["api/errors.py<br/>Service failures to HTTP status codes"]
    service["services/<br/>Business rules and transactions"]
    models["models/<br/>ORM records, constraints and validators"]
    core["core/<br/>Settings, database, UTC time and text normalization"]
    llm["llm/ollama_review.py<br/>Provider request and output validation"]
    entry["prompt_worker.py + prompt_jobs.py<br/>Thin command entry points"]

    main --> routes
    routes --> schemas
    routes --> deps
    routes --> transport
    routes --> errors
    routes --> service
    transport --> service
    deps --> service
    deps --> core
    service --> schemas
    service --> models
    service --> core
    models --> core
    entry --> service
    service -->|"Prompt worker only"| llm
```

```text
backend/
  app/
    main.py
    api/
      router.py
      auth_transport.py
      dependencies.py
      errors.py
      routes/                  auth, account, words, reviews, health
    core/                      config, database, time, text
    schemas/                   auth, account, words, reviews
    models/                    user, auth, word, review_state,
                               review_attempt, prompt_job
    services/
      auth.py
      accounts.py
      words.py
      dictionary.py
      errors.py
      reviews/
        service.py             Session and answer orchestration
        selection.py           Shared word-selection query
        queries.py             Review queue queries and totals
        answers.py             Answer comparison
        scheduling.py          SM-2 scheduling
        prompts.py             Fallback construction and answer masking
        choices.py             Four-option distractor selection
        tickets.py             Signed review authorization
      prompt_jobs/
        worker.py              Claiming, generation and completion
        management.py          Queue inspection and failed-job reset
    llm/ollama_review.py
    prompt_worker.py            Continuous worker command
    prompt_jobs.py              Status/retry command
    migrate.py                  Guarded forward-only migration command
    migration_backup.py         Pre-migration database backups
    export_user.py              Operator-only data export
  migrations/versions/          Immutable shipped schema revisions
  tests/
    api/                       Accounts, contracts, words, answers,
                               sessions and prompt-worker integration tests
    test_*.py                  Focused service/model/command tests
  docker-compose.yml
  Dockerfile
  entrypoint.sh
```

## 3. HTTP request boundaries

```mermaid
flowchart TB
    request["Incoming request"] --> cors["CORS policy"]
    cors --> kind{"Route type"}
    kind -->|"Auth POST"| guard["Check browser Origin / cookie policy<br/>Shared peer-IP rate limit"]
    kind -->|"Protected endpoint"| bearer["Hash bearer token<br/>Check session expiry and active account"]
    kind -->|"Operational endpoint"| public["Health or API documentation"]
    guard --> validation["Pydantic request validation"]
    bearer --> validation
    validation --> business["Route calls service<br/>Owner-scoped queries and transactions"]
    business --> success["Validated response<br/>Protected/auth responses use no-store"]
    business --> failure["ServiceError translated by api/errors.py"]
    failure --> codes["401 authentication / account<br/>404 missing or other owner's review<br/>409 conflict / duplicate<br/>429 auth rate limit<br/>503 dictionary unavailable"]
    validation --> invalid["422 invalid request"]
    guard --> denied["403 disallowed or missing required Origin"]
```

The two authentication branches differ: Origin checks and the database-backed
rate limit protect auth POST routes; bearer authentication protects product
routes and `/auth/me`. `/health` checks process liveness without querying the
database. Body validation and dependencies are shown as conceptual stages, not
a guarantee about every internal framework execution step.

| Method | Route | Responsibility |
| --- | --- | --- |
| POST | `/api/v1/auth/register` | Create account and initial session; optional validated timezone |
| POST | `/api/v1/auth/sign-in` | Verify password and issue a new session |
| POST | `/api/v1/auth/refresh` | Lock session and rotate tokens |
| POST | `/api/v1/auth/logout` | Delete the authenticated refresh session |
| GET | `/api/v1/auth/me` | Return the active account profile |
| PATCH | `/api/v1/account` | Update the current account's validated timezone |
| DELETE | `/api/v1/account` | Atomically erase account and owned records |
| GET | `/api/v1/words/search` | Local lexical search with owner-specific saved markers |
| POST | `/api/v1/words` | Save word, fallback prompt, review state and generation job |
| GET | `/api/v1/reviews/next` | Return immediately due hints; limit 1–50 |
| GET | `/api/v1/reviews/summary` | Saved-word and user-local daily due totals |
| GET | `/api/v1/reviews/preparation` | Matching count and bounded session count |
| GET | `/api/v1/reviews/session` | Up to 50 masked review items and signed tickets |
| POST | `/api/v1/reviews/{word_id}/choices` | Reveal four options for an authorized review item |
| POST | `/api/v1/reviews/{word_id}/answer` | Grade, record history and update scheduling atomically |
| GET | `/health` | Process liveness |
| GET | `/docs`, `/openapi.json` | API documentation and schema |

## 4. Authentication and refresh rotation

```mermaid
sequenceDiagram
    participant C as Browser or native client
    participant A as Auth route and guard
    participant S as Auth service
    participant D as PostgreSQL
    C->>A: Register or sign in
    A->>D: Increment shared peer-IP rate bucket
    A->>S: Validated credentials and platform
    alt Registration
        S->>S: Argon2 password hash, normalize email
        S->>D: Insert user and initial auth session in one transaction
    else Sign in
        S->>D: Load user and password hash
        S->>S: Argon2 verification, reject inactive account
        S->>D: Insert new auth session
    end
    Note over S,D: Persist SHA-256 token digests, never plaintext tokens
    S-->>A: Random access and refresh tokens
    alt Browser
        A-->>C: Access token JSON and HttpOnly SameSite=Strict refresh cookie
    else Native
        A-->>C: Access and refresh tokens in JSON
    end
    C->>A: Protected request with bearer access token
    A->>D: Resolve token digest, check expiry and active user
    A-->>C: Authorized response
    C->>A: Refresh request
    A->>D: Apply auth guard and rate limit
    A->>S: Refresh token and platform
    S->>D: Lock matching session FOR UPDATE
    S->>D: Replace access and refresh digests, commit
    A-->>C: New tokens through the platform-specific transport
```

Defaults are a 15-minute access token, a 30-day refresh lifetime, and 20 auth
POST requests per peer IP per 60-second window. Refresh rotation preserves the
session's original refresh expiry. Browser cookie security is configurable;
native token transport requires `X-Auth-Platform: native` and no Origin header.
Auth failures and disabled/deleted accounts do not bypass the guard.

## 5. Word search and atomic save

```mermaid
sequenceDiagram
    participant C as Client
    participant A as Words API
    participant S as Words service
    participant L as Local dictionary
    participant D as PostgreSQL
    participant W as Background worker
    C->>A: GET /words/search with query and optional filters
    A->>S: Current user and validated search parameters
    S->>L: Normalize query, WordNet family and LemmInflect forms
    L-->>S: Up to 60 matching dictionary entries
    S->>D: Find matching normalized words owned by this user
    S-->>C: Entries with saved markers
    C->>A: POST /words with word, definition and optional example
    A->>S: Validated input and current user
    S->>D: Check normalized duplicate, lock active account
    S->>S: Build masked example or definition fallback
    S->>D: Insert word, immediately due review state, and prompt job
    S->>D: Commit all three records together
    S-->>C: 201 Created without waiting for generation
    W->>D: Claim the persisted job later
    Note over C,D: The fallback is already reviewable while generation is pending or failed
```

The unique `(user_id, normalised_word)` constraint resolves concurrent duplicate
saves. A failed enqueue rolls back the word and review state as well. Dictionary
corpus access is protected by a process-local lock and bounded caches because
the lexical reader is shared by request handlers.

## 6. Review selection, masking and choices

```mermaid
flowchart TB
    prep["Preparation / session request"] --> owner["Scope words to the current user"]
    owner --> source{"Selection source"}
    source -->|"Recall"| day["Due before next local midnight<br/>Optionally exclude overdue words"]
    source -->|"Time: Yesterday"| yesterday["Created during previous local calendar day"]
    source -->|"Time: Weekly / Monthly"| rolling["Created during previous 7 / 30 elapsed days"]
    day --> selection["Shared selection query"]
    yesterday --> selection
    rolling --> selection
    selection --> count["Preparation counts all matching words<br/>Session count capped at 50"]
    selection --> snapshot["Session reads at most 50 word/state pairs"]
    snapshot --> mask["Mask target in stored prompt, definition and example"]
    mask --> ticket["Generate attempt UUID and signed 24-hour ticket<br/>Bind user, word and current scheduling state"]
    ticket --> mode{"Answer mode"}
    mode -->|"Typing: default"| typing["Return masked item and attempt metadata<br/>No choices or explicit answer field"]
    mode -->|"Choice"| pool["Read at most 200 saved candidate words<br/>Include up to 50 session targets"]
    pool --> tiers["Infer parts of speech<br/>Select distractors by tier"]
    tiers --> options["Return exactly 4 distinct shuffled options<br/>The answer is one unlabeled option"]
    typing --> switch["Explicit choices request<br/>Validate ownership and signed ticket"]
    switch --> one["At most 200 candidates plus one target"]
    one --> tiers
```

The candidate query follows the existing `(user_id, normalised_word)` index.
Profiles cover at most 250 saved words per choice session or 201 per single-item
choice request; lexical fallback processing is also bounded. Distractor tiers
prefer saved words with matching parts of speech, lexical family words, other
saved candidates, matching general vocabulary, then general vocabulary of any
part of speech.

Recall selection includes all reviews scheduled before the end of the user's
local day, including items not due at this instant. `/reviews/next` instead uses
`due_at <= now`. Signed session tickets authorize the selected snapshot, including
time-based practice of words whose normal due date is in the future. Updating a
timezone changes local selection boundaries without rewriting UTC due dates.

## 7. Answer submission, concurrency and retries

```mermaid
flowchart TB
    submit["POST answer<br/>Typed answer, elapsed time, optional attempt ID and ticket"]
    submit --> account["Lock active account"]
    account --> row["Lock owned Word and ReviewState rows"]
    row --> found{"Owned review exists?"}
    found -->|"No"| missing["404"]
    found -->|"Yes"| previous{"Attempt ID already recorded?"}
    previous -->|"Yes"| same{"Same owner, word, answer and duration?"}
    same -->|"No"| conflict["409"]
    same -->|"Yes"| replay["Return original result and saved next_due_at<br/>No second history record or schedule update"]
    previous -->|"No"| auth{"Ticket supplied?"}
    auth -->|"Yes"| valid{"Signature, expiry, attempt and state match?"}
    auth -->|"No: legacy request"| due{"Item immediately due?"}
    valid -->|"No"| conflict
    due -->|"No"| conflict
    valid -->|"Yes"| normalize["Normalize both strings<br/>Unicode NFKC, case folding and collapsed whitespace"]
    due -->|"Yes"| normalize
    normalize --> grade{"Exact normalized match?"}
    grade -->|"Correct"| success["SM-2 grade 4<br/>1 day, 6 days, then ceil(previous interval x previous ease)"]
    grade -->|"Incorrect"| fail["SM-2 grade 1<br/>Reset repetitions and interval; retry in 10 minutes"]
    success --> atomic["Insert immutable attempt with next_due_at snapshot<br/>Update mutable review state; commit together"]
    fail --> atomic
    atomic --> feedback["Return attempt ID, result, correct word and next_due_at"]
```

Duplicate attempts are checked before ticket expiry, so a lost-response retry
can still return an accepted result after its original ticket expires. Attempts
created before migration `0014` have no original due-date snapshot and retain
the legacy fallback to the current schedule. Accents, punctuation and spelling
remain significant after normalization. There is no daily attempt cap.

The account lock serializes answer writes, word creation, timezone changes and
account erasure for that account. Password-session rotation separately holds the
auth-session row lock through commit. Database constraints and history triggers
provide protections in addition to service-level checks.

## 8. Durable prompt-job lifecycle

```mermaid
stateDiagram-v2
    [*] --> Pending: Word transaction commits a job
    Pending --> InFlight: Claim with row lock and fresh lease token
    InFlight --> Completed: Valid prompt and matching lease
    Completed --> [*]: Update word prompt and delete job atomically
    InFlight --> WaitingRetry: Generation fails below attempt limit
    WaitingRetry --> Pending: Backoff expires
    InFlight --> Pending: Worker crashes and lease expires below limit
    InFlight --> Failed: Generation fails at attempt limit
    InFlight --> Failed: Final lease expires and next claim pass detects exhaustion
    Failed --> Pending: Operator explicitly resets failed job
    Pending --> Erased: Account deletion
    WaitingRetry --> Erased: Account deletion
    InFlight --> Erased: Account deletion
    Failed --> Erased: Account deletion
    Erased --> [*]
```

These are derived states, not values in a status column. The worker uses
`available_at`, `lease_token`, `attempts` and `failed_at` to determine eligibility.
Queue monitoring reports an expired lease as pending until the next claim pass
reclaims it or marks it failed.

```mermaid
sequenceDiagram
    participant W as Worker polling loop
    participant Q as Prompt-job service
    participant D as PostgreSQL
    participant O as Ollama
    W->>Q: process_one
    Q->>D: Mark expired exhausted jobs failed
    Q->>D: Select eligible job FOR UPDATE SKIP LOCKED
    Q->>D: Increment attempts, set lease token and expiry, commit
    Q->>O: Generate sentence from word and meaning
    Note over Q,O: No database transaction is held during this HTTP request
    O-->>Q: Completed JSON sentence or provider failure
    Q->>Q: Validate exact target occurrence, mask answer locally
    Q->>D: Lock owner first, then job with matching lease token
    alt Valid output and current lease
        Q->>D: Update words.review_prompt and delete job, commit
    else Failure below attempt limit
        Q->>D: Save safe category, clear lease, set backoff, commit
    else Failure at limit
        Q->>D: Save failure timestamp/category, clear lease, commit
    else Deleted account or stale lease
        Q->>Q: Discard result
    end
    Q-->>W: Job was processed, or no eligible job
```

Default automatic limit: five claims. Retry delay is
`min(3600, 5 * 2 ** min(attempts, 10))` seconds, starting at ten seconds.
Lease duration is `OLLAMA_TIMEOUT_SECONDS + 60` seconds. The loop sleeps one
second when idle and five seconds after a database error. Lease expiry permits
recovery; it does not prove a slow or stalled old worker has stopped, so stale
completion protection is essential.

Failed jobs remain stored and keep the word's fallback usable. A partial index
on `(available_at, word_id) WHERE failed_at IS NULL` excludes terminal failures
from the ready queue. Safe categories distinguish provider HTTP errors,
connection errors, invalid input/output, and exhausted attempts. Vocabulary and
provider response bodies are not written to worker failure logs or queue status.

## 9. Database relationships

```mermaid
erDiagram
    users ||--o{ auth_sessions : owns
    users ||--o{ words : owns
    words ||--o| review_states : schedules
    words ||--o{ review_attempts : records
    words ||--o| prompt_jobs : queues

    users {
        uuid id PK
        string email UK
        string name "nullable"
        string password_hash "nullable with alternate identity"
        string auth_provider_id UK "nullable; reserved identity field"
        string timezone "IANA zone; default UTC"
        datetime created_at
        datetime disabled_at "nullable"
        datetime deleted_at "nullable"
    }
    auth_sessions {
        uuid id PK
        uuid user_id FK
        string access_hash UK
        string refresh_hash UK
        datetime access_expires_at
        datetime refresh_expires_at
        boolean native
    }
    auth_rate_buckets {
        string key PK "HMAC of peer address and time window"
        int count
        datetime expires_at
    }
    words {
        uuid id PK
        uuid user_id FK
        string word
        string normalised_word "unique within owner"
        string english_explanation
        string example_sentence "nullable"
        string review_prompt
        datetime created_at
    }
    review_states {
        uuid word_id PK, FK
        int level
        datetime due_at
        int correct_count
        int incorrect_count
        datetime last_reviewed_at "nullable"
        int repetitions
        int interval_days
        float ease_factor
    }
    review_attempts {
        uuid id PK
        uuid word_id FK "composite ownership reference"
        uuid user_id FK "composite ownership reference"
        string typed_answer
        string normalised_answer
        string result "correct or incorrect"
        datetime reviewed_at
        int time_taken_ms
        datetime next_due_at "nullable for pre-0014 history"
    }
    prompt_jobs {
        uuid word_id PK, FK
        datetime available_at
        int attempts
        uuid lease_token "nullable"
        datetime failed_at "nullable"
        string failure_category "nullable; safe category only"
    }
```

`review_attempts.(word_id, user_id)` references `words.(id, user_id)` as one
composite foreign key, preventing cross-account history references. Rate buckets
are shared operational records without a user foreign key. Word creation inserts
one review-state row, but the schema permits a word without one; the optional
ER relationships reflect database constraints rather than only the normal flow.
Completed prompt jobs are removed, while terminal failures remain until retry
or account erasure. The identity field does not imply an implemented OAuth flow.

## 10. Account erasure and timezone changes

```mermaid
flowchart TB
    request["Authenticated account request"] --> action{"Action"}
    action -->|"PATCH timezone"| validate["Validate IANA zone"]
    validate --> update_lock["Lock active account"]
    update_lock --> update["Save timezone and commit<br/>Keep all stored UTC review dates unchanged"]
    update --> profile["Return updated profile<br/>Future local-day queries use the new zone"]
    action -->|"DELETE account"| erase_lock["Lock active account"]
    erase_lock --> mark["Set deleted_at in the same transaction"]
    mark --> sessions["Delete all auth sessions"]
    sessions --> attempts["Delete review attempts<br/>Database trigger permits marked-account erasure"]
    attempts --> states["Delete review states"]
    states --> words["Delete words<br/>Cascade deletion removes prompt jobs"]
    words --> user["Delete user and commit"]
    user --> response["204 and clear browser refresh cookie"]
```

Ordinary history updates and deletes remain blocked. A worker finishing during
erasure uses the same owner-first locking order and rechecks existence, so a late
generation result cannot recreate erased words. Application erasure does not
rewrite retained infrastructure logs or backups.

## 11. Deployment and migration order

```mermaid
flowchart TB
    start["deploy_backend.sh start"] --> build["Build API and prompt-worker images<br/>from current checkout"]
    build --> db["Start PostgreSQL and wait for its health check"]
    db --> stop["Stop old prompt worker"]
    stop --> recreate["Force-recreate API container"]
    recreate --> entry["entrypoint.sh runs app.migrate"]
    entry --> head["Require exactly one migration head"]
    head --> lock["Acquire PostgreSQL advisory lock"]
    lock --> env{"Preview or production?"}
    env -->|"Yes"| backup["Create private pg_dump archive<br/>Verify archive listing and SHA-256 metadata"]
    env -->|"Development / test"| migrate["Upgrade forward to head<br/>Including 0014 and 0015"]
    backup --> migrate
    migrate --> release["Release migration lock"]
    release --> serve["Start Uvicorn / FastAPI"]
    serve --> probe["Probe new container's /health<br/>Up to 120 seconds"]
    probe -->|"Ready"| worker["Force-recreate background worker"]
    worker --> status["Show db, API and worker status"]
    backup -->|"Failure"| fail["Deployment fails<br/>Worker stays stopped"]
    migrate -->|"Failure"| fail
    probe -->|"Timeout or startup failure"| fail
```

The current Compose file is for development: API port `8001` maps to container
port `8000` by default, Uvicorn uses live reload, application sources are mounted,
and PostgreSQL's host port is bound to loopback. Database data and migration
backups persist outside the application containers. The worker uses the same
application build context and environment but bypasses the API migration
entrypoint. Starting Compose directly has weaker ordering: the worker can start
when the API container is merely running, then retries database errors while
migrations finish. The helper waits for the recreated API to serve first.

Migration files that have shipped are immutable. Schema fixes add new revisions;
deployment never downgrades or stamps a database. A health check on an older
already-running API is only liveness and does not establish migration currency.

## 12. Operations and verification

| Operation | Command from repository root |
| --- | --- |
| Build and start current backend | `./devops/deploy_backend.sh start` |
| Show containers | `./devops/deploy_backend.sh status` |
| Follow API and worker logs | `./devops/deploy_backend.sh logs` |
| Inspect queue counts and failed job IDs | `./devops/deploy_backend.sh queue-status` |

From `backend/`, reset a failed job only after correcting its cause:

```bash
docker compose exec -T api python -m app.prompt_jobs retry --word-id WORD_UUID
```

Status reports pending, in-flight, waiting-retry and failed counts, the oldest
pending timestamp, and at most 20 failed-job identifiers with safe metadata.
Retry resets only terminal failures, clearing their failure/lease fields and
attempt count. It cannot reset a pending or in-flight job.

Backend verification includes Ruff, mypy, pytest, temporary SQLite databases,
and CI API integration tests against isolated PostgreSQL schemas. PostgreSQL
tests exercise row-lock behavior that SQLite cannot reproduce. Deployment-helper
tests simulate Docker to check service ordering and failure handling without
restarting a live stack.

Source entry points: [application](../backend/app/main.py),
[API routes](../backend/app/api/routes/), [services](../backend/app/services/),
[database models](../backend/app/models/),
[Compose setup](../backend/docker-compose.yml), and
[deployment helper](../devops/deploy_backend.sh).
