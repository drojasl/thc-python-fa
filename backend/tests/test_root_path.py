import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, settings
from app.main import create_app

ROOT_PATH = "/some-prefix"


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
        (ROOT_PATH, ROOT_PATH),
        ("thc2/", "/thc2"),
        ("//some///prefix///", "/some/prefix"),
    ],
)
def test_root_path_is_normalized(value: str, expected: str) -> None:
    assert _settings(value).ROOT_PATH == expected


def _create_app_with_frontend(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    root_path: str,
):
    frontend_dir = tmp_path / "frontend"
    frontend_dir.mkdir()
    (frontend_dir / "index.html").write_text("<html></html>")
    monkeypatch.setattr("app.main.FRONTEND_DIR", frontend_dir)
    monkeypatch.setattr(settings, "ROOT_PATH", root_path)
    return create_app()


def _request_through_stripping_proxy(
    client: TestClient,
    public_url: str,
    root_path: str,
):
    assert public_url.startswith(f"{root_path}/")
    backend_path = public_url.removeprefix(root_path)
    return client.get(backend_path)


def test_empty_root_path_preserves_existing_urls(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    unprefixed_app = _create_app_with_frontend(monkeypatch, tmp_path, "")
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
    tmp_path,
) -> None:
    prefixed_app = _create_app_with_frontend(monkeypatch, tmp_path, ROOT_PATH)

    assert prefixed_app.root_path == ROOT_PATH

    with TestClient(prefixed_app) as client:
        docs = _request_through_stripping_proxy(
            client,
            f"{ROOT_PATH}/docs",
            ROOT_PATH,
        )
        openapi = _request_through_stripping_proxy(
            client,
            f"{ROOT_PATH}/api/v1/openapi.json",
            ROOT_PATH,
        )
        health_check = _request_through_stripping_proxy(
            client,
            f"{ROOT_PATH}/api/v1/utils/health-check/",
            ROOT_PATH,
        )

    expected_openapi_url = f"{ROOT_PATH}/api/v1/openapi.json"
    assert docs.status_code == 200
    assert expected_openapi_url in docs.text
    assert f"{ROOT_PATH}{ROOT_PATH}/" not in docs.text
    assert openapi.status_code == 200
    assert openapi.json()["servers"][0]["url"] == ROOT_PATH
    assert health_check.status_code == 200
    assert health_check.json() is True
