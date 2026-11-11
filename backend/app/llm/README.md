# Standalone Ollama review experiment

Generates a vocabulary fill-in-the-blank question from a word and meaning using
local Ollama. Uses Python's standard library; no packages, backend configuration,
database, routes, or existing review services are needed or changed.

Start your installed Ollama server (`ollama serve`, unless already running).
Use `ollama list` to find an installed model, then from the repository root run:

```bash
python3 backend/app/llm/ollama_review.py --model YOUR_LOCAL_MODEL --word reluctant --meaning "unwilling or hesitant to do something"
```

Optional: `--url http://localhost:11434` and `--timeout 120` (seconds). The model
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
