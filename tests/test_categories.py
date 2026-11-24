from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from nimblebrain_catalog.build import BuildError
from nimblebrain_catalog.categories import check_entries, parse_vocabulary
from nimblebrain_catalog.cli import read_authored

VOCAB = parse_vocabulary(
    {
        "categories": ["Sales & support", "Developer tools"],
        "reserved": ["HR & recruiting"],
        "forbiddenTags": {"composio": "derived from auth"},
    }
)


def entry(meta: dict) -> dict:
    return {
        "server": {"name": "com.example/mcp", "_meta": {"ai.nimblebrain/connector": meta}},
        "_meta": {},
    }


def test_a_known_category_and_keywords_pass() -> None:
    check_entries([entry({"category": "Sales & support", "tags": ["crm", "leads"]})], VOCAB)


def test_tags_are_optional() -> None:
    check_entries([entry({"category": "Sales & support"})], VOCAB)


@pytest.mark.parametrize(
    ("meta", "message"),
    [
        ({}, "needs a `category`"),
        ({"category": ""}, "needs a `category`"),
        ({"category": ["Sales & support"]}, "needs a `category`"),
        ({"category": "Marketing"}, "not in categories.yaml"),
        ({"category": "sales & support"}, "not in categories.yaml"),
        ({"category": "HR & recruiting"}, "reserved, not yet offered"),
        ({"category": "Sales & support", "tags": ["Composio"]}, "forbidden"),
        ({"category": "Sales & support", "tags": ["developer tools"]}, "repeat a category"),
        ({"category": "Sales & support", "tags": "crm"}, "list of words"),
    ],
)
def test_rejects(meta: dict, message: str) -> None:
    with pytest.raises(BuildError, match=message):
        check_entries([entry(meta)], VOCAB)


@pytest.mark.parametrize(
    "raw",
    [
        {},
        {"categories": []},
        {"categories": "Sales"},
        {"categories": ["Sales", "Sales"]},
        {"categories": ["Sales"], "reserved": ["Sales"]},
        {"categories": ["Sales"], "extra": 1},
    ],
)
def test_rejects_bad_vocabulary(raw: dict) -> None:
    with pytest.raises(BuildError):
        parse_vocabulary(raw)


def test_repo_vocabulary_and_servers_pass() -> None:
    """The checked-in vocabulary is valid, and every authored server meets it."""
    root = Path(__file__).resolve().parent.parent
    vocab = parse_vocabulary(yaml.safe_load((root / "categories.yaml").read_text()))
    check_entries(read_authored(root / "servers"), vocab)
