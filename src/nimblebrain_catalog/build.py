"""Turn the catalog's servers into the catalog's API objects.

A server reaches the catalog one of two ways. A member (`members.yaml`) names a
server published to the official registry, and its records are mirrored from
there unchanged, upstream's `_meta` kept as provenance. An authored server
(`servers/*.yaml`) is a `ServerDetail` the catalog publishes itself, for a
connector whose vendor has not published one under the name NimbleBrain installs
it by. Its NimbleBrain fields sit in the server's own `_meta`, under
`ai.nimblebrain/connector` and `ai.nimblebrain/host`, where the runtime reads them.

The output is a map from object key to JSON body. Keys are the API paths with the
leading slash dropped, and a server name's "/" stays a literal "/" in the key: the
host resolves a request for `ai.example%2Fserver` to the key `ai.example/server`,
so one object answers both the encoded and the raw form of a URL. A key such as
`v0.1/servers` and the keys under `v0.1/servers/` are separate objects, which is
why the catalog is served from an object store rather than a file tree.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

API_PREFIX = "v0.1"
OFFICIAL_META_KEY = "io.modelcontextprotocol.registry/official"

# Reverse-DNS namespace, one slash, server name: the official registry's name rule.
NAME_RE = re.compile(r"^[a-zA-Z0-9.-]+/[a-zA-Z0-9._-]+$")

Entry = dict[str, Any]
# Given a server name, returns every upstream entry ({"server", "_meta"}) for it.
FetchVersions = Callable[[str], list[Entry]]


class BuildError(Exception):
    """The member list or the upstream data cannot produce a valid catalog."""


@dataclass(frozen=True)
class Member:
    name: str


def parse_members(raw: object) -> list[Member]:
    if not isinstance(raw, list):
        raise BuildError("members.yaml must be a list of entries")
    members: list[Member] = []
    seen: set[str] = set()
    for i, item in enumerate(raw):
        if not isinstance(item, Mapping):
            raise BuildError(f"entry {i}: must be a mapping")
        unknown = set(item) - {"name"}
        if unknown:
            raise BuildError(f"entry {i}: unknown fields {sorted(unknown)}")
        name = item.get("name")
        if not isinstance(name, str) or not NAME_RE.match(name):
            raise BuildError(f"entry {i}: name {name!r} is not a registry name (namespace/server)")
        if name in seen:
            raise BuildError(f"entry {i}: {name} is listed twice")
        seen.add(name)
        members.append(Member(name=name))
    return members


REMOTE_TYPES = {"streamable-http", "sse"}


def parse_authored(source: str, raw: object) -> list[Entry]:
    """The `ServerDetail`s in one `servers/*.yaml` file, as API entries.

    The file is `{servers: [ServerDetail, ...]}`, the shape the runtime's catalog
    directory reads. Only remote servers are accepted: the runtime connects over
    the network and never runs a package.
    """
    if not isinstance(raw, Mapping) or not isinstance(raw.get("servers"), list):
        raise BuildError(f"{source}: must be a mapping with a `servers` list")
    entries: list[Entry] = []
    for i, server in enumerate(raw["servers"]):
        where = f"{source}: server {i}"
        if not isinstance(server, Mapping):
            raise BuildError(f"{where}: must be a mapping")
        name = server.get("name")
        if not isinstance(name, str) or not NAME_RE.match(name):
            raise BuildError(f"{where}: name {name!r} is not a registry name (namespace/server)")
        if not isinstance(server.get("version"), str):
            raise BuildError(f"{source}: {name}: version must be a string")
        remotes = server.get("remotes")
        if not isinstance(remotes, list) or not remotes:
            raise BuildError(f"{source}: {name}: needs at least one remote")
        for remote in remotes:
            if (
                not isinstance(remote, Mapping)
                or remote.get("type") not in REMOTE_TYPES
                or not isinstance(remote.get("url"), str)
            ):
                raise BuildError(f"{source}: {name}: each remote needs a type and a url")
        if "packages" in server:
            raise BuildError(f"{source}: {name}: an authored server is remote only")
        if not isinstance(server.get("_meta", {}), Mapping):
            raise BuildError(f"{source}: {name}: _meta must be a mapping")
        entries.append({"server": dict(server), "_meta": {}})
    return entries


def _official(entry: Entry) -> Mapping[str, Any]:
    return entry.get("_meta", {}).get(OFFICIAL_META_KEY, {})


def _check_entries(member: Member, entries: list[Entry]) -> Entry:
    """Validate one member's upstream entries and return the latest."""
    if not entries:
        raise BuildError(f"{member.name}: not found in the upstream registry")
    for entry in entries:
        server = entry.get("server")
        if not isinstance(server, Mapping) or server.get("name") != member.name:
            raise BuildError(f"{member.name}: upstream returned an entry for another server")
        if not isinstance(server.get("version"), str):
            raise BuildError(f"{member.name}: upstream entry has no version")
    latest = [e for e in entries if _official(e).get("isLatest") is True]
    if len(latest) != 1:
        raise BuildError(f"{member.name}: expected one latest version upstream, got {len(latest)}")
    return latest[0]


def _add(objects: dict[str, Any], name: str, entries: list[Entry], latest: Entry) -> None:
    base = f"{API_PREFIX}/servers/{name}/versions"
    objects[base] = {"servers": entries, "metadata": {"count": len(entries)}}
    for entry in entries:
        objects[f"{base}/{entry['server']['version']}"] = entry
    objects[f"{base}/latest"] = latest


def build(
    members: list[Member], fetch_versions: FetchVersions, authored: list[Entry] | None = None
) -> dict[str, Any]:
    """Return every API object of the catalog, keyed by its path."""
    objects: dict[str, Any] = {}
    listed: list[Entry] = []
    names: set[str] = set()

    for member in members:
        entries = fetch_versions(member.name)
        latest = _check_entries(member, entries)
        _add(objects, member.name, entries, latest)
        names.add(member.name)
        if _official(latest).get("status") != "deleted":
            listed.append(latest)

    # An authored server has one version: the one the catalog states.
    for entry in authored or []:
        name = entry["server"]["name"]
        if name in names:
            raise BuildError(f"{name}: listed more than once in the catalog")
        names.add(name)
        _add(objects, name, [entry], entry)
        listed.append(entry)

    # The list holds each server's latest version only. Upstream lists every version
    # unless asked for `?version=latest`; a static object cannot read the query, and
    # latest-only is what a client listing servers wants.
    objects[f"{API_PREFIX}/servers"] = {"servers": listed, "metadata": {"count": len(listed)}}
    return objects
