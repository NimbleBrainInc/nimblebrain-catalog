"""The connector categories (`categories.yaml`) and the check every authored server meets.

Each authored server names exactly one category under
`_meta["ai.nimblebrain/connector"].category`, as the display text a reader shows, so no
reader depends on this vocabulary: it only keeps the catalog's own entries to one
consistent set. Its `tags` are search keywords only, and none may be a word the
vocabulary forbids. A mirrored server's record is upstream's, so it carries neither and
is not checked.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from nimblebrain_catalog.build import BuildError, Entry

CONNECTOR_META_KEY = "ai.nimblebrain/connector"


@dataclass(frozen=True)
class Vocabulary:
    categories: frozenset[str]
    reserved: frozenset[str]
    forbidden_tags: frozenset[str]


def _names(raw: object, field: str) -> list[str]:
    if not isinstance(raw, list) or not all(isinstance(n, str) and n.strip() for n in raw):
        raise BuildError(f"categories.yaml: {field} must be a list of names")
    names = [n.strip() for n in raw]
    if len(set(names)) != len(names):
        raise BuildError(f"categories.yaml: {field} lists a name twice")
    return names


def parse_vocabulary(raw: object) -> Vocabulary:
    if not isinstance(raw, Mapping) or "categories" not in raw:
        raise BuildError("categories.yaml: must be a mapping with a `categories` list")
    unknown = set(raw) - {"categories", "reserved", "forbiddenTags"}
    if unknown:
        raise BuildError(f"categories.yaml: unknown fields {sorted(unknown)}")
    categories = _names(raw["categories"], "categories")
    if not categories:
        raise BuildError("categories.yaml: categories must not be empty")
    reserved = _names(raw.get("reserved") or [], "reserved")
    clash = set(reserved) & set(categories)
    if clash:
        raise BuildError(f"categories.yaml: {sorted(clash)} are both offered and reserved")
    forbidden = raw.get("forbiddenTags") or {}
    if not isinstance(forbidden, Mapping):
        raise BuildError("categories.yaml: forbiddenTags must map each tag to its reason")
    return Vocabulary(
        frozenset(categories), frozenset(reserved), frozenset(t.lower() for t in forbidden)
    )


def check_entries(entries: list[Entry], vocabulary: Vocabulary) -> None:
    """Fail on any authored server whose category or tags break the vocabulary."""
    lowered = {c.lower() for c in vocabulary.categories}
    for entry in entries:
        server = entry["server"]
        name = server["name"]
        meta: Mapping[str, Any] = (server.get("_meta") or {}).get(CONNECTOR_META_KEY) or {}
        category = meta.get("category")
        if not isinstance(category, str) or not category:
            raise BuildError(f"{name}: needs a `category` from categories.yaml")
        if category not in vocabulary.categories:
            hint = " (reserved, not yet offered)" if category in vocabulary.reserved else ""
            raise BuildError(f"{name}: category {category!r} is not in categories.yaml{hint}")
        tags = meta.get("tags", [])
        if not isinstance(tags, list) or not all(isinstance(t, str) and t for t in tags):
            raise BuildError(f"{name}: tags must be a list of words")
        banned = [t for t in tags if t.lower() in vocabulary.forbidden_tags]
        if banned:
            raise BuildError(f"{name}: tags {banned} are forbidden by categories.yaml")
        named = [t for t in tags if t.lower() in lowered]
        if named:
            raise BuildError(f"{name}: tags {named} repeat a category; tags are search keywords")
