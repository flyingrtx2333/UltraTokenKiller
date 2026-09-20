from pathlib import Path

from fastapi.testclient import TestClient


def test_packaged_dashboard_serves_brand_assets():
    from ultratokenkiller.service import app

    static = Path(__file__).parents[1] / "src" / "ultratokenkiller" / "static"
    assert (static / "brand" / "utk-icon.svg").is_file()
    assert (static / "brand" / "utk-lockup-light.svg").is_file()

    client = TestClient(app)
    dashboard = client.get("/dashboard")
    icon = client.get("/brand/utk-icon.svg")
    favicon_path = "/brand/utk-icon.svg"

    assert dashboard.status_code == 200
    assert favicon_path in dashboard.text
    assert icon.status_code == 200
    assert icon.headers["content-type"].startswith("image/svg+xml")
    assert "UltraTokenKiller" in icon.text
