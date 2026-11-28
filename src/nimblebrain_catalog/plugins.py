"""The catalog's plugins: what a person installs (ADR-0068).

A plugin is one catalog server plus, when the catalog has one, the skill for
using it. `plugins.yaml` lists the plugins; `plugins/<name>/skills/` holds the
hand-written skills, and `plugins/<name>/conversation-starters.yaml` the
hand-written conversation starters, which a host offers a person who has the plugin
and does not know what to ask. Everything else about a plugin restates its server, so
it is generated here, never stored:

- `plugin.json` and `mcp.json`, the Agent Plugins 1.0 manifest and MCP config,
  read by any Agent Plugins host. NimbleBrain's link from the plugin to its
  catalog server, and its conversation starters, sit in `extensions["ai.nimblebrain"]`.
- `.mcp.json`, the same server in Claude Code's own plugin format.
- `ai.nimblebrain/servers/<key>.json` for each server the plugin names, where
  `<key>` is its key in `extensions["ai.nimblebrain"].servers`: the server's
  `ServerDetail` exactly as `/v0.1/servers` serves it, NimbleBrain `_meta`
  included. A reverse-domain folder is how Agent Plugins lets a host add files.
  It makes the pinned NimbleBrain index the runtime's whole catalog: one digest
  pins every plugin's servers, skills and starters.
- one zip per plugin, which is the plugin's install source: the catalog repo is
  private, so no host can clone it. It is served at `plugins/<name>.zip`, which
  moves with the plugin, and at `plugins/<name>/<sha256>.zip`, which never changes
  and is the URL every index names, so a host that pinned a digest can fetch it
  again after the plugin changes.
- one install index per kind of reader, in Claude Code's marketplace format
  (ADR-0068). A listing promises its reader the plugin installs and signs in:
  `marketplace.json` lists the portable plugins, for any host, and
  `nimblebrain/marketplace.json` lists every plugin, for the NimbleBrain runtime.
- `nimblebrain/marketplace/<sha256>.json`, the same bytes as
  `nimblebrain/marketplace.json` under their own digest. A runtime pins the
  catalog by that digest and reads the plugins it lists from there.
- `.well-known/ai-catalog.json`, the AI Catalog index for discovery. It lists
  every plugin and marks the ones only NimbleBrain can run.
- `nimblebrain/connectors.yaml`, the portable servers as a runtime catalog file
  (`{servers: [ServerDetail, ...]}`), which the runtime image ships as the catalog a
  fresh install starts with: every entry installs with nothing to configure.

A plugin is portable when every server it names is reached by URL and signs in
by dynamic client registration, or is mirrored from upstream with no NimbleBrain
auth stated. A Composio connector's remote is a placeholder only NimbleBrain
replaces, so its plugin has no MCP config; a server with `auth: static` needs an
operator's own OAuth app. Both make a plugin NimbleBrain-only.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from nimblebrain_catalog.build import BuildError

PLUGIN_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
MCP_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json"
EXTENSION = "ai.nimblebrain"
CONNECTOR_META_KEY = "ai.nimblebrain/connector"
# Where a plugin's zip carries each server it names, by its key in the manifest.
SERVER_FILE_DIR = f"{EXTENSION}/servers"

MARKETPLACE = "nimblebrain"
PUBLISHER = "nimblebrain.ai"
OWNER = {"name": "NimbleBrain", "url": "https://nimblebrain.ai"}
SITE_URL = "https://catalog.nimblebrain.ai"

MARKETPLACE_KEY = "marketplace.json"
NIMBLEBRAIN_MARKETPLACE_KEY = "nimblebrain/marketplace.json"
# Where each NimbleBrain index is kept under its own sha256, for a runtime that pins it.
PINNED_INDEX_PREFIX = "nimblebrain/marketplace/"
ZERO_SETUP_CONNECTORS_KEY = "nimblebrain/connectors.yaml"
ZERO_SETUP_HEADER = (
    "# The connectors a fresh NimbleBrain install starts with: the catalog's portable\n"
    "# servers, each of which installs with nothing to configure. Built by\n"
    "# nimblebrain-catalog from servers/ and published at catalog.nimblebrain.ai; the\n"
    "# runtime image ships it as its in-image catalog. Edit the catalog, not this file.\n"
)
# Auth kinds any host can complete on its own. None is a mirrored server whose
# entry states no NimbleBrain auth, which a host connects as its vendor publishes it.
PORTABLE_AUTH = {None, "dcr"}
AI_CATALOG_KEY = ".well-known/ai-catalog.json"
# The AI Catalog spec version this catalog follows, which the spec requires it to state.
# CI checks the built catalog against that version with ai-catalog-check.
AI_CATALOG_SPEC_VERSION = "0.9"

# Agent Plugins 1.0 §5.5.
PLUGIN_NAME_RE = re.compile(r"^(?!.*(?:--|\.\.))[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$")
# Agent Skills: lowercase letters, digits and single hyphens, matching its folder.
SKILL_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

# A conversation starter is one line a person reads and the text a host sends. A few
# per plugin, so a host can show them without choosing.
CONVERSATION_STARTERS_FILE = "conversation-starters.yaml"
MAX_CONVERSATION_STARTERS = 4
MAX_STARTER_TITLE = 60
MAX_STARTER_TEXT = 500

# Every zip entry gets this timestamp, so a plugin's bytes, and its digest, change
# only when its content does.
ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)


@dataclass(frozen=True)
class Plugin:
    name: str
    server: str


def parse_plugins(raw: object) -> list[Plugin]:
    if not isinstance(raw, list):
        raise BuildError("plugins.yaml must be a list of entries")
    plugins: list[Plugin] = []
    seen: set[str] = set()
    for i, item in enumerate(raw):
        if not isinstance(item, Mapping):
            raise BuildError(f"plugin {i}: must be a mapping")
        unknown = set(item) - {"name", "server"}
        if unknown:
            raise BuildError(f"plugin {i}: unknown fields {sorted(unknown)}")
        name, server = item.get("name"), item.get("server")
        if not isinstance(name, str) or len(name) > 64 or not PLUGIN_NAME_RE.match(name):
            raise BuildError(f"plugin {i}: name {name!r} is not an Agent Plugins name")
        if name in seen:
            raise BuildError(f"plugin {name}: listed twice")
        if not isinstance(server, str):
            raise BuildError(f"plugin {name}: server must be a registry name")
        seen.add(name)
        plugins.append(Plugin(name=name, server=server))
    return plugins


def connector(server: Mapping[str, Any]) -> Mapping[str, Any]:
    return (server.get("_meta") or {}).get(CONNECTOR_META_KEY) or {}


def portable(server: Mapping[str, Any]) -> bool:
    """Whether any host can install the server's plugin and sign in on its own."""
    return connector(server).get("auth") in PORTABLE_AUTH and _remote(server) is not None


def brokered(server: Mapping[str, Any]) -> bool:
    return connector(server).get("auth") == "composio"


def _remote(server: Mapping[str, Any]) -> Mapping[str, Any] | None:
    if brokered(server):
        return None
    remotes = server.get("remotes") or []
    preferred = [r for r in remotes if r.get("type") == "streamable-http"]
    return (preferred or remotes or [None])[0]


def named_servers(plugin: Plugin, server: Mapping[str, Any]) -> dict[str, str]:
    """The servers a plugin names, key → registry name, as its manifest states them."""
    return {plugin.name: server["name"]}


def manifest(
    plugin: Plugin,
    server: Mapping[str, Any],
    conversation_starters: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """The plugin's Agent Plugins `plugin.json`."""
    out: dict[str, Any] = {"$schema": PLUGIN_SCHEMA, "name": plugin.name}
    if server.get("description"):
        out["description"] = server["description"]
    out["author"] = dict(OWNER)
    if server.get("websiteUrl"):
        out["homepage"] = server["websiteUrl"]
    tags = connector(server).get("tags")
    if tags:
        out["keywords"] = list(tags)
    extension: dict[str, Any] = {"servers": named_servers(plugin, server)}
    if conversation_starters:
        extension["conversationStarters"] = conversation_starters
    out["extensions"] = {EXTENSION: extension}
    return out


def mcp_config(plugin: Plugin, server: Mapping[str, Any]) -> dict[str, Any] | None:
    """The plugin's Agent Plugins `mcp.json`, or None for a brokered server."""
    remote = _remote(server)
    if remote is None:
        return None
    entry = {"type": remote["type"], "url": remote["url"]}
    return {"$schema": MCP_SCHEMA, "mcpServers": {plugin.name: entry}}


def claude_mcp_config(plugin: Plugin, server: Mapping[str, Any]) -> dict[str, Any] | None:
    """The same server as Claude Code's `.mcp.json`, which names Streamable HTTP `http`."""
    remote = _remote(server)
    if remote is None:
        return None
    kind = "http" if remote["type"] == "streamable-http" else remote["type"]
    return {"mcpServers": {plugin.name: {"type": kind, "url": remote["url"]}}}


def _frontmatter(text: str) -> Mapping[str, Any]:
    if not text.startswith("---\n"):
        raise ValueError("no frontmatter")
    end = text.index("\n---\n", 4)
    data = yaml.safe_load(text[4:end])
    if not isinstance(data, Mapping):
        raise ValueError("frontmatter is not a mapping")
    return data


def read_skills(plugin: Plugin, root: Path) -> dict[str, bytes]:
    """The plugin's skill files, keyed by their path inside the plugin.

    Each `skills/<dir>/SKILL.md` is an Agent Skill whose `name` is its folder.
    A skill that names a server under `metadata.nimblebrain.server` must name
    one of the plugin's own.
    """
    skills_dir = root / plugin.name / "skills"
    if not skills_dir.is_dir():
        return {}
    files: dict[str, bytes] = {}
    for folder in sorted(p for p in skills_dir.iterdir() if p.is_dir()):
        where = f"plugin {plugin.name}: skill {folder.name}"
        skill = folder / "SKILL.md"
        if not skill.is_file():
            raise BuildError(f"{where}: has no SKILL.md")
        try:
            front = _frontmatter(skill.read_text())
        except ValueError as err:
            raise BuildError(f"{where}: {err}") from err
        if front.get("name") != folder.name or not SKILL_NAME_RE.match(folder.name):
            raise BuildError(f"{where}: name must equal its folder and be an Agent Skills name")
        if not isinstance(front.get("description"), str) or not front["description"]:
            raise BuildError(f"{where}: needs a description")
        bound = ((front.get("metadata") or {}).get("nimblebrain") or {}).get("server")
        if bound is not None and bound != plugin.name:
            raise BuildError(f"{where}: names server {bound!r}, not the plugin's {plugin.name!r}")
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                files[path.relative_to(root / plugin.name).as_posix()] = path.read_bytes()
    return files


def read_conversation_starters(plugin: Plugin, root: Path) -> list[dict[str, str]]:
    """The plugin's conversation starters from `plugins/<name>/conversation-starters.yaml`.

    The file is a list of `{title, text}`: `title` is what a person reads (a short
    action, such as "Summarize my unread email"), and `text` is what the host sends
    when they choose it. None when the plugin has no file.
    """
    path = root / plugin.name / CONVERSATION_STARTERS_FILE
    if not path.is_file():
        return []
    where = f"plugin {plugin.name}: {CONVERSATION_STARTERS_FILE}"
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, list) or not raw:
        raise BuildError(f"{where}: must be a non-empty list of starters")
    if len(raw) > MAX_CONVERSATION_STARTERS:
        raise BuildError(f"{where}: at most {MAX_CONVERSATION_STARTERS} starters")
    starters: list[dict[str, str]] = []
    seen: set[str] = set()
    for i, item in enumerate(raw):
        if not isinstance(item, Mapping):
            raise BuildError(f"{where}: starter {i} must be a mapping")
        unknown = set(item) - {"title", "text"}
        if unknown:
            raise BuildError(f"{where}: starter {i} has unknown fields {sorted(unknown)}")
        title, text = item.get("title"), item.get("text")
        if not isinstance(title, str) or not title.strip() or len(title) > MAX_STARTER_TITLE:
            raise BuildError(
                f"{where}: starter {i} needs a title of at most {MAX_STARTER_TITLE} characters"
            )
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_STARTER_TEXT:
            raise BuildError(
                f"{where}: starter {i} needs a text of at most {MAX_STARTER_TEXT} characters"
            )
        if title in seen:
            raise BuildError(f"{where}: title {title!r} appears twice")
        seen.add(title)
        starters.append({"title": title.strip(), "text": text.strip()})
    return starters


def _json(value: object) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode()


def plugin_files(plugin: Plugin, server: Mapping[str, Any], root: Path) -> dict[str, bytes]:
    """Every file of one plugin, keyed by its path inside the plugin."""
    files = {
        "plugin.json": _json(manifest(plugin, server, read_conversation_starters(plugin, root)))
    }
    # Keyed as the manifest keys it, so a reader of `servers` finds each server's file.
    for key in named_servers(plugin, server):
        files[f"{SERVER_FILE_DIR}/{key}.json"] = _json(server)
    mcp = mcp_config(plugin, server)
    if mcp is not None:
        files["mcp.json"] = _json(mcp)
        files[".mcp.json"] = _json(claude_mcp_config(plugin, server))
    files.update(read_skills(plugin, root))
    return files


def zip_bytes(files: Mapping[str, bytes]) -> bytes:
    """A zip of the files with the plugin root at the top, the same bytes every build."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(files):
            info = zipfile.ZipInfo(path, date_time=ZIP_EPOCH)
            info.external_attr = 0o644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, files[path])
    return buffer.getvalue()


def archive_key(name: str, digest: str) -> str:
    """The key that serves one version of a plugin's zip, by its sha256, for good."""
    return f"plugins/{name}/{digest}.zip"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _marketplace(description: str, entries: list[dict[str, Any]]) -> bytes:
    return _json(
        {"name": MARKETPLACE, "description": description, "owner": dict(OWNER), "plugins": entries}
    )


def distribution(
    plugins: list[Plugin], servers: Mapping[str, Mapping[str, Any]], root: Path
) -> dict[str, bytes]:
    """The catalog's plugin files: each plugin's zip, the indexes, and the zero-setup file."""
    listed = {p.name for p in root.iterdir() if p.is_dir()} if root.is_dir() else set()
    unlisted = listed - {p.name for p in plugins}
    if unlisted:
        raise BuildError(f"plugins/ has folders plugins.yaml does not list: {sorted(unlisted)}")

    out: dict[str, bytes] = {}
    entries: list[dict[str, Any]] = []
    portable_entries: list[dict[str, Any]] = []
    catalog: list[dict[str, Any]] = []
    for plugin in plugins:
        server = servers.get(plugin.server)
        if server is None:
            raise BuildError(f"plugin {plugin.name}: server {plugin.server} is not in the catalog")
        archive = zip_bytes(plugin_files(plugin, server, root))
        digest = _sha256(archive)
        out[f"plugins/{plugin.name}.zip"] = archive
        pinned = archive_key(plugin.name, digest)
        out[pinned] = archive
        url = f"{SITE_URL}/{pinned}"

        entry: dict[str, Any] = {
            "name": plugin.name,
            "source": {"source": "archive", "url": url, "sha256": digest},
        }
        if server.get("description"):
            entry["description"] = server["description"]
        # Claude Code's marketplace entry fields: a free-form `category` to organize the
        # catalog by, and `tags` for search. A reader shows them when present.
        if connector(server).get("category"):
            entry["category"] = connector(server)["category"]
        if connector(server).get("tags"):
            entry["tags"] = list(connector(server)["tags"])
        entries.append(entry)
        if portable(server):
            portable_entries.append(entry)

        item: dict[str, Any] = {
            "identifier": f"urn:air:{PUBLISHER}:{plugin.name}:plugin",
            "displayName": server.get("title") or plugin.name,
            "type": "application/agent-plugins+zip",
            "url": url,
            "digest": f"sha256:{digest}",
        }
        if server.get("description"):
            item["description"] = server["description"]
        tags = connector(server).get("tags")
        if tags:
            item["tags"] = list(tags)
        if not portable(server):
            item["extensions"] = {EXTENSION: {"nimblebrainOnly": True}}
        item["publisher"] = {
            "identifier": PUBLISHER,
            "displayName": OWNER["name"],
            "identityType": "dns",
        }
        catalog.append(item)

    out[MARKETPLACE_KEY] = _marketplace(
        "The connectors NimbleBrain offers that any agent can install and sign in to,"
        " each with the skill for using it.",
        portable_entries,
    )
    zero_setup = [servers[p.server] for p in plugins if portable(servers[p.server])]
    out[ZERO_SETUP_CONNECTORS_KEY] = (
        ZERO_SETUP_HEADER
        + yaml.safe_dump(
            {"servers": [dict(s) for s in zero_setup]},
            sort_keys=False,
            allow_unicode=True,
            width=100,
        )
    ).encode()
    index = _marketplace(
        "Every connector NimbleBrain offers, each with the skill for using it,"
        " for the NimbleBrain runtime.",
        entries,
    )
    out[NIMBLEBRAIN_MARKETPLACE_KEY] = index
    out[f"{PINNED_INDEX_PREFIX}{_sha256(index)}.json"] = index
    out[AI_CATALOG_KEY] = _json(
        {
            "specVersion": AI_CATALOG_SPEC_VERSION,
            "host": {
                "displayName": OWNER["name"],
                "identifier": PUBLISHER,
                "documentationUrl": "https://docs.nimblebrain.ai",
            },
            "entries": catalog,
        }
    )
    return out
