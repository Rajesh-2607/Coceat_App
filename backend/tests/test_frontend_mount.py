"""The API can serve the built web app from the same origin (single-origin hosting)."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import _mount_frontend


def _app_with_build(build: Path) -> TestClient:
    app = FastAPI()

    @app.get("/api/ping")
    def ping() -> dict[str, bool]:
        return {"ok": True}

    _mount_frontend(app, build)
    return TestClient(app)


def test_serves_assets_and_falls_back_to_index_for_client_routes(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<title>app shell</title>")
    (tmp_path / "sw.js").write_text("worker")
    client = _app_with_build(tmp_path)

    assert client.get("/sw.js").text == "worker"
    assert "app shell" in client.get("/w/sell").text  # deep link survives a reload
    assert "app shell" in client.get("/").text


def test_api_routes_win_and_unknown_api_paths_stay_404(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<title>app shell</title>")
    client = _app_with_build(tmp_path)

    assert client.get("/api/ping").json() == {"ok": True}
    assert client.get("/api/does-not-exist").status_code == 404


def test_files_outside_the_build_folder_are_not_served(tmp_path: Path) -> None:
    build = tmp_path / "static"
    build.mkdir()
    (build / "index.html").write_text("<title>app shell</title>")
    (tmp_path / "secret.txt").write_text("do not serve")
    client = _app_with_build(build)

    response = client.get("/..%2Fsecret.txt")
    assert "do not serve" not in response.text
