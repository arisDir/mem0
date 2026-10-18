from tests.conftest import _noop_session


def test_token_scheme_authenticates(raw_client, monkeypatch, fake_user):
    monkeypatch.setattr("auth._resolve_user_from_api_key", lambda key, db: fake_user)
    monkeypatch.setattr("auth.SessionLocal", _noop_session)

    resp = raw_client.get("/configure", headers={"Authorization": "Token m0sk_test"})

    assert resp.status_code == 200


def test_missing_auth_still_401(raw_client):
    assert raw_client.get("/configure").status_code == 401
