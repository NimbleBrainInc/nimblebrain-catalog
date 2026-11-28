from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path
from typing import Any

import pytest
import yaml

from nimblebrain_catalog.build import BuildError
from nimblebrain_catalog.plugins import (
    AI_CATALOG_KEY,
    MARKETPLACE_KEY,
    NIMBLEBRAIN_MARKETPLACE_KEY,
    PINNED_INDEX_PREFIX,
    ZERO_SETUP_CONNECTORS_KEY,
    Plugin,
    claude_mcp_config,
    distribution,
    icon_url,
    manifest,
    mcp_config,
    parse_plugins,
    plugin_files,
    portable,
)

DIRECT: dict[str, Any] = {
    "name": "com.vendor/mcp",
    "title": "Vendor",
    "description": "A vendor's server.",
    "version": "1.0.0",
    "websiteUrl": "https://vendor.com",
    "remotes": [{"type": "streamable-http", "url": "https://mcp.vendor.com/mcp"}],
    "_meta": {
        "ai.nimblebrain/connector": {"auth": "dcr", "category": "Docs & files", "tags": ["docs"]}
    },
}
BROKERED: dict[str, Any] = {
    "name": "com.vendor/brokered",
    "description": "A brokered toolkit.",
    "version": "0.1.0",
    "remotes": [{"type": "streamable-http", "url": "https://broker.example/mcp"}],
    "_meta": {"ai.nimblebrain/connector": {"auth": "composio", "composio": {"toolkit": "x"}}},
}
SERVERS: dict[str, dict[str, Any]] = {DIRECT["name"]: DIRECT, BROKERED["name"]: BROKERED}

SKILL = """---
name: {name}
description: How to use the vendor's tools.
metadata:
  nimblebrain:
    server: {server}
---

Use the tools.
"""


def write_skill(root: Path, plugin: str, name: str, server: str | None = None) -> None:
    folder = root / plugin / "skills" / name
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text(SKILL.format(name=name, server=server or plugin))


def test_parse_plugins() -> None:
    assert parse_plugins([{"name": "vendor", "server": "com.vendor/mcp"}]) == [
        Plugin("vendor", "com.vendor/mcp")
    ]


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ({"name": "vendor"}, "must be a list"),
        ([{"name": "Vendor", "server": "a/b"}], "not an Agent Plugins name"),
        ([{"name": "ven--dor", "server": "a/b"}], "not an Agent Plugins name"),
        ([{"name": "a.b/c", "server": "a/b"}], "not an Agent Plugins name"),
        ([{"name": "v", "server": "a/b"}, {"name": "v", "server": "a/c"}], "listed twice"),
        ([{"name": "v"}], "server must be"),
        ([{"name": "v", "server": "a/b", "tag": "x"}], "unknown fields"),
    ],
)
def test_parse_plugins_rejects(raw: object, message: str) -> None:
    with pytest.raises(BuildError, match=message):
        parse_plugins(raw)


def test_manifest_links_the_plugin_to_its_catalog_server() -> None:
    out = manifest(Plugin("vendor", DIRECT["name"]), DIRECT)
    assert out["name"] == "vendor"
    assert out["homepage"] == "https://vendor.com"
    assert out["keywords"] == ["docs"]
    assert out["extensions"] == {"ai.nimblebrain": {"servers": {"vendor": "com.vendor/mcp"}}}


def write_starters(root: Path, plugin: str, starters: object) -> None:
    (root / plugin).mkdir(parents=True, exist_ok=True)
    (root / plugin / "conversation-starters.yaml").write_text(yaml.safe_dump(starters))


def test_starters_ride_in_the_manifest_and_not_as_a_file(tmp_path: Path) -> None:
    write_starters(
        tmp_path,
        "vendor",
        [{"title": "Summarize my week", "text": "  Summarize what changed this week.  "}],
    )
    files = plugin_files(Plugin("vendor", DIRECT["name"]), DIRECT, tmp_path)
    assert "conversation-starters.yaml" not in files
    extension = json.loads(files["plugin.json"])["extensions"]["ai.nimblebrain"]
    assert extension == {
        "servers": {"vendor": "com.vendor/mcp"},
        "conversationStarters": [
            {"title": "Summarize my week", "text": "Summarize what changed this week."}
        ],
    }


def test_a_plugin_without_starters_has_none_in_its_manifest(tmp_path: Path) -> None:
    files = plugin_files(Plugin("vendor", DIRECT["name"]), DIRECT, tmp_path)
    extension = json.loads(files["plugin.json"])["extensions"]["ai.nimblebrain"]
    assert "conversationStarters" not in extension


@pytest.mark.parametrize(
    ("starters", "message"),
    [
        ([], "non-empty list"),
        ({"title": "x", "text": "y"}, "non-empty list"),
        ([{"title": f"t{i}", "text": "p"} for i in range(5)], "at most 4"),
        (["just a string"], "must be a mapping"),
        ([{"title": "t", "text": "p", "icon": "x"}], "unknown fields"),
        ([{"title": "", "text": "p"}], "needs a title"),
        ([{"title": "x" * 61, "text": "p"}], "needs a title"),
        ([{"title": "t", "text": "x" * 501}], "needs a text"),
        ([{"title": "t", "text": "a"}, {"title": "t", "text": "b"}], "appears twice"),
    ],
)
def test_starters_reject(tmp_path: Path, starters: object, message: str) -> None:
    write_starters(tmp_path, "vendor", starters)
    with pytest.raises(BuildError, match=message):
        plugin_files(Plugin("vendor", DIRECT["name"]), DIRECT, tmp_path)


def test_direct_server_gets_both_mcp_configs() -> None:
    plugin = Plugin("vendor", DIRECT["name"])
    config = mcp_config(plugin, DIRECT)
    assert config is not None
    assert config["mcpServers"] == {
        "vendor": {"type": "streamable-http", "url": "https://mcp.vendor.com/mcp"}
    }
    assert claude_mcp_config(plugin, DIRECT) == {
        "mcpServers": {"vendor": {"type": "http", "url": "https://mcp.vendor.com/mcp"}}
    }


def test_brokered_server_has_no_mcp_config(tmp_path: Path) -> None:
    plugin = Plugin("brokered", BROKERED["name"])
    assert mcp_config(plugin, BROKERED) is None
    assert set(plugin_files(plugin, BROKERED, tmp_path)) == {
        "plugin.json",
        "ai.nimblebrain/servers/brokered.json",
    }


def test_plugin_files_carry_its_skills(tmp_path: Path) -> None:
    write_skill(tmp_path, "vendor", "vendor")
    files = plugin_files(Plugin("vendor", DIRECT["name"]), DIRECT, tmp_path)
    assert set(files) == {
        "plugin.json",
        "mcp.json",
        ".mcp.json",
        "ai.nimblebrain/servers/vendor.json",
        "skills/vendor/SKILL.md",
    }


@pytest.mark.parametrize(
    ("folder", "name", "server", "message"),
    [
        ("vendor", "other", None, "name must equal its folder"),
        ("Vendor", "Vendor", None, "Agent Skills name"),
        ("vendor", "vendor", "elsewhere", "names server 'elsewhere'"),
    ],
)
def test_skill_rejects(
    tmp_path: Path, folder: str, name: str, server: str | None, message: str
) -> None:
    root = tmp_path / "vendor" / "skills" / folder
    root.mkdir(parents=True)
    (root / "SKILL.md").write_text(SKILL.format(name=name, server=server or "vendor"))
    with pytest.raises(BuildError, match=message):
        plugin_files(Plugin("vendor", DIRECT["name"]), DIRECT, tmp_path)


def test_skill_without_frontmatter_fails(tmp_path: Path) -> None:
    root = tmp_path / "vendor" / "skills" / "vendor"
    root.mkdir(parents=True)
    (root / "SKILL.md").write_text("Use the tools.\n")
    with pytest.raises(BuildError, match="no frontmatter"):
        plugin_files(Plugin("vendor", DIRECT["name"]), DIRECT, tmp_path)


PLUGINS = [Plugin("vendor", DIRECT["name"]), Plugin("brokered", BROKERED["name"])]


def test_distribution_serves_zips_marketplace_and_catalog(tmp_path: Path) -> None:
    write_skill(tmp_path, "vendor", "vendor")
    out = distribution(PLUGINS, SERVERS, tmp_path)

    digest = hashlib.sha256(out["plugins/vendor.zip"]).hexdigest()
    brokered = hashlib.sha256(out["plugins/brokered.zip"]).hexdigest()
    index = hashlib.sha256(out[NIMBLEBRAIN_MARKETPLACE_KEY]).hexdigest()
    assert set(out) == {
        "plugins/vendor.zip",
        f"plugins/vendor/{digest}.zip",
        "plugins/brokered.zip",
        f"plugins/brokered/{brokered}.zip",
        MARKETPLACE_KEY,
        NIMBLEBRAIN_MARKETPLACE_KEY,
        f"{PINNED_INDEX_PREFIX}{index}.json",
        ZERO_SETUP_CONNECTORS_KEY,
        AI_CATALOG_KEY,
    }
    assert out[f"plugins/vendor/{digest}.zip"] == out["plugins/vendor.zip"]
    assert out[f"{PINNED_INDEX_PREFIX}{index}.json"] == out[NIMBLEBRAIN_MARKETPLACE_KEY]
    names = zipfile.ZipFile(io.BytesIO(out["plugins/vendor.zip"])).namelist()
    assert sorted(names) == [
        ".mcp.json",
        "ai.nimblebrain/servers/vendor.json",
        "mcp.json",
        "plugin.json",
        "skills/vendor/SKILL.md",
    ]

    marketplace = json.loads(out[MARKETPLACE_KEY])
    assert marketplace["name"] == "nimblebrain"
    assert [p["name"] for p in marketplace["plugins"]] == ["vendor"]
    everything = json.loads(out[NIMBLEBRAIN_MARKETPLACE_KEY])
    assert [p["name"] for p in everything["plugins"]] == ["vendor", "brokered"]
    assert marketplace["plugins"][0] == {
        "name": "vendor",
        "source": {
            "source": "archive",
            "url": f"https://catalog.nimblebrain.ai/plugins/vendor/{digest}.zip",
            "sha256": digest,
        },
        "description": "A vendor's server.",
        "category": "Docs & files",
        "tags": ["docs"],
    }
    # A server with no category or tags gets neither field.
    assert "category" not in everything["plugins"][1] and "tags" not in everything["plugins"][1]

    catalog = json.loads(out[AI_CATALOG_KEY])
    assert catalog["specVersion"] == "0.9"
    entry = catalog["entries"][0]
    assert entry["identifier"] == "urn:air:nimblebrain.ai:vendor:plugin"
    assert entry["type"] == "application/agent-plugins+zip"
    assert entry["digest"] == f"sha256:{digest}"
    assert entry["url"] == f"https://catalog.nimblebrain.ai/plugins/vendor/{digest}.zip"
    assert entry["displayName"] == "Vendor"
    assert entry["extensions"] == {
        "ai.nimblebrain": {
            "category": "Docs & files",
            "servers": {"vendor": {"name": "com.vendor/mcp", "auth": "dcr"}},
        }
    }
    assert catalog["entries"][1]["extensions"] == {
        "ai.nimblebrain": {
            "nimblebrainOnly": True,
            "servers": {"brokered": {"name": "com.vendor/brokered", "auth": "composio"}},
        }
    }


STATIC: dict[str, Any] = {
    **DIRECT,
    "name": "com.vendor/static",
    "_meta": {
        "ai.nimblebrain/connector": {"auth": "static", "category": "Docs & files"},
        "ai.nimblebrain/host": {"placements": [{"slot": "sidebar"}]},
    },
}


@pytest.mark.parametrize(
    ("plugin", "server"),
    [("vendor", DIRECT), ("brokered", BROKERED), ("static", STATIC)],
)
def test_each_zip_carries_a_file_per_named_server_equal_to_its_detail(
    tmp_path: Path, plugin: str, server: dict[str, Any]
) -> None:
    out = distribution([Plugin(plugin, server["name"])], {server["name"]: server}, tmp_path)
    archive = zipfile.ZipFile(io.BytesIO(out[f"plugins/{plugin}.zip"]))
    named = json.loads(archive.read("plugin.json"))["extensions"]["ai.nimblebrain"]["servers"]
    carried = {
        n.removeprefix("ai.nimblebrain/servers/").removesuffix(".json"): json.loads(archive.read(n))
        for n in archive.namelist()
        if n.startswith("ai.nimblebrain/servers/")
    }
    # One file per key the manifest names, holding the ServerDetail it names, _meta and all.
    assert set(carried) == set(named) == {plugin}
    assert all(carried[k]["name"] == named[k] for k in named)
    assert carried[plugin] == server
    # The index entry stays marketplace fields only.
    (entry,) = json.loads(out[NIMBLEBRAIN_MARKETPLACE_KEY])["plugins"]
    assert set(entry) <= {"name", "source", "description", "category", "tags"}


def test_distribution_is_the_same_bytes_every_build(tmp_path: Path) -> None:
    write_skill(tmp_path, "vendor", "vendor")
    assert distribution(PLUGINS, SERVERS, tmp_path) == distribution(PLUGINS, SERVERS, tmp_path)


def test_distribution_rejects_a_plugin_whose_server_is_not_in_the_catalog(
    tmp_path: Path,
) -> None:
    with pytest.raises(BuildError, match="not in the catalog"):
        distribution([Plugin("gone", "com.gone/mcp")], SERVERS, tmp_path)


def test_distribution_rejects_an_unlisted_plugin_folder(tmp_path: Path) -> None:
    write_skill(tmp_path, "stray", "stray")
    with pytest.raises(BuildError, match="does not list"):
        distribution(PLUGINS, SERVERS, tmp_path)


@pytest.mark.parametrize(
    ("server", "expected"),
    [
        (DIRECT, True),
        (BROKERED, False),
        ({**DIRECT, "_meta": {"ai.nimblebrain/connector": {"auth": "static"}}}, False),
        ({k: v for k, v in DIRECT.items() if k != "_meta"}, True),
        ({**DIRECT, "remotes": []}, False),
    ],
)
def test_portable_means_any_host_installs_and_signs_in(
    server: dict[str, Any], expected: bool
) -> None:
    assert portable(server) is expected


def test_zero_setup_file_lists_only_portable_servers(tmp_path: Path) -> None:
    out = distribution(PLUGINS, SERVERS, tmp_path)
    body = out[ZERO_SETUP_CONNECTORS_KEY].decode()
    assert body.startswith("# The connectors a fresh NimbleBrain install starts with")
    assert yaml.safe_load(body) == {"servers": [DIRECT]}


MIRRORED: dict[str, Any] = {k: v for k, v in DIRECT.items() if k != "_meta"} | {
    "name": "com.vendor/mirrored"
}
ICON = "https://static.nimblebrain.ai/logos/vendor/light.svg"


@pytest.mark.parametrize(
    ("server", "expected_auth"),
    [
        (DIRECT, "dcr"),
        (STATIC, "static"),
        (BROKERED, "composio"),
        (MIRRORED, "none"),
    ],
)
def test_ai_catalog_entry_lists_each_server_its_manifest_names_with_its_auth(
    tmp_path: Path, server: dict[str, Any], expected_auth: str
) -> None:
    plugin = Plugin("p", server["name"])
    out = distribution([plugin], {server["name"]: server}, tmp_path)
    (entry,) = json.loads(out[AI_CATALOG_KEY])["entries"]
    listing = entry["extensions"]["ai.nimblebrain"]
    manifest_servers = json.loads(
        zipfile.ZipFile(io.BytesIO(out["plugins/p.zip"])).read("plugin.json")
    )["extensions"]["ai.nimblebrain"]["servers"]
    # The same keys and registry names the plugin's manifest states.
    assert {k: v["name"] for k, v in listing["servers"].items()} == manifest_servers
    assert listing["servers"]["p"]["auth"] == expected_auth
    # nimblebrainOnly is unchanged: set exactly when the plugin is not portable.
    assert listing.get("nimblebrainOnly", False) is not portable(server)


def test_ai_catalog_entry_carries_the_icon_and_category(tmp_path: Path) -> None:
    server: dict[str, Any] = {**DIRECT, "icons": [{"src": ICON, "sizes": ["any"]}]}
    out = distribution([Plugin("vendor", server["name"])], {server["name"]: server}, tmp_path)
    (entry,) = json.loads(out[AI_CATALOG_KEY])["entries"]
    listing = entry["extensions"]["ai.nimblebrain"]
    assert listing["iconUrl"] == ICON
    assert listing["category"] == "Docs & files"


def test_ai_catalog_entry_omits_icon_and_category_when_the_server_has_none(
    tmp_path: Path,
) -> None:
    out = distribution([Plugin("m", MIRRORED["name"])], {MIRRORED["name"]: MIRRORED}, tmp_path)
    (entry,) = json.loads(out[AI_CATALOG_KEY])["entries"]
    assert set(entry["extensions"]["ai.nimblebrain"]) == {"servers"}


@pytest.mark.parametrize(
    ("icons", "expected"),
    [
        ([], None),
        ([{"src": "https://a/light.svg"}], "https://a/light.svg"),
        (
            [{"src": "https://a/dark.svg", "theme": "dark"}, {"src": "https://a/light.svg"}],
            "https://a/light.svg",
        ),
        ([{"src": "https://a/dark.svg", "theme": "dark"}], "https://a/dark.svg"),
    ],
)
def test_icon_url_prefers_an_icon_not_meant_for_a_dark_theme(
    icons: list[dict[str, Any]], expected: str | None
) -> None:
    assert icon_url({**DIRECT, "icons": icons}) == expected
