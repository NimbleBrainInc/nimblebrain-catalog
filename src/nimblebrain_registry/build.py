"""Turn the member list and the upstream registry's records into the registry's objects.

The output is a map from object key to JSON body. Keys are the API paths with the
leading slash dropped, and a server name's "/" stays a literal "/" in the key: the
host resolves a request for `ai.example%2Fserver` to the key `ai.example/server`,
so one object answers both the encoded and the raw form of a URL. A key such as
`v0.1/servers` and the keys under `v0.1/servers/` are separate objects, which is
why the registry is served from an object store rather than a file tree.

The upstream `server` block is copied unchanged, and upstream's own `_meta` is
kept as provenance. This registry adds one `_meta` entry of its own.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

API_PREFIX = "v0.1"
CATALOG_META_KEY = "ai.nimblebrain/catalog"
OFFICIAL_META_KEY = "io.modelcontextprotocol.registry/official"

# Reverse-DNS namespace, one slash, server name: the official registry's name rule.
NAME_RE = re.compile(r"^[a-zA-Z0-9.-]+/[a-zA-Z0-9._-]+$")

Entry = dict[str, Any]
# Given a server name, returns every upstream entry ({"server", "_meta"}) for it.
FetchVersions = Callable[[str], list[Entry]]


class BuildError(Exception):
    """The member list or the upstream data cannot produce a valid registry."""


@dataclass(frozen=True)
class Member:
    name: str
    included_in_platform: bool


def parse_members(raw: object) -> list[Member]:
    if not isinstance(raw, list):
        raise BuildError("members.yaml must be a list of entries")
    members: list[Member] = []
    seen: set[str] = set()
    for i, item in enumerate(raw):
        if not isinstance(item, Mapping):
            raise BuildError(f"entry {i}: must be a mapping")
        unknown = set(item) - {"name", "includedInPlatform"}
        if unknown:
            raise BuildError(f"entry {i}: unknown fields {sorted(unknown)}")
        name = item.get("name")
        if not isinstance(name, str) or not NAME_RE.match(name):
            raise BuildError(f"entry {i}: name {name!r} is not a registry name (namespace/server)")
        if name in seen:
            raise BuildError(f"entry {i}: {name} is listed twice")
        seen.add(name)
        included = item.get("includedInPlatform", False)
        if not isinstance(included, bool):
            raise BuildError(f"{name}: includedInPlatform must be true or false")
        members.append(Member(name=name, included_in_platform=included))
    return members


def catalog_meta(member: Member) -> dict[str, Any]:
    return {"includedInPlatform": member.included_in_platform}


def annotate(entry: Entry, member: Member) -> Entry:
    """Copy an upstream entry and add this registry's _meta beside upstream's."""
    return {
        "server": entry["server"],
        "_meta": {**entry.get("_meta", {}), CATALOG_META_KEY: catalog_meta(member)},
    }


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


def build(members: list[Member], fetch_versions: FetchVersions) -> dict[str, Any]:
    """Return every object of the registry, keyed by its path."""
    objects: dict[str, Any] = {}
    listed: list[Entry] = []

    for member in members:
        entries = fetch_versions(member.name)
        latest = _check_entries(member, entries)
        annotated = [annotate(e, member) for e in entries]

        base = f"{API_PREFIX}/servers/{member.name}/versions"
        objects[base] = {"servers": annotated, "metadata": {"count": len(annotated)}}
        for entry in annotated:
            objects[f"{base}/{entry['server']['version']}"] = entry
        objects[f"{base}/latest"] = annotate(latest, member)

        if _official(latest).get("status") != "deleted":
            listed.append(annotate(latest, member))

    # The list holds each server's latest version only. Upstream lists every version
    # unless asked for `?version=latest`; a static object cannot read the query, and
    # latest-only is what a client listing servers wants.
    objects[f"{API_PREFIX}/servers"] = {"servers": listed, "metadata": {"count": len(listed)}}
    return objects
