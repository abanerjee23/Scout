from unloop import create_app


def test_liveness_does_not_claim_provider_readiness():
    client = create_app({"TESTING": True}).test_client()
    result = client.get("/api/health")
    assert result.status_code == 200
    assert result.json == {
        "service": "unloop",
        "status": "ok",
        "phase": "scaffold",
        "persistence": False,
    }


def test_scaffold_does_not_expose_fixtures_or_writes():
    client = create_app({"TESTING": True}).test_client()
    for url in ("/api/reports", "/fixtures/meals/heldout/cases.json", "/.env"):
        assert client.get(url).status_code == 404
    assert client.post("/api/reports", json={"name": "Example"}).status_code == 404
