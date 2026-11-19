from __future__ import annotations

import pytest

from nimblebrain_registry.build import (
    OFFICIAL_META_KEY,
    BuildError,
    Member,
    build,
    parse_authored,
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


MEMBER = Member(name=NAME)


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


def test_upstream_entry_is_mirrored_unchanged() -> None:
    upstream = [entry("1.0.0", latest=True)]
    latest = build([MEMBER], lambda _: upstream)[f"v0.1/servers/{NAME}/versions/latest"]

    assert latest == upstream[0]


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
    assert parse_members([{"name": NAME}]) == [Member(NAME)]
    assert parse_members([]) == []


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ({"name": NAME}, "must be a list"),
        ([{"name": "no-namespace"}], "not a registry name"),
        ([{"name": NAME}, {"name": NAME}], "listed twice"),
        ([{"name": NAME, "category": "x"}], "unknown fields"),
        ([{"name": NAME, "includedInPlatform": True}], "unknown fields"),
    ],
)
def test_parse_members_rejects(raw: object, message: str) -> None:
    with pytest.raises(BuildError, match=message):
        parse_members(raw)


AUTHORED = "com.vendor/mcp"


def authored(**server: object) -> dict:
    return {
        "name": AUTHORED,
        "version": "1.0.0",
        "description": "A vendor's server.",
        "remotes": [{"type": "streamable-http", "url": "https://mcp.vendor.com/mcp"}],
        "_meta": {"ai.nimblebrain/connector": {"auth": "dcr", "tags": ["docs"]}},
        **server,
    }


def test_authored_server_is_served_with_its_own_meta() -> None:
    entries = parse_authored("x.yaml", {"servers": [authored()]})
    objects = build([], lambda _: [], entries)

    base = f"v0.1/servers/{AUTHORED}/versions"
    assert set(objects) == {"v0.1/servers", base, f"{base}/latest", f"{base}/1.0.0"}
    latest = objects[f"{base}/latest"]
    assert latest["server"] == authored()
    assert latest["server"]["_meta"]["ai.nimblebrain/connector"]["auth"] == "dcr"
    assert objects["v0.1/servers"]["servers"] == [latest]


def test_members_and_authored_servers_list_together() -> None:
    entries = parse_authored("x.yaml", {"servers": [authored()]})
    objects = build([MEMBER], lambda _: [entry("1.0.0", latest=True)], entries)
    names = [s["server"]["name"] for s in objects["v0.1/servers"]["servers"]]
    assert names == [NAME, AUTHORED]


def test_a_name_listed_twice_fails() -> None:
    entries = parse_authored("x.yaml", {"servers": [authored(name=NAME)]})
    with pytest.raises(BuildError, match="more than once"):
        build([MEMBER], lambda _: [entry("1.0.0", latest=True)], entries)


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ([authored()], "`servers` list"),
        ({"servers": [authored(name="nope")]}, "not a registry name"),
        ({"servers": [authored(version=1)]}, "version must be a string"),
        ({"servers": [authored(remotes=[])]}, "at least one remote"),
        ({"servers": [authored(remotes=[{"type": "stdio", "url": "x"}])]}, "type and a url"),
        ({"servers": [authored(packages=[{"registryType": "npm"}])]}, "remote only"),
        ({"servers": [authored(_meta=[])]}, "_meta must be a mapping"),
    ],
)
def test_parse_authored_rejects(raw: object, message: str) -> None:
    with pytest.raises(BuildError, match=message):
        parse_authored("x.yaml", raw)
