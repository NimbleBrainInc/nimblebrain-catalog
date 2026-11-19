from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import boto3
import pytest
import yaml

from nimblebrain_catalog import cli
from nimblebrain_catalog.build import OFFICIAL_META_KEY, BuildError
from nimblebrain_catalog.cli import main, publish, read, write

OBJECTS = {
    "v0.1/servers": {"servers": [], "metadata": {"count": 0}},
    "v0.1/servers/ai.example/widget/versions": {"servers": []},
    "v0.1/servers/ai.example/widget/versions/latest": {"server": {}},
}

FILES = {
    "plugins/widget.zip": b"PK\x05\x06" + b"\x00" * 18,
    "marketplace.json": b"{}\n",
    ".well-known/ai-catalog.json": b"{}\n",
    "nimblebrain/connectors.yaml": b"servers: []\n",
}


def test_write_then_read_round_trips_api_and_site(tmp_path: Path) -> None:
    write(OBJECTS, tmp_path)
    built = read(tmp_path)

    assert set(built) == {*OBJECTS, "index.html", "errors/404.json"}
    assert built["v0.1/servers"][1] == "application/json"
    assert built["index.html"][1] == "text/html; charset=utf-8"
    assert built["errors/404.json"][1] == "application/problem+json"


class FakeClient:
    """Records calls to the S3 and CloudFront methods `publish` uses."""

    def __init__(self, existing: list[str]) -> None:
        self.existing = existing
        self.puts: dict[str, dict[str, Any]] = {}
        self.deleted: list[str] = []
        self.invalidations: list[dict[str, Any]] = []

    def put_object(self, **kwargs: Any) -> None:
        self.puts[kwargs["Key"]] = kwargs

    def get_paginator(self, _name: str) -> FakeClient:
        return self

    def paginate(self, Bucket: str, Prefix: str) -> list[dict[str, Any]]:
        return [{"Contents": [{"Key": k} for k in self.existing if k.startswith(Prefix)]}]

    def delete_objects(self, Bucket: str, Delete: dict[str, Any]) -> None:
        self.deleted += [o["Key"] for o in Delete["Objects"]]

    def create_invalidation(self, **kwargs: Any) -> None:
        self.invalidations.append(kwargs)


@pytest.fixture
def clients(monkeypatch: pytest.MonkeyPatch) -> dict[str, FakeClient]:
    made: dict[str, FakeClient] = {}

    def client(service: str) -> FakeClient:
        existing = ["v0.1/servers/ai.example/gone/versions", "plugins/gone.zip", "old-page.html"]
        return made.setdefault(service, FakeClient(existing))

    monkeypatch.setattr(boto3, "client", client)
    return made


def test_publish_uploads_with_content_types_and_invalidates_everything(
    tmp_path: Path, clients: dict[str, FakeClient]
) -> None:
    write(OBJECTS, tmp_path, FILES)
    publish(tmp_path, "bucket", "DIST")

    puts = clients["s3"].puts
    assert set(puts) == {*OBJECTS, *FILES, "index.html", "errors/404.json"}
    assert puts["v0.1/servers"]["ContentType"] == "application/json"
    assert puts["index.html"]["ContentType"] == "text/html; charset=utf-8"
    assert puts["errors/404.json"]["ContentType"] == "application/problem+json"
    assert puts["plugins/widget.zip"]["ContentType"] == "application/zip"
    assert puts["marketplace.json"]["ContentType"] == "application/json"
    assert puts[".well-known/ai-catalog.json"]["ContentType"] == "application/json"
    assert puts["nimblebrain/connectors.yaml"]["ContentType"] == "application/yaml"
    assert puts["plugins/widget.zip"]["Body"] == FILES["plugins/widget.zip"]
    assert puts["nimblebrain/connectors.yaml"]["Body"] == FILES["nimblebrain/connectors.yaml"]
    assert clients["s3"].deleted == ["v0.1/servers/ai.example/gone/versions", "plugins/gone.zip"]
    (invalidation,) = clients["cloudfront"].invalidations
    assert invalidation["DistributionId"] == "DIST"
    assert invalidation["InvalidationBatch"]["Paths"] == {"Quantity": 1, "Items": ["/*"]}


def test_publish_rejects_an_incomplete_build_before_any_aws_call(
    tmp_path: Path, clients: dict[str, FakeClient]
) -> None:
    write(OBJECTS, tmp_path)
    (tmp_path / "site" / "index.html").unlink()

    with pytest.raises(BuildError, match="index.html"):
        publish(tmp_path, "bucket", "DIST")
    assert clients == {}


MIRRORED = "ai.example/mirrored"


def server(name: str) -> dict[str, Any]:
    return {
        "name": name,
        "version": "1.0.0",
        "remotes": [{"type": "streamable-http", "url": f"https://{name.split('/')[0]}/mcp"}],
    }


def upstream(name: str, _base: str) -> list[dict[str, Any]]:
    return [{"server": server(name), "_meta": {OFFICIAL_META_KEY: {"isLatest": True}}}]


def run_build(tmp_path: Path, files: dict[str, list[str]]) -> int:
    (tmp_path / "members.yaml").write_text(yaml.safe_dump([{"name": MIRRORED}]))
    (tmp_path / "plugins.yaml").write_text(
        yaml.safe_dump([{"name": "mirrored", "server": MIRRORED}])
    )
    folder = tmp_path / "servers"
    folder.mkdir()
    for file, names in files.items():
        (folder / file).write_text(yaml.safe_dump({"servers": [server(n) for n in names]}))
    return main(
        [
            "build",
            "--members",
            str(tmp_path / "members.yaml"),
            "--servers",
            str(folder),
            "--plugins",
            str(tmp_path / "plugins.yaml"),
            "--plugin-dir",
            str(tmp_path / "plugins"),
            "--out",
            str(tmp_path / "dist"),
        ]
    )


def test_build_lists_mirrored_and_every_authored_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "fetch_upstream_versions", upstream)

    assert run_build(tmp_path, {"b.yaml": ["ai.example/b"], "a.yaml": ["ai.example/a"]}) == 0

    listing = json.loads((tmp_path / "dist" / "api" / "v0.1" / "servers.json").read_text())
    assert [e["server"]["name"] for e in listing["servers"]] == [
        MIRRORED,
        "ai.example/a",
        "ai.example/b",
    ]
    site = tmp_path / "dist" / "site"
    assert (site / "plugins" / "mirrored.zip").is_file()
    marketplace = json.loads((site / "marketplace.json").read_text())
    assert [p["name"] for p in marketplace["plugins"]] == ["mirrored"]
    assert (site / ".well-known" / "ai-catalog.json").is_file()


def test_build_fails_on_a_name_authored_in_two_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "fetch_upstream_versions", upstream)

    assert run_build(tmp_path, {"a.yaml": ["ai.example/a"], "b.yaml": ["ai.example/a"]}) == 1
    assert "ai.example/a: listed more than once" in capsys.readouterr().err
    assert not (tmp_path / "dist").exists()
