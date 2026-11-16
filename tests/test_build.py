from __future__ import annotations

import pytest

from nimblebrain_registry.build import (
    CATALOG_META_KEY,
    OFFICIAL_META_KEY,
    BuildError,
    Member,
    build,
    parse_members,
)

NAME = "ai.example/widget"


def entry(version: str, *, latest: bool = False, status: str = "active") -> dict:
    return {
        "server": {
            "name": NAME,
            "version": version,
            "description": "A widget.",
            "remotes": [{"type": "streamable-http", "url": "https://mcp.example.ai/mcp"}],
        },
        "_meta": {OFFICIAL_META_KEY: {"status": status, "isLatest": latest}},
    }


MEMBER = Member(name=NAME, included_in_platform=True)


def test_builds_list_versions_and_each_version() -> None:
    upstream = [entry("0.1.0"), entry("0.2.0", latest=True)]
    objects = build([MEMBER], lambda _: upstream)

    assert set(objects) == {
        "v0.1/servers",
        f"v0.1/servers/{NAME}/versions",
        f"v0.1/servers/{NAME}/versions/latest",
        f"v0.1/servers/{NAME}/versions/0.1.0",
        f"v0.1/servers/{NAME}/versions/0.2.0",
    }
    listing = objects["v0.1/servers"]
    assert listing["metadata"] == {"count": 1}
    assert [s["server"]["version"] for s in listing["servers"]] == ["0.2.0"]
    assert objects[f"v0.1/servers/{NAME}/versions"]["metadata"] == {"count": 2}
    assert objects[f"v0.1/servers/{NAME}/versions/latest"]["server"]["version"] == "0.2.0"


def test_server_block_is_unchanged_and_meta_is_added_beside_upstream() -> None:
    upstream = [entry("1.0.0", latest=True)]
    latest = build([MEMBER], lambda _: upstream)[f"v0.1/servers/{NAME}/versions/latest"]

    assert latest["server"] == upstream[0]["server"]
    assert latest["_meta"][OFFICIAL_META_KEY] == upstream[0]["_meta"][OFFICIAL_META_KEY]
    assert latest["_meta"][CATALOG_META_KEY] == {
        "includedInPlatform": True,
        "catalogUrl": "https://nimblebrain.ai/registry/widget",
    }


def test_deleted_server_leaves_the_list_but_keeps_its_versions() -> None:
    objects = build([MEMBER], lambda _: [entry("1.0.0", latest=True, status="deleted")])
    assert objects["v0.1/servers"]["servers"] == []
    assert f"v0.1/servers/{NAME}/versions/1.0.0" in objects


def test_member_missing_upstream_fails() -> None:
    with pytest.raises(BuildError, match="not found"):
        build([MEMBER], lambda _: [])


def test_no_single_latest_fails() -> None:
    with pytest.raises(BuildError, match="one latest"):
        build([MEMBER], lambda _: [entry("1.0.0"), entry("1.1.0")])


def test_entry_for_another_server_fails() -> None:
    other = entry("1.0.0", latest=True)
    other["server"]["name"] = "ai.example/other"
    with pytest.raises(BuildError, match="another server"):
        build([MEMBER], lambda _: [other])


def test_parse_members() -> None:
    assert parse_members([{"name": NAME}]) == [Member(NAME, included_in_platform=False)]
    assert parse_members([{"name": NAME, "includedInPlatform": True}])[0].included_in_platform


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ({"name": NAME}, "must be a list"),
        ([{"name": "no-namespace"}], "not a registry name"),
        ([{"name": NAME}, {"name": NAME}], "listed twice"),
        ([{"name": NAME, "category": "x"}], "unknown fields"),
        ([{"name": NAME, "includedInPlatform": "yes"}], "true or false"),
    ],
)
def test_parse_members_rejects(raw: object, message: str) -> None:
    with pytest.raises(BuildError, match=message):
        parse_members(raw)
