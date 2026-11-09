from fastapi import FastAPI

app = FastAPI(title="English Vocabulary API", version="0.1.0")


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    """Report process health without requiring a database connection."""
    return {"status": "ok"}
