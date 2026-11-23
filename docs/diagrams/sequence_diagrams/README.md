# Backend sequence diagrams

These 31 PlantUML diagrams describe the current backend source: all 18 application HTTP endpoints, shared authentication and review helpers, background jobs, provider adapters, and operator commands. Each source file lists the backend files it was derived from.

Open an SVG to view a diagram, or edit its .puml source. Alternative outcomes use alt fragments, optional behavior uses opt fragments, break fragments terminate the enclosing interaction on the stated condition, and ref fragments point to another numbered diagram in this folder.

Protected endpoint diagrams reference diagram 02 as their authentication precondition; their request arrow begins the endpoint-specific detail. Diagram 01 covers the separate Origin and rate-limit guard on authentication mutations. Invalid request input can return 422 before service execution. Known service failures are mapped by backend/app/api/errors.py; request sessions close on completion or error and roll back uncommitted work.

The set groups meaningful implemented branches rather than enumerating every possible interleaving or arbitrary infrastructure failure. It documents source behavior, not an inspected running deployment. Framework-generated OpenAPI and documentation routes are outside this application-route inventory.

## HTTP endpoint coverage

| Endpoint | Sequence source | Rendered diagram |
| --- | --- | --- |
| `DELETE /api/v1/account` | [09_account_delete](09_account_delete.puml) | [SVG](09_account_delete.svg) |
| `GET /api/v1/auth/me` | [07_auth_me](07_auth_me.puml) | [SVG](07_auth_me.svg) |
| `GET /api/v1/reviews/next` | [12_reviews_next](12_reviews_next.puml) | [SVG](12_reviews_next.svg) |
| `GET /api/v1/reviews/preparation` | [14_reviews_preparation](14_reviews_preparation.puml) | [SVG](14_reviews_preparation.svg) |
| `GET /api/v1/reviews/session` | [15_reviews_session](15_reviews_session.puml) | [SVG](15_reviews_session.svg) |
| `GET /api/v1/reviews/summary` | [13_reviews_summary](13_reviews_summary.puml) | [SVG](13_reviews_summary.svg) |
| `GET /api/v1/words/search` | [10_words_search](10_words_search.puml) | [SVG](10_words_search.svg) |
| `GET /health` | [30_health](30_health.puml) | [SVG](30_health.svg) |
| `PATCH /api/v1/account` | [08_account_update](08_account_update.puml) | [SVG](08_account_update.svg) |
| `POST /api/v1/auth/logout` | [06_auth_logout](06_auth_logout.puml) | [SVG](06_auth_logout.svg) |
| `POST /api/v1/auth/refresh` | [05_auth_refresh](05_auth_refresh.puml) | [SVG](05_auth_refresh.svg) |
| `POST /api/v1/auth/register` | [03_auth_register](03_auth_register.puml) | [SVG](03_auth_register.svg) |
| `POST /api/v1/auth/sign-in` | [04_auth_sign_in](04_auth_sign_in.puml) | [SVG](04_auth_sign_in.svg) |
| `POST /api/v1/common-words/batch` | [20_common_words_batch](20_common_words_batch.puml) | [SVG](20_common_words_batch.svg) |
| `POST /api/v1/common-words/{question_id}/learned` | [21_common_words_learned](21_common_words_learned.puml) | [SVG](21_common_words_learned.svg) |
| `POST /api/v1/reviews/{word_id}/answer` | [17_reviews_answer](17_reviews_answer.puml) | [SVG](17_reviews_answer.svg) |
| `POST /api/v1/reviews/{word_id}/choices` | [16_reviews_choices](16_reviews_choices.puml) | [SVG](16_reviews_choices.svg) |
| `POST /api/v1/words` | [11_words_create](11_words_create.puml) | [SVG](11_words_create.svg) |

## Complete diagram index

| Diagram | Sequence source | Rendered diagram |
| --- | --- | --- |
| 01. Authentication mutation guard and rate limit | [PlantUML](01_auth_request_guard.puml) | [SVG](01_auth_request_guard.svg) |
| 02. Protected request: bearer access authentication | [PlantUML](02_access_authentication.puml) | [SVG](02_access_authentication.svg) |
| 03. Register account and initial session | [PlantUML](03_auth_register.puml) | [SVG](03_auth_register.svg) |
| 04. Sign in with password | [PlantUML](04_auth_sign_in.puml) | [SVG](04_auth_sign_in.svg) |
| 05. Rotate access and refresh tokens | [PlantUML](05_auth_refresh.puml) | [SVG](05_auth_refresh.svg) |
| 06. Revoke session and clear refresh cookie | [PlantUML](06_auth_logout.puml) | [SVG](06_auth_logout.svg) |
| 07. Read current account identity | [PlantUML](07_auth_me.puml) | [SVG](07_auth_me.svg) |
| 08. Update account timezone | [PlantUML](08_account_update.puml) | [SVG](08_account_update.svg) |
| 09. Atomically erase account and owned data | [PlantUML](09_account_delete.puml) | [SVG](09_account_delete.svg) |
| 10. Search local dictionary and annotate saved words | [PlantUML](10_words_search.puml) | [SVG](10_words_search.svg) |
| 11. Save word and enqueue prompt generation | [PlantUML](11_words_create.puml) | [SVG](11_words_create.svg) |
| 12. Read next immediately due reviews | [PlantUML](12_reviews_next.puml) | [SVG](12_reviews_next.svg) |
| 13. Read review and learning totals | [PlantUML](13_reviews_summary.puml) | [SVG](13_reviews_summary.svg) |
| 14. Count selected reviews before starting | [PlantUML](14_reviews_preparation.puml) | [SVG](14_reviews_preparation.svg) |
| 15. Build typing or multiple-choice review session | [PlantUML](15_reviews_session.puml) | [SVG](15_reviews_session.svg) |
| 16. Switch an existing review to multiple choice | [PlantUML](16_reviews_choices.puml) | [SVG](16_reviews_choices.svg) |
| 17. Submit answer with idempotency and atomic scheduling | [PlantUML](17_reviews_answer.puml) | [SVG](17_reviews_answer.svg) |
| 18. Semantic topic selection shared by preparation and session | [PlantUML](18_topic_search.puml) | [SVG](18_topic_search.svg) |
| 19. Build four distinct multiple-choice options | [PlantUML](19_choice_generation.puml) | [SVG](19_choice_generation.svg) |
| 20. Serve Common-word bank and queue refill | [PlantUML](20_common_words_batch.puml) | [SVG](20_common_words_batch.svg) |
| 21. Mark a correctly answered Common word learned | [PlantUML](21_common_words_learned.puml) | [SVG](21_common_words_learned.svg) |
| 22. Durable saved-word prompt generation and retry | [PlantUML](22_prompt_generation_worker.puml) | [SVG](22_prompt_generation_worker.svg) |
| 23. Generate Common questions with global lock and durable lease | [PlantUML](23_common_words_worker.puml) | [SVG](23_common_words_worker.svg) |
| 24. Index saved words with restartable Ollama embeddings | [PlantUML](24_embedding_worker.puml) | [SVG](24_embedding_worker.svg) |
| 25. OpenRouter generation with capability fallback and validation | [PlantUML](25_openrouter_generation.puml) | [SVG](25_openrouter_generation.svg) |
| 26. Standalone Ollama review-sentence generation | [PlantUML](26_ollama_review_cli.puml) | [SVG](26_ollama_review_cli.svg) |
| 27. Startup migration with verified snapshot and forward-only upgrade | [PlantUML](27_forward_migrations.puml) | [SVG](27_forward_migrations.svg) |
| 28. Operator-only consistent user-data export | [PlantUML](28_user_export.puml) | [SVG](28_user_export.svg) |
| 29. Inspect prompt queue or explicitly retry terminal failure | [PlantUML](29_prompt_queue_management.puml) | [SVG](29_prompt_queue_management.svg) |
| 30. Unauthenticated process liveness check | [PlantUML](30_health.puml) | [SVG](30_health.svg) |
| 31. Background prompt-worker orchestration and recovery | [PlantUML](31_prompt_worker_loop.puml) | [SVG](31_prompt_worker_loop.svg) |

## Reading paths

- Authentication: 01–07; account changes and erasure: 08–09.
- Save and review words: 10–17; semantic topic selection and choice generation: 18–19.
- Common-word practice: 20–21; background generation and indexing: 22–24, 31.
- Provider integration and standalone review generation: 25–26.
- Forward migrations, user export, job administration and liveness: 27–30.

Important distinctions reflected in the diagrams: immediately due reviews differ from local-day review counts; Common-word learning differs from saving a review word; duplicate answer replay is checked before ticket expiry; workers generate outside database transactions and verify their leases before applying results. The Common generator holds a session advisory lock during its provider call. Deployment migrations only upgrade forward, and preview/production require a verified pre-migration snapshot.

## Render

From the repository root, with PlantUML installed:

```bash
plantuml -tsvg docs/diagrams/sequence_diagrams/*.puml
```

Or with a local PlantUML JAR:

```bash
java -jar /path/to/plantuml.jar -tsvg docs/diagrams/sequence_diagrams/*.puml
```

No external PlantUML includes are required. Keep .puml and .svg files together when updating these diagrams.
