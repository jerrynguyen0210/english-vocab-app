"""Helpers for API contract tests."""


def create(client, headers, word="Hello"):
    return client.post(
        "/api/v1/words",
        headers=headers,
        json={"word": word, "english_explanation": "A greeting"},
    )
