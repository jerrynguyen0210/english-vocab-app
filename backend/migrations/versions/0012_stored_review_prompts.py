"""Persist review prompts; backfill legacy hints without requiring Ollama."""

import re
import unicodedata

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def mask_target(text: str, word: str) -> str:
    """Mask every occurrence, including case/compatibility and spacing variants.

    Match substrings conservatively so compounds cannot disclose the answer.
    Keep an index map because case folding can expand characters (ß -> ss).
    """
    text = unicodedata.normalize("NFKC", text)
    folded = ""
    positions = []
    for index, char in enumerate(text):
        part = char.casefold()
        folded += part
        positions.extend([index] * len(part))
    target = " ".join(unicodedata.normalize("NFKC", word).casefold().split())
    if not target:
        return "_____"
    pattern = r"\s+".join(re.escape(part) for part in target.split())
    spans: list[tuple[int, int]] = []
    for match in re.finditer(pattern, folded):
        start, end = positions[match.start()], positions[match.end() - 1] + 1
        if spans and start <= spans[-1][1]:
            spans[-1] = (spans[-1][0], end)
        else:
            spans.append((start, end))
    for start, end in reversed(spans):
        text = text[:start] + "_____" + text[end:]
    return text


def prompt_sentence(example: str | None, explanation: str, word: str) -> str:
    """Prefer a saved cloze sentence; definitions keep older words reviewable.

    Only use examples that actually contain the target. A pre-existing blank or
    an unrelated example does not guarantee a usable question. Mask the entire
    fallback too, since the target can also occur in its connective wording.
    """
    if example and example.strip():
        original = unicodedata.normalize("NFKC", example.strip())
        masked = mask_target(original, word)
        if masked != original:
            return masked
    return mask_target(f"“_____” means: {explanation.strip()}", word)


def upgrade() -> None:
    op.add_column(
        "words",
        sa.Column("review_prompt", sa.Text(), nullable=False, server_default="_____"),
    )
    words = sa.table(
        "words",
        sa.column("id", sa.Uuid()),
        sa.column("word", sa.Text()),
        sa.column("english_explanation", sa.Text()),
        sa.column("example_sentence", sa.Text()),
        sa.column("review_prompt", sa.Text()),
    )
    connection = op.get_bind()
    # Keyset batches bound memory and close each read before updating its rows.
    last_id = None
    while True:
        query = sa.select(words).order_by(words.c.id).limit(500)
        if last_id is not None:
            query = query.where(words.c.id > last_id)
        rows = connection.execute(query).mappings().all()
        if not rows:
            break
        for row in rows:
            connection.execute(
                words.update()
                .where(words.c.id == row["id"])
                .values(
                    review_prompt=prompt_sentence(
                        row["example_sentence"], row["english_explanation"], row["word"]
                    )
                )
            )
        last_id = rows[-1]["id"]


def downgrade() -> None:
    raise RuntimeError("Deployment migrations are forward-only")
