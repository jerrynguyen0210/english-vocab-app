# Common-word architecture and workflow

Start with the [main architecture diagram](architecture_diagrams/common_words_architecture.puml).
It connects operator-driven vocabulary generation, the shared SQL bank, learner
practice, and explicit saving for scheduled recall. These diagrams describe the
current source and migration definitions; they do not assert that deployment or
operator generation has run.

| View | PlantUML source | What it explains |
| --- | --- | --- |
| Main architecture | [Common-word architecture](architecture_diagrams/common_words_architecture.puml) | Backend components, actors, SQL stores and the two LLM tasks |
| System context | [Backend context](context_diagrams/backend_context.puml) | Client, backend, operator, SQL and model-provider boundaries |
| Data relationships | [Database relationships](er_diagrams/database_relationships.puml) | Shared words, per-user learning, owned questions and saved recall |
| Operator sequence | [Generate N Common words](sequence_diagrams/32_operator_common_bank_generation.puml) | Count entry, exclusions, LLM validation, conflict handling and batch commits |
| Operator behavior | [Generation activity](behaviour_diagrams/common_bank_generation_activity.puml) | Success, failure, no-progress stopping and manual recovery |
| Learner batch | [Select unlearned words](sequence_diagrams/20_common_words_batch.puml) | Read pages of ten until ten unlearned words or end of bank |
| Question generation | [Generate practice questions](sequence_diagrams/23_common_words_worker.puml) | One question, four choices and one backend answer per selected word |
| Answer and Save | [Grade and offer recall](sequence_diagrams/21_common_words_learned.puml) | Correct-answer learning, retries, incorrect-answer feedback and explicit Save |
| Learner behavior | [Common review activity](behaviour_diagrams/common_words_review_activity.puml) | The complete learner interaction |

The operator runs `python -m app.generate_common_words --count N` from the configured
backend environment, or omits `--count` to enter the count interactively. N means
new unique entries to add, rather than a target total. The default generation batch
size is 20 and can be reduced with `--batch-size 1-20`. The configured LLM returns
word content, meanings, examples, parts of speech and nullable IPA; validated
batches go directly to SQL. No transaction remains open during provider calls.
Failures preserve earlier commits and report saved/remaining counts. Three
consecutive batches with no insertions stop the command.

A learner clicking Common requests a separate LLM task: generate quiz questions
for up to ten existing unlearned bank words. The bank does not have a fixed
1,000-word capacity. An empty bank returns unavailable; a populated bank with all
words learned returns completion. Correct answers record per-user learning.
Incorrect answers offer Save for recall; saving alone does not mark a word learned.

Apply migrations using the normal forward-only process before operator generation.
Revision 0022 removes the historical 1,000 seed entries and their Common questions
and progress. Operator-generated entries and independently saved recall words are
retained. The old JSON remains solely because immutable migration 0021 requires
it for historical replay. Migrations do not call the LLM.

Only PlantUML sources are updated. Existing SVGs may be stale and are intentionally
not regenerated. Syntax can be checked without rendering:

```bash
java -jar /path/to/plantuml.jar -checkonly docs/diagrams/architecture_diagrams/common_words_architecture.puml
```
