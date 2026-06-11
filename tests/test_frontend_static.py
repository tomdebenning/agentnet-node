"""Frontend static asset validation tests."""

from __future__ import annotations

from pathlib import Path

from gateway.frontend_static import validate_frontend_build


def test_validate_frontend_build_ok(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (assets / "app.js").write_text("console.log('ok')", encoding="utf-8")
    (dist / "index.html").write_text(
        '<script type="module" src="/assets/app.js"></script>',
        encoding="utf-8",
    )
    ok, missing = validate_frontend_build(dist)
    assert ok is True
    assert missing == []


def test_validate_frontend_build_missing_js(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text(
        '<script type="module" src="/assets/missing.js"></script>',
        encoding="utf-8",
    )
    ok, missing = validate_frontend_build(dist)
    assert ok is False
    assert missing == ["/assets/missing.js"]
