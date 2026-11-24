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
    "_meta": {"ai.nimblebrain/connector": {"auth": "dcr", "tags": ["docs"]}},
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
    assert set(plugin_files(plugin, BROKERED, tmp_path)) == {"plugin.json"}


def test_plugin_files_carry_its_skills(tmp_path: Path) -> None:
    write_skill(tmp_path, "vendor", "vendor")
    files = plugin_files(Plugin("vendor", DIRECT["name"]), DIRECT, tmp_path)
    assert set(files) == {"plugin.json", "mcp.json", ".mcp.json", "skills/vendor/SKILL.md"}


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
    assert sorted(names) == [".mcp.json", "mcp.json", "plugin.json", "skills/vendor/SKILL.md"]

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
    }

    catalog = json.loads(out[AI_CATALOG_KEY])
    assert catalog["specVersion"] == "0.9"
    entry = catalog["entries"][0]
    assert entry["identifier"] == "urn:air:nimblebrain.ai:vendor:plugin"
    assert entry["type"] == "application/agent-plugins+zip"
    assert entry["digest"] == f"sha256:{digest}"
    assert entry["url"] == f"https://catalog.nimblebrain.ai/plugins/vendor/{digest}.zip"
    assert entry["displayName"] == "Vendor"
    assert "extensions" not in entry
    assert catalog["entries"][1]["extensions"] == {"ai.nimblebrain": {"nimblebrainOnly": True}}


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
