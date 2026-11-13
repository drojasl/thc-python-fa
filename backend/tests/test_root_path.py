import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, settings
from app.main import create_app


def _settings(root_path: str = "") -> Settings:
    return Settings(
        _env_file=None,
        ROOT_PATH=root_path,
        PROJECT_NAME="Test project",
        SECRET_KEY="test-secret",
        DATABASE_URL="postgresql://postgres:test-password@localhost:5432/test",
        FIRST_SUPERUSER="admin@example.com",
        FIRST_SUPERUSER_PASSWORD="test-password",
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("", ""),
        ("/thc1", "/thc1"),
        ("thc2/", "/thc2"),
        ("//some///prefix///", "/some/prefix"),
    ],
)
def test_root_path_is_normalized(value: str, expected: str) -> None:
    assert _settings(value).ROOT_PATH == expected


def test_empty_root_path_preserves_existing_urls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "ROOT_PATH", "")
    unprefixed_app = create_app()
    assert unprefixed_app.root_path == ""

    with TestClient(unprefixed_app) as client:
        docs = client.get("/docs")
        openapi = client.get("/api/v1/openapi.json")
        health_check = client.get("/api/v1/utils/health-check/")

    assert docs.status_code == 200
    assert "/api/v1/openapi.json" in docs.text
    assert openapi.status_code == 200
    assert health_check.status_code == 200
    assert health_check.json() is True


def test_prefixed_root_path_routes_and_swagger_urls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "ROOT_PATH", "/thc1")
    prefixed_app = create_app()

    assert prefixed_app.root_path == "/thc1"

    with TestClient(prefixed_app) as client:
        docs = client.get("/docs")
        openapi = client.get("/api/v1/openapi.json")
        health_check = client.get("/api/v1/utils/health-check/")
        frontend = client.get("/")

    expected_openapi_url = "/thc1/api/v1/openapi.json"
    assert docs.status_code == 200
    assert expected_openapi_url in docs.text
    assert "/thc1/thc1/" not in docs.text
    assert openapi.status_code == 200
    assert openapi.json()["servers"][0]["url"] == "/thc1"
    assert health_check.status_code == 200
    assert health_check.json() is True
    assert frontend.status_code == 200
    assert "./assets/" in frontend.text
