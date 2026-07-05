from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_analyze_returns_categories():
    response = client.post("/analyze", json={
        "github_url": "https://github.com/octocat/hello-world"
    })
    assert response.status_code == 200
    data = response.json()
    assert data["owner"] == "octocat"
    assert data["repo"] == "hello-world"
    assert "categories" in data
    assert isinstance(data["categories"], dict)
    for key in ("code", "config", "docs", "binary", "other"):
        assert key in data["categories"]
        assert isinstance(data["categories"][key], int)
    assert data["total_files"] == sum(data["categories"].values())


def test_analyze_bad_url():
    response = client.post("/analyze", json={
        "github_url": "not-a-url"
    })
    assert response.status_code == 400


def test_analyze_returns_chunks():
    response = client.post("/analyze", json={
        "github_url": "https://github.com/octocat/hello-world"
    })
    assert response.status_code == 200
    data = response.json()
    assert "chunks" in data
    assert isinstance(data["chunks"], list)
