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
to 120 seconds. Choose a text-generation model. If the provider rejects schema enforcement,
the client retries once without it and validates the returned JSON locally. Missing keys
fail generation jobs safely while the API and fallback prompts remain usable.
See `backend/.env.example`. Embeddings continue to use Ollama via `OLLAMA_URL`
and `EMBEDDING_MODEL`; no embedding reindex is needed for this change.

Run the normal deployment migration command from `backend`: `python -m app.migrate`.
Revision 0012 adds the stored prompt and backfills existing words with their
previous example/definition prompts, without network calls or changing schedules.
Revision 0013 adds the durable job queue. Old words keep their prompts; only newly added words use OpenRouter generation.
Direct database inserts that bypass the word service receive a blank placeholder.

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
