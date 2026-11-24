from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from nimblebrain_catalog.build import BuildError
from nimblebrain_catalog.categories import check_entries, parse_vocabulary

VOCAB = parse_vocabulary(
    {
        "categories": [
            {"slug": "sales", "label": "Sales & support"},
            {"slug": "developer-tools", "label": "Developer tools"},
        ],
        "reserved": ["hr"],
        "forbiddenTags": {"composio": "derived from auth"},
    }
)


def entry(meta: dict) -> dict:
    return {
        "server": {"name": "com.example/mcp", "_meta": {"ai.nimblebrain/connector": meta}},
        "_meta": {},
    }


def test_one_known_category_and_keywords_pass() -> None:
    check_entries([entry({"categories": ["sales"], "tags": ["crm", "leads"]})], VOCAB)


def test_tags_are_optional() -> None:
    check_entries([entry({"categories": ["sales"]})], VOCAB)


@pytest.mark.parametrize(
    ("meta", "message"),
    [
        ({}, "needs `categories`"),
        ({"categories": []}, "needs `categories`"),
        ({"categories": "sales"}, "needs `categories`"),
        ({"categories": ["sales", "developer-tools"]}, "one is allowed"),
        ({"categories": ["marketing"]}, "not in categories.yaml"),
        ({"categories": ["hr"]}, "reserved, not yet offered"),
        ({"categories": ["sales"], "tags": ["Composio"]}, "forbidden"),
        ({"categories": ["sales"], "tags": ["developer-tools"]}, "repeat a category"),
        ({"categories": ["sales"], "tags": "crm"}, "list of words"),
    ],
)
def test_rejects(meta: dict, message: str) -> None:
    with pytest.raises(BuildError, match=message):
        check_entries([entry(meta)], VOCAB)


@pytest.mark.parametrize(
    "raw",
    [
        {},
        {"categories": [{"slug": "sales"}]},
        {"categories": [{"slug": "Sales", "label": "Sales"}]},
        {"categories": [{"slug": "a", "label": "A"}, {"slug": "a", "label": "B"}]},
        {"categories": [{"slug": "a", "label": "A"}], "reserved": ["a"]},
        {"categories": [], "extra": 1},
    ],
)
def test_rejects_bad_vocabulary(raw: dict) -> None:
    with pytest.raises(BuildError):
        parse_vocabulary(raw)


def test_repo_vocabulary_and_servers_pass() -> None:
    """The checked-in vocabulary is valid, and every authored server meets it."""
    root = Path(__file__).resolve().parent.parent
    vocab = parse_vocabulary(yaml.safe_load((root / "categories.yaml").read_text()))
    from nimblebrain_catalog.cli import read_authored

    check_entries(read_authored(root / "servers"), vocab)
