from fastapi.testclient import TestClient
from unloop import create_app


def test_liveness_does_not_claim_provider_readiness():
    client = TestClient(create_app({"DATABASE_URL": None}))
    result = client.get("/api/health")
    assert result.status_code == 200
    assert result.json() == {
        "service": "unloop",
        "status": "ok",
    }


def test_app_does_not_expose_fixtures_or_unconfigured_storage():
    client = TestClient(create_app({"DATABASE_URL": None}))
    for url in ("/fixtures/meals/heldout/cases.json", "/.env"):
        assert client.get(url).status_code == 404
    assert client.get("/api/reports").status_code == 503
    assert client.get("/api/readiness").status_code == 503
