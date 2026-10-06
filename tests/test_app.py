import pytest

from tests.conftest import BASE

CSP = (
    "default-src 'self'; media-src 'self' blob:; img-src 'self' data: blob:; "
    "style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'"
)


def test_health_reports_ok_and_version(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["version"] == "0.1.0"


@pytest.mark.parametrize("host", ["127.0.0.1:8417", "localhost:8417"])
def test_own_hosts_are_accepted(client, host):
    assert client.get("/api/health", headers={"host": host}).status_code == 200


@pytest.mark.parametrize(
    "host", ["evil.example:8417", "127.0.0.1:9999", "localhost", "0.0.0.0:8417"]
)
def test_foreign_host_gets_400(client, host):
    assert client.get("/api/health", headers={"host": host}).status_code == 400


def test_post_from_foreign_origin_gets_403(client):
    r = client.post("/api/health", headers={"origin": "https://evil.example"})
    assert r.status_code == 403


@pytest.mark.parametrize("origin", [BASE, "http://localhost:8417"])
def test_post_from_own_origin_passes_the_check(client, origin):
    # The route only allows GET, so getting past the middleware means 405.
    assert client.post("/api/health", headers={"origin": origin}).status_code == 405


def test_security_headers_on_every_response(client):
    for r in (
        client.get("/api/health"),
        client.get("/"),
        client.get("/api/health", headers={"host": "evil.example:8417"}),
    ):
        assert r.headers["content-security-policy"] == CSP
        assert r.headers["x-content-type-options"] == "nosniff"
        assert r.headers["referrer-policy"] == "no-referrer"
        assert "access-control-allow-origin" not in r.headers


def test_static_assets_and_spa_fallback(client):
    assert client.get("/assets/app.js").text == "console.log(1)"
    assert "<title>sukoon</title>" in client.get("/").text
    assert "<title>sukoon</title>" in client.get("/some/client/route").text


def test_static_serving_does_not_escape_the_bundle(client):
    for path in ("/../secret.txt", "/%2e%2e/secret.txt", "/assets/%2e%2e/%2e%2e/secret.txt"):
        assert "outside" not in client.get(path).text


def test_unknown_api_path_is_404(client):
    assert client.get("/api/nope").status_code == 404
