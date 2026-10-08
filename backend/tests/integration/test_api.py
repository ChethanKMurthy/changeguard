"""End-to-end tests of the HTTP API (FastAPI TestClient against a temporary database)."""

from __future__ import annotations

import io
import json
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from changeguard.api.app import create_app
from changeguard.config import Settings
from tests.conftest import zip_bytes

pytestmark = pytest.mark.integration

PATCH = """\
diff --git a/src/a.py b/src/a.py
--- a/src/a.py
+++ b/src/a.py
@@ -1,2 +1,2 @@
-def f(x):
-    return x
+def f(x, y):
+    return eval(x)
"""
BASE = {"src/a.py": "def f(x):\n    return x\n", "src/b.py": "from a import f\n\nf(1)\n"}


def _client(tmp_path: Path, **overrides: object) -> TestClient:
    params: dict[str, object] = {"rate_limit_per_minute": 50, **overrides}
    settings = Settings(database_path=tmp_path / "cg.db", **params)  # type: ignore[arg-type]
    return TestClient(create_app(settings))


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    with _client(tmp_path) as c:
        yield c


def _wait(client: TestClient, analysis_id: str, timeout: float = 30.0) -> dict:  # type: ignore[type-arg]
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        body = client.get(f"/api/v1/analyses/{analysis_id}").json()
        if body["status"] in ("completed", "failed"):
            return body
        time.sleep(0.05)
    raise AssertionError("analysis did not finish")


def test_health_meta_rules(client: TestClient) -> None:
    assert client.get("/api/v1/health").json()["status"] == "ok"
    meta = client.get("/api/v1/meta").json()
    assert meta["structural_languages"] == ["Python", "JavaScript", "TypeScript"]
    assert meta["ai"]["provider"] == "none" and meta["auth_required"] is False
    assert meta["stages"][0]["name"] == "ingest"
    rules = client.get("/api/v1/rules").json()
    assert any(r["id"] == "CG-API-001" for r in rules) and any(r["source"] == "ruff" for r in rules)


def test_full_upload_flow_with_events_and_exports(client: TestClient) -> None:
    response = client.post(
        "/api/v1/analyses",
        files={
            "patch": ("change.patch", PATCH, "text/x-diff"),
            "repository": ("repo.zip", zip_bytes(BASE), "application/zip"),
        },
        data={"title": "Upload test"},
    )
    assert response.status_code == 202, response.text
    created = response.json()
    assert created["status"] in ("queued", "running", "completed") and created["source"] == "upload"

    with client.stream("GET", created["links"]["events"]) as stream:
        events = [json.loads(line[6:]) for line in stream.iter_lines() if line.startswith("data: ")]
    assert events[0]["type"] == "started" and events[-1]["type"] == "completed"
    stage_names = [e["name"] for e in events if e["type"] == "stage" and e["status"] != "running"]
    assert stage_names[0] == "ingest" and stage_names[-1] == "report"

    detail = _wait(client, created["id"])
    assert detail["status"] == "completed" and detail["title"] == "Upload test"
    report = detail["report"]
    assert report["input"]["mode"] == "full_context"
    assert {f["rule_id"] for f in report["findings"]} >= {"CG-API-001", "RUFF-S307"}

    md = client.get(created["links"]["export_markdown"])
    assert md.status_code == 200 and md.headers["content-type"].startswith("text/markdown")
    sarif = client.get(created["links"]["export_sarif"]).json()
    assert sarif["runs"][0]["results"]
    assert client.get(created["links"]["export_json"]).json()["analysis_id"] == created["id"]

    listing = client.get("/api/v1/analyses").json()
    assert listing["total"] == 1 and listing["items"][0]["summary"]["findings_total"] == len(
        report["findings"]
    )
    assert client.delete(f"/api/v1/analyses/{created['id']}").status_code == 204
    assert client.get(f"/api/v1/analyses/{created['id']}").status_code == 404


def test_paste_diff_only_and_sample(client: TestClient) -> None:
    created = client.post("/api/v1/analyses", data={"patch_text": PATCH}).json()
    detail = _wait(client, created["id"])
    assert detail["source"] == "paste" and detail["report"]["input"]["mode"] == "diff_only"
    samples = client.get("/api/v1/samples").json()
    assert samples and all(s["synthetic"] for s in samples)
    sample = client.get(f"/api/v1/samples/{samples[0]['id']}").json()
    assert sample["patch"].startswith("diff --git")
    run = client.post(f"/api/v1/samples/{samples[0]['id']}/analyses").json()
    assert _wait(client, run["id"])["status"] == "completed"


@pytest.mark.parametrize(
    ("data", "files", "status", "code"),
    [
        ({"patch_text": "not a diff"}, None, 422, "malformed_patch"),
        ({}, None, 422, "invalid_input"),
        (
            {"patch_text": PATCH},
            {"repository": ("r.zip", b"garbage", "application/zip")},
            422,
            "invalid_archive",
        ),
        (
            {"patch_text": PATCH},
            {"coverage": ("c.xml", b"<html/>", "text/xml")},
            422,
            "invalid_coverage_report",
        ),
    ],
)
def test_input_errors_are_problem_details(
    client: TestClient, data: dict, files: dict | None, status: int, code: str
) -> None:  # type: ignore[type-arg]
    response = client.post("/api/v1/analyses", data=data, files=files)
    assert response.status_code == status
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == code


def test_size_limit(tmp_path: Path) -> None:
    with _client(tmp_path, max_patch_bytes=200) as c:
        response = c.post(
            "/api/v1/analyses",
            files={"patch": ("p.diff", io.BytesIO(PATCH.encode() * 5), "text/x-diff")},
        )
        assert response.status_code == 413 and response.json()["code"] == "payload_too_large"


def test_api_keys_and_rate_limit(tmp_path: Path) -> None:
    with _client(tmp_path, api_keys=[SecretStr("s3cret-key")], rate_limit_per_minute=2) as c:
        assert c.get("/api/v1/health").status_code == 200  # health stays public
        assert c.get("/api/v1/analyses").status_code == 401
        assert c.get("/api/v1/analyses", headers={"X-API-Key": "wrong"}).status_code == 401
        headers = {"Authorization": "Bearer s3cret-key"}
        assert c.get("/api/v1/analyses", headers=headers).status_code == 200
        codes = [
            c.post("/api/v1/analyses", data={"patch_text": PATCH}, headers=headers).status_code
            for _ in range(3)
        ]
        assert codes == [202, 202, 429]


def test_security_headers_and_unknown_ids(client: TestClient) -> None:
    response = client.get("/api/v1/analyses")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "no-store"
    assert "x-request-id" in response.headers
    assert client.get("/api/v1/analyses/../../etc/passwd").status_code == 404
    assert client.get("/api/v1/analyses/an_zzzz").status_code == 404


def test_workspaces_isolate_analyses(client: TestClient) -> None:
    a = {"X-ChangeGuard-Workspace": "a" * 24}
    b = {"X-ChangeGuard-Workspace": "b" * 24}
    created = client.post("/api/v1/analyses", data={"patch_text": PATCH}, headers=a)
    assert created.status_code == 202
    aid = created.json()["id"]
    assert _wait(client, aid)["status"] == "completed"  # unscoped operator access sees it

    assert client.get(f"/api/v1/analyses/{aid}", headers=a).status_code == 200
    for path in (
        f"/api/v1/analyses/{aid}",
        f"/api/v1/analyses/{aid}/export",
        f"/api/v1/analyses/{aid}/events",
    ):
        response = client.get(path, headers=b)
        assert response.status_code == 404 and response.json()["code"] == "not_found"
    assert client.delete(f"/api/v1/analyses/{aid}", headers=b).status_code == 404

    assert [item["id"] for item in client.get("/api/v1/analyses", headers=a).json()["items"]] == [
        aid
    ]
    assert client.get("/api/v1/analyses", headers=b).json()["total"] == 0
    assert aid in [item["id"] for item in client.get("/api/v1/analyses").json()["items"]]

    sample = client.post("/api/v1/samples/billing-refactor/analyses", headers=b).json()["id"]
    assert client.get(f"/api/v1/analyses/{sample}", headers=a).status_code == 404
    assert client.get(f"/api/v1/analyses/{sample}", headers=b).status_code == 200

    bad = client.get("/api/v1/analyses", headers={"X-ChangeGuard-Workspace": "../etc/passwd"})
    assert bad.status_code == 422 and bad.json()["code"] == "invalid_input"
    assert client.delete(f"/api/v1/analyses/{aid}", headers=a).status_code == 204


def test_rate_limit_is_per_forwarded_client_behind_a_trusted_proxy(tmp_path: Path) -> None:
    with _client(
        tmp_path,
        api_keys=[SecretStr("proxy-key")],
        rate_limit_per_minute=1,
        trust_proxy_headers=True,
    ) as c:

        def post(ip: str) -> int:
            headers = {"X-API-Key": "proxy-key", "X-Forwarded-For": ip}
            return c.post(
                "/api/v1/analyses", data={"patch_text": PATCH}, headers=headers
            ).status_code

        # Same key for everyone (as through the web app), separate buckets per client address.
        assert [post("203.0.113.7"), post("203.0.113.7"), post("198.51.100.4")] == [202, 429, 202]
