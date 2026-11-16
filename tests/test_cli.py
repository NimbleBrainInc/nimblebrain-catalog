from __future__ import annotations

from pathlib import Path

from nimblebrain_registry.cli import read, write


def test_write_then_read_round_trips_keys_that_are_also_folders(tmp_path: Path) -> None:
    objects = {
        "v0.1/servers": {"servers": []},
        "v0.1/servers/ai.example/widget/versions": {"servers": []},
        "v0.1/servers/ai.example/widget/versions/latest": {"server": {}},
    }
    write(objects, tmp_path)
    assert set(read(tmp_path)) == set(objects)
