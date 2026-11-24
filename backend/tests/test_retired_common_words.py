"""The old client-graded learned endpoint stays retired."""

from fastapi.testclient import TestClient

from app.main import app


def test_old_common_learned_route_stays_removed() -> None:
    with TestClient(app) as client:
        assert (
            client.post(
                "/api/v1/common-words/00000000-0000-0000-0000-000000000001/learned",
                json={"selected_index": 0},
            ).status_code
            == 404
        )
