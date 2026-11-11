"""Backend liveness check, independent of authentication and database access."""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    """Report process health without requiring a database connection."""
    return {"status": "ok"}
