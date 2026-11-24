# OpenRouter review prompts

Generates a vocabulary fill-in-the-blank question from a word and meaning using
OpenRouter. HTTP requests use Python's standard library; the CLI uses python-dotenv for configuration.

## Backend flow

`POST /api/v1/words` commits the word, review state, a safe fallback prompt,
and a durable generation job together, then returns 201 without waiting for OpenRouter.
Known duplicates return 409. Run `python -m app.prompt_worker` separately (or use
Compose's `prompt-worker` service) to generate and store `words.review_prompt`.
Generation failures retain the word and retry automatically with backoff up to
`PROMPT_JOB_MAX_ATTEMPTS` (default 5). Terminal failures remain inspectable with
`python -m app.prompt_jobs status`; after fixing the cause, reset a failed job with
`python -m app.prompt_jobs retry --word-id UUID`. Jobs
survive restarts; expired claims are recovered and stale results are discarded.
The existing masked example/definition fallback remains usable until completion.

Review sessions and switching to multiple choice read the stored prompt; neither
calls OpenRouter. Prompts are redacted again before serialization as a defensive check.
The generated answer is never included in the review session response.

Configure `OPENROUTER_API_KEY`, `OPENROUTER_URL`, `OPENROUTER_MODEL`, and
`OPENROUTER_TIMEOUT_SECONDS` in the private backend environment. The URL defaults
to `https://openrouter.ai/api/v1`, the model to `openai/gpt-4o-mini`, and the timeout
to 120 seconds. Requests disable optional reasoning, cap output at 128 tokens,
and prefer providers with lower latency. Use a model that supports disabling reasoning;
models with mandatory reasoning may still think. The sentence prompt requests at most
9 words, including the target. The standalone Ollama generator also disables thinking
and caps output at 128 tokens.
Models that require reasoning are retried without the request to disable it;
models that support the control still receive `reasoning.enabled: false`.
Mandatory-reasoning retries allow 4,096 completion tokens for review sentences,
because reasoning shares the budget with the final JSON. Ordinary requests retain their smaller budgets. Truncated responses are
still rejected and never stored as review prompts.
Choose a text-generation model. If the provider rejects schema enforcement,
the client retries once without it and validates the returned JSON locally. Missing keys
fail generation jobs safely while the API and fallback prompts remain usable.
See `backend/.env.example`. Embeddings continue to use Ollama via `OLLAMA_URL`
and `EMBEDDING_MODEL`; no embedding reindex is needed for this change.

Run the normal deployment migration command from `backend`: `python -m app.migrate`.
Revision 0012 adds the stored prompt and backfills existing words with their
previous example/definition prompts, without network calls or changing schedules.
Revision 0013 adds the durable job queue. Old words keep their prompts; only newly added words use OpenRouter generation.
Direct database inserts that bypass the word service receive a blank placeholder.

## Shared-bank Common questions

`openrouter_common.py` generates questions for up to ten supplied bank entries.
The Common button triggers selection from the operator-populated shared bank before the LLM
call; generation never invents bank words. The structured JSON must contain
exactly one question, four distinct choices, and one integer answer index per
supplied bank ID. Partial, duplicate, extra-ID, oversized and truncated responses
are rejected as a whole. Capability fallback is bounded to three HTTP requests
within the remaining Common timeout. Provider error bodies are not exposed.

Questions and answer keys are persisted per user. Batch responses omit the keys;
only the answer endpoint returns feedback after server grading. No Common worker
or background refill queue is used. `COMMON_WORDS_TIMEOUT_SECONDS` is a total
batch-generation budget (default 240 seconds), independent of saved-word prompt
worker timeouts. Generation and failures are exercised with mocked providers in
`tests/test_openrouter_common.py` and `tests/api/test_common_words.py`.

## Operator bank generation

`python -m app.generate_common_words --count 1000` adds 1,000 **new** unique
Common vocabulary entries directly to SQL. Without `--count`, the command prompts
for a positive integer. `--batch-size` accepts 1 through 20 (default 20).
`openrouter_common_bank.py` asks the configured LLM for word content, meanings,
examples, parts of speech and nullable IPA; it does not generate quiz questions.

This uses private `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `OPENROUTER_URL`, and
`OPENROUTER_TIMEOUT_SECONDS` for each provider call. The same bounded transport
and capability fallback used by question generation validates completed JSON.
Every batch is validated before SQL insertion, and normalized duplicates are
ignored using a database conflict guard. Exclusions include the whole current
bank. There are no automatic content-generation jobs or startup LLM calls.

Completed batches persist even if a later provider call fails. The command exits
nonzero with saved/remaining counts for manual retry, and stops after three
consecutive batches add nothing. Migration 0022 removes the retired bundled seed;
apply migrations before running this command. Migrations never generate content.

## Direct testing

Set `OPENROUTER_API_KEY` in your private `backend/.env`, then from the repository
root run with the backend environment. The CLI loads that file regardless of the
current directory; exported shell variables take precedence:

```bash
backend/.venv/bin/python backend/app/llm/openrouter_review.py --model openai/gpt-4o-mini --word reluctant --meaning "unwilling or hesitant to do something"
```

Optional: `--url https://openrouter.ai/api/v1` and `--timeout 120` (seconds).
Model, URL, and timeout also accept their `OPENROUTER_*` environment variables.
Use a text-generation model, not an embedding model such as
`nvidia/nemotron-3-embed-1b:free`. App embeddings still use Ollama.
Keep the key in private configuration; do not pass it as a command-line argument.

Example output (actual wording varies):

```json
{
  "prompt_sentence": "She was _____ to leave her friends behind.",
  "answer": "reluctant"
}
```

OpenRouter generates a complete sentence, requesting a JSON schema when supported; the script validates
that the target occurs once as a standalone word/phrase and masks it locally.
Invalid output or connection failures produce an error and exit code 1.
Meaning, naturalness, and question ambiguity still need human review. The answer
is included for this local experiment; this output is not a backend API contract.

Run isolated tests without OpenRouter:

```bash
cd backend
python -m pytest tests/test_openrouter_review.py
```

API reference: https://openrouter.ai/docs/api/reference/overview
