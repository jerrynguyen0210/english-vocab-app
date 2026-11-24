# Backend sequence diagrams

These 32 PlantUML sequence diagrams describe backend flows, including operator-driven Common vocabulary generation (32) and learner practice (20, 21 and 23). Start with the [main architecture and workflow guide](../README.md). Common-specific sources reflect the implemented source; older shared diagrams may retain proposal annotations from the original design. Deployment state is not asserted.

Read the .puml sources for the latest Common design. Existing SVG files have not been regenerated and may show the retired Common implementation. Alternative outcomes use alt fragments, optional behavior uses opt fragments, break fragments terminate the enclosing interaction on the stated condition, and ref fragments point to another numbered diagram in this folder.

Protected endpoint diagrams reference diagram 02 as their authentication precondition; their request arrow begins the endpoint-specific detail. Diagram 01 covers the separate Origin and rate-limit guard on authentication mutations. Invalid request input can return 422 before service execution. Known service failures are mapped by backend/app/api/errors.py; request sessions close on completion or error and roll back uncommitted work.

The set groups meaningful implemented or explicitly proposed branches rather than enumerating every possible interleaving or arbitrary infrastructure failure. It documents source behavior and the labeled Common proposal, not an inspected running deployment. Framework-generated OpenAPI and documentation routes are outside this application-route inventory.

## HTTP endpoint coverage

| Endpoint | Sequence source | Rendered diagram |
| --- | --- | --- |
| `DELETE /api/v1/account` | [09_account_delete](09_account_delete.puml) | Not regenerated |
| `GET /api/v1/auth/me` | [07_auth_me](07_auth_me.puml) | [SVG](07_auth_me.svg) |
| `GET /api/v1/reviews/next` | [12_reviews_next](12_reviews_next.puml) | [SVG](12_reviews_next.svg) |
| `GET /api/v1/reviews/preparation` | [14_reviews_preparation](14_reviews_preparation.puml) | [SVG](14_reviews_preparation.svg) |
| `GET /api/v1/reviews/session` | [15_reviews_session](15_reviews_session.puml) | [SVG](15_reviews_session.svg) |
| `GET /api/v1/reviews/summary` | [13_reviews_summary](13_reviews_summary.puml) | Not regenerated |
| `GET /api/v1/words/search` | [10_words_search](10_words_search.puml) | [SVG](10_words_search.svg) |
| `GET /health` | [30_health](30_health.puml) | [SVG](30_health.svg) |
| `PATCH /api/v1/account` | [08_account_update](08_account_update.puml) | [SVG](08_account_update.svg) |
| `POST /api/v1/auth/logout` | [06_auth_logout](06_auth_logout.puml) | [SVG](06_auth_logout.svg) |
| `POST /api/v1/auth/refresh` | [05_auth_refresh](05_auth_refresh.puml) | [SVG](05_auth_refresh.svg) |
| `POST /api/v1/auth/register` | [03_auth_register](03_auth_register.puml) | [SVG](03_auth_register.svg) |
| `POST /api/v1/auth/sign-in` | [04_auth_sign_in](04_auth_sign_in.puml) | [SVG](04_auth_sign_in.svg) |
| `POST /api/v1/common-words/batch` | [20_common_words_batch](20_common_words_batch.puml) | Not regenerated |
| `POST /api/v1/common-words/questions/{question_id}/answer` | [21_common_words_learned](21_common_words_learned.puml) | Not regenerated |
| `POST /api/v1/reviews/{word_id}/answer` | [17_reviews_answer](17_reviews_answer.puml) | [SVG](17_reviews_answer.svg) |
| `POST /api/v1/reviews/{word_id}/choices` | [16_reviews_choices](16_reviews_choices.puml) | [SVG](16_reviews_choices.svg) |
| `POST /api/v1/words` | [11_words_create](11_words_create.puml) | Not regenerated |

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
| 09. Atomically erase account and owned data | [PlantUML](09_account_delete.puml) | Not regenerated |
| 10. Search local dictionary and annotate saved words | [PlantUML](10_words_search.puml) | [SVG](10_words_search.svg) |
| 11. Save word and enqueue prompt generation | [PlantUML](11_words_create.puml) | Not regenerated |
| 12. Read next immediately due reviews | [PlantUML](12_reviews_next.puml) | [SVG](12_reviews_next.svg) |
| 13. Read review and learning totals | [PlantUML](13_reviews_summary.puml) | Not regenerated |
| 14. Count selected reviews before starting | [PlantUML](14_reviews_preparation.puml) | [SVG](14_reviews_preparation.svg) |
| 15. Build typing or multiple-choice review session | [PlantUML](15_reviews_session.puml) | [SVG](15_reviews_session.svg) |
| 16. Switch an existing review to multiple choice | [PlantUML](16_reviews_choices.puml) | [SVG](16_reviews_choices.svg) |
| 17. Submit answer with idempotency and atomic scheduling | [PlantUML](17_reviews_answer.puml) | [SVG](17_reviews_answer.svg) |
| 18. Semantic topic selection shared by preparation and session | [PlantUML](18_topic_search.puml) | [SVG](18_topic_search.svg) |
| 19. Build four distinct multiple-choice options | [PlantUML](19_choice_generation.puml) | [SVG](19_choice_generation.svg) |
| 20. Select 10 unlearned words from shared bank | [PlantUML](20_common_words_batch.puml) | Not regenerated |
| 21. Grade answer, mark learned or offer Save | [PlantUML](21_common_words_learned.puml) | Not regenerated |
| 22. Durable saved-word prompt generation and retry | [PlantUML](22_prompt_generation_worker.puml) | [SVG](22_prompt_generation_worker.svg) |
| 23. Generate requested four-choice questions | [PlantUML](23_common_words_worker.puml) | Not regenerated |
| 24. Index saved words with restartable Ollama embeddings | [PlantUML](24_embedding_worker.puml) | [SVG](24_embedding_worker.svg) |
| 25. OpenRouter generation with capability fallback and validation | [PlantUML](25_openrouter_generation.puml) | Not regenerated |
| 26. Standalone Ollama review-sentence generation | [PlantUML](26_ollama_review_cli.puml) | [SVG](26_ollama_review_cli.svg) |
| 27. Startup migration with verified snapshot and forward-only upgrade | [PlantUML](27_forward_migrations.puml) | [SVG](27_forward_migrations.svg) |
| 28. Operator-only consistent user-data export | [PlantUML](28_user_export.puml) | [SVG](28_user_export.svg) |
| 29. Inspect prompt queue or explicitly retry terminal failure | [PlantUML](29_prompt_queue_management.puml) | Not regenerated |
| 30. Unauthenticated process liveness check | [PlantUML](30_health.puml) | [SVG](30_health.svg) |
| 31. Background prompt-worker orchestration and recovery | [PlantUML](31_prompt_worker_loop.puml) | Not regenerated |
| 32. Operator generates N new Common words into SQL | [PlantUML](32_operator_common_bank_generation.puml) | Not generated |

## Reading paths

- Authentication: 01–07; account changes and erasure: 08–09.
- Save and review words: 10–17; semantic topic selection and choice generation: 18–19.
- Operator Common vocabulary generation: [32](32_operator_common_bank_generation.puml) and [activity](../behaviour_diagrams/common_bank_generation_activity.puml).
- Common practice: 20–21 and 23; background saved-word generation and indexing: 22, 24, 31.
- Common review behavior: [activity diagram](../behaviour_diagrams/common_words_review_activity.puml).
- Provider integration and standalone review generation: 25–26.
- Forward migrations, user export, job administration and liveness: 27–30.

Important distinctions reflected in the diagrams: immediately due reviews differ from local-day review counts; Common-word learning differs from saving a review word; duplicate answer replay is checked before ticket expiry; workers generate outside database transactions and verify their leases before applying results. Common question generation runs on a batch request, outside database transactions, using selected bank words rather than generating new words. Deployment migrations only upgrade forward, and preview/production require a verified pre-migration snapshot.

## Common flow

Clicking Common on Add a word starts an authenticated batch request. The backend
reads the operator-populated shared bank in pages of 10, skips the user's learned IDs,
and continues until 10 distinct unlearned words are selected or the bank is exhausted.
The selected words and meanings go to the LLM with a review prompt requesting one
question, four distinct choices and exactly one answer per word. The backend validates
and persists the questions, keeps answer keys private, and returns the batch.

Correct answers atomically record per-user learning. Incorrect answers show feedback
and offer Save for recall; confirmation reuses the existing saved-word flow, while
declining leaves the word unlearned. Saving alone does not mark it learned. Already
saved words are not duplicated. A final batch may contain fewer than 10 words; an
empty selection from a populated bank means all bank words have been learned.
An empty bank returns unavailable (503) until the operator populates it. Generation and persistence
failures offer retry without losing existing progress.

The ER diagram includes `common_words`, `user_common_word_progress`, and owned
`common_practice_questions` for backend grading and answer replay. No Common refill
worker runs; file 23 retains its historical filename for existing references.
Operator generation (32) adds N new words in batches of up to 20, validates and
normalizes content, and commits each batch to SQL. The count is selected by the
operator; there is no fixed 1,000-word bank size. Failures preserve completed
commits and report the remaining count for manual retry.

## Render (optional; not performed for this update)

From the repository root, with PlantUML installed:

```bash
plantuml -tsvg docs/diagrams/sequence_diagrams/*.puml
```

Or with a local PlantUML JAR:

```bash
java -jar /path/to/plantuml.jar -tsvg docs/diagrams/sequence_diagrams/*.puml
```

No external PlantUML includes are required. SVG regeneration is intentionally deferred for this Common-only design update.
