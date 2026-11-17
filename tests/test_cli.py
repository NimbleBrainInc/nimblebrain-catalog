from __future__ import annotations

from pathlib import Path
from typing import Any

import boto3
import pytest

from nimblebrain_registry.build import BuildError
from nimblebrain_registry.cli import publish, read, write

OBJECTS = {
    "v0.1/servers": {"servers": [], "metadata": {"count": 0}},
    "v0.1/servers/ai.example/widget/versions": {"servers": []},
    "v0.1/servers/ai.example/widget/versions/latest": {"server": {}},
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
        existing = ["v0.1/servers/ai.example/gone/versions", "old-page.html"]
        return made.setdefault(service, FakeClient(existing))

    monkeypatch.setattr(boto3, "client", client)
    return made


def test_publish_uploads_with_content_types_and_invalidates_everything(
    tmp_path: Path, clients: dict[str, FakeClient]
) -> None:
    write(OBJECTS, tmp_path)
    publish(tmp_path, "bucket", "DIST")

    puts = clients["s3"].puts
    assert set(puts) == {*OBJECTS, "index.html", "errors/404.json"}
    assert puts["v0.1/servers"]["ContentType"] == "application/json"
    assert puts["index.html"]["ContentType"] == "text/html; charset=utf-8"
    assert puts["errors/404.json"]["ContentType"] == "application/problem+json"
    assert clients["s3"].deleted == ["v0.1/servers/ai.example/gone/versions"]
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
