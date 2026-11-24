"""The connector categories (`categories.yaml`) and the check every authored server meets.

Each authored server names exactly one category under
`_meta["ai.nimblebrain/connector"].categories`, from the vocabulary, so a category filter
shows every connector once. Its `tags` are search keywords only, and none may be a word
the vocabulary forbids. A mirrored server's record is upstream's, so it carries neither
and is not checked.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from nimblebrain_catalog.build import BuildError, Entry

CONNECTOR_META_KEY = "ai.nimblebrain/connector"
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
# One category per connector today; the field is a list so this can grow without
# changing what readers parse.
MAX_CATEGORIES = 1


@dataclass(frozen=True)
class Vocabulary:
    categories: tuple[tuple[str, str], ...]  # (slug, label), in display order
    reserved: frozenset[str]
    forbidden_tags: frozenset[str]

    @property
    def slugs(self) -> frozenset[str]:
        return frozenset(slug for slug, _ in self.categories)


def parse_vocabulary(raw: object) -> Vocabulary:
    if not isinstance(raw, Mapping) or not isinstance(raw.get("categories"), list):
        raise BuildError("categories.yaml: must be a mapping with a `categories` list")
    unknown = set(raw) - {"categories", "reserved", "forbiddenTags"}
    if unknown:
        raise BuildError(f"categories.yaml: unknown fields {sorted(unknown)}")
    categories: list[tuple[str, str]] = []
    for i, item in enumerate(raw["categories"]):
        if not isinstance(item, Mapping) or set(item) != {"slug", "label"}:
            raise BuildError(f"categories.yaml: category {i} needs exactly a slug and a label")
        slug, label = item["slug"], item["label"]
        if not isinstance(slug, str) or not SLUG_RE.match(slug):
            raise BuildError(f"categories.yaml: category {i} slug {slug!r} is not a slug")
        if not isinstance(label, str) or not label.strip():
            raise BuildError(f"categories.yaml: category {slug} needs a label")
        if slug in {s for s, _ in categories}:
            raise BuildError(f"categories.yaml: category {slug} is listed twice")
        categories.append((slug, label.strip()))
    reserved = raw.get("reserved") or []
    if not isinstance(reserved, list) or not all(isinstance(s, str) for s in reserved):
        raise BuildError("categories.yaml: reserved must be a list of slugs")
    clash = set(reserved) & {s for s, _ in categories}
    if clash:
        raise BuildError(f"categories.yaml: {sorted(clash)} are both offered and reserved")
    forbidden = raw.get("forbiddenTags") or {}
    if not isinstance(forbidden, Mapping):
        raise BuildError("categories.yaml: forbiddenTags must map each tag to its reason")
    return Vocabulary(tuple(categories), frozenset(reserved), frozenset(forbidden))


def check_entries(entries: list[Entry], vocabulary: Vocabulary) -> None:
    """Fail on any authored server whose category or tags break the vocabulary."""
    for entry in entries:
        server = entry["server"]
        name = server["name"]
        meta: Mapping[str, Any] = (server.get("_meta") or {}).get(CONNECTOR_META_KEY) or {}
        categories = meta.get("categories")
        if not isinstance(categories, list) or not categories:
            raise BuildError(f"{name}: needs `categories` with one slug from categories.yaml")
        if len(categories) > MAX_CATEGORIES:
            raise BuildError(f"{name}: names {len(categories)} categories; one is allowed")
        for slug in categories:
            if slug not in vocabulary.slugs:
                hint = " (reserved, not yet offered)" if slug in vocabulary.reserved else ""
                raise BuildError(f"{name}: category {slug!r} is not in categories.yaml{hint}")
        tags = meta.get("tags", [])
        if not isinstance(tags, list) or not all(isinstance(t, str) and t for t in tags):
            raise BuildError(f"{name}: tags must be a list of words")
        banned = [t for t in tags if t.lower() in vocabulary.forbidden_tags]
        if banned:
            raise BuildError(f"{name}: tags {banned} are forbidden by categories.yaml")
        named = [t for t in tags if t.lower() in vocabulary.slugs]
        if named:
            raise BuildError(f"{name}: tags {named} repeat a category; tags are search keywords")
