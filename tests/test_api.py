from fastapi.testclient import TestClient

from app.api import app


def test_health():
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_query_endpoint(built):
    client = TestClient(app)
    resp = client.post("/query", json={"question": "Who hit the most home runs in 1998?"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["route"] == "sql"
    assert "request_id" in body


def test_query_validation():
    client = TestClient(app)
    resp = client.post("/query", json={"question": ""})
    assert resp.status_code == 422
