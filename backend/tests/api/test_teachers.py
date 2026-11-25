"""Teacher transport remains authenticated and explicitly unimplemented."""


def test_teacher_options_are_empty(api):
    client, _, owner, _, _ = api
    response = client.get("/api/v1/teachers", headers=owner)
    assert response.status_code == 200
    assert response.json() == {"teachers": [], "selected_teacher_id": None}
    assert response.headers["cache-control"] == "no-store"


def test_teacher_selection_does_not_claim_a_save(api):
    client, _, owner, _, _ = api
    response = client.put(
        "/api/v1/teachers/selection", headers=owner, json={"teacher_id": "teacher-1"}
    )
    assert response.status_code == 501
    assert client.get("/api/v1/teachers", headers=owner).json() == {
        "teachers": [],
        "selected_teacher_id": None,
    }


def test_teacher_endpoints_require_authentication(api):
    client, *_ = api
    assert client.get("/api/v1/teachers").status_code == 401
    assert (
        client.put(
            "/api/v1/teachers/selection", json={"teacher_id": "teacher-1"}
        ).status_code
        == 401
    )


def test_teacher_selection_validates_transport(api):
    client, _, owner, _, _ = api
    for body in (
        {},
        {"teacher_id": ""},
        {"teacher_id": "x" * 129},
        {"teacher_id": "teacher-1", "user_id": "another-user"},
    ):
        assert (
            client.put(
                "/api/v1/teachers/selection", headers=owner, json=body
            ).status_code
            == 422
        )
