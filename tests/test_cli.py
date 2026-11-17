from __future__ import annotations

from pathlib import Path

from nimblebrain_registry.cli import read, write


def test_write_then_read_round_trips_api_and_site(tmp_path: Path) -> None:
    objects = {
        "v0.1/servers": {"servers": [], "metadata": {"count": 0}},
        "v0.1/servers/ai.example/widget/versions": {"servers": []},
        "v0.1/servers/ai.example/widget/versions/latest": {"server": {}},
    }
    write(objects, tmp_path)
    built = read(tmp_path)

    assert set(built) == {*objects, "index.html", "errors/404.json"}
    assert built["v0.1/servers"][1] == "application/json"
    assert built["index.html"][1] == "text/html; charset=utf-8"
    assert built["errors/404.json"][1] == "application/problem+json"
