# Ollama review prompts

Generates a vocabulary fill-in-the-blank question from a word and meaning using
local Ollama. The client uses Python's standard library and can still run directly.

## Backend flow

`POST /api/v1/words` commits the word, review state, a safe fallback prompt,
and a durable generation job together, then returns 201 without waiting for Ollama.
Known duplicates return 409. Run `python -m app.prompt_worker` separately (or use
Compose's `prompt-worker` service) to generate and store `words.review_prompt`.
Generation failures retain the word and retry automatically with backoff. Jobs
survive restarts; expired claims are recovered and stale results are discarded.
The existing masked example/definition fallback remains usable until completion.

Review sessions and switching to multiple choice read the stored prompt; neither
calls Ollama. Prompts are redacted again before serialization as a defensive check.
The generated answer is never included in the review session response.

Configure `OLLAMA_URL`, `OLLAMA_MODEL`, and `OLLAMA_TIMEOUT_SECONDS` in the backend
environment. Defaults match the existing LAN server: `http://192.168.0.108:11434`,
`translategemma:4b`, and 120 seconds. See `backend/.env.example`. In Docker, localhost
means the worker container; use a reachable LAN server address instead.

Run the normal deployment migration command from `backend`: `python -m app.migrate`.
Revision 0012 adds the stored prompt and backfills existing words with their
previous example/definition prompts, without network calls or changing schedules.
Revision 0013 adds the durable job queue. Old words keep their prompts; only newly added words use Ollama generation.
Direct database inserts that bypass the word service receive a blank placeholder.

## Direct testing

Start your installed Ollama server (`ollama serve`, unless already running).
Use `ollama list` to find an installed model, then from the repository root run:

```bash
python3 backend/app/llm/ollama_review.py --model YOUR_LOCAL_MODEL --word reluctant --meaning "unwilling or hesitant to do something"
```

Optional: `--url http://192.168.0.108:11434` and `--timeout 120` (seconds). The model
must already be available locally; the script does not download models.

Example output (actual wording varies):

```json
{
  "prompt_sentence": "She was _____ to leave her friends behind.",
  "answer": "reluctant"
}
```

Ollama generates a complete sentence using a JSON schema; the script validates
that the target occurs once as a standalone word/phrase and masks it locally.
Invalid output or connection failures produce an error and exit code 1.
Meaning, naturalness, and question ambiguity still need human review. The answer
is included for this local experiment; this output is not a backend API contract.

Run isolated tests without Ollama:

```bash
python3 backend/app/llm/test_ollama_review.py
```

API reference: https://docs.ollama.com/api/generate
