# Historical Common bank snapshot

`0021_common_words.json` and `WORDNET-LICENSE.txt` are historical migration
resources. Shipped migration 0021 references this exact 1,000-entry snapshot,
so these files must remain available for migration replay. They are not the
source for the active bank after migration 0022.

Revision 0022 removes those exact seed IDs and their dependent Common questions
and learning progress. It preserves operator-generated bank entries, users, and
independently saved recall words. Fresh databases upgraded to head have an empty
bank. Do not edit shipped revisions, downgrade, or stamp deployed databases.

Operators now populate SQL explicitly with the configured LLM:

```bash
cd backend
.venv/bin/python -m app.generate_common_words --count 1000
```

Omit `--count` to enter any positive count interactively. Generated vocabulary is
stored directly in `common_words`, not in a source-controlled content file.

The historical meanings and examples were taken from WordNet 3.0 and retain the
Princeton license reproduced in `WORDNET-LICENSE.txt`. Its IDs use UUIDv5 in the
URL namespace with `wordrecall/common-bank/0021/` plus the normalized word.
LLM-generated bank IDs use the separate `wordrecall/common-bank/llm/` prefix.
