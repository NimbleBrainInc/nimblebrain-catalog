from __future__ import annotations

import json

from nimblebrain_registry.build import OFFICIAL_META_KEY
from nimblebrain_registry.render import NOT_FOUND, render_index, site


def entry(name: str, **server: object) -> dict:
    return {
        "server": {"name": name, "version": "1.0.0", "description": "Does things.", **server},
        "_meta": {
            OFFICIAL_META_KEY: {"status": "active", "updatedAt": "2026-11-16T06:08:23Z"},
        },
    }


def listing(*entries: dict) -> dict:
    return {"servers": list(entries), "metadata": {"count": len(entries)}}


def test_card_shows_server_fields_and_links() -> None:
    page = render_index(
        listing(
            entry(
                "ai.example/widget",
                title="Widget",
                websiteUrl="https://widget.example",
                remotes=[{"type": "streamable-http", "url": "https://mcp.widget.example/mcp"}],
            )
        )
    )
    assert 'id="ai.example/widget"' in page
    assert "Widget" in page and "ai.example/widget" in page
    assert "v1.0.0" in page and "Updated 2026-11-16" in page
    assert 'data-copy="https://mcp.widget.example/mcp"' in page
    assert 'href="https://widget.example"' in page
    assert 'href="/v0.1/servers/ai.example%2Fwidget/versions/latest"' in page
    assert "1 server<" in page


def test_upstream_text_is_escaped_and_unsafe_urls_dropped() -> None:
    page = render_index(
        listing(
            entry(
                "ai.example/widget",
                description="<script>alert(1)</script>",
                websiteUrl="javascript:alert(1)",
                remotes=[{"type": "sse", "url": "javascript:alert(2)"}],
            )
        )
    )
    assert "<script>alert(1)" not in page
    assert "&lt;script&gt;" in page
    assert "javascript:" not in page


def test_deprecated_server_is_badged() -> None:
    deprecated = entry("ai.example/b")
    deprecated["_meta"][OFFICIAL_META_KEY]["status"] = "deprecated"
    assert "Deprecated" in render_index(listing(deprecated))


def test_brokered_connector_hides_its_placeholder_remote() -> None:
    brokered = entry(
        "io.vendor/mcp",
        remotes=[{"type": "streamable-http", "url": "https://broker.example/mcp"}],
        _meta={"ai.nimblebrain/connector": {"auth": "composio"}},
    )
    page = render_index(listing(brokered))
    assert "broker.example" not in page


def test_packages_render_as_endpoints() -> None:
    page = render_index(
        listing(entry("ai.example/pkg", packages=[{"registryType": "npm", "identifier": "@x/y"}]))
    )
    assert 'data-copy="@x/y"' in page


def test_empty_catalog() -> None:
    assert "No servers are listed yet." in render_index(listing())


def test_site_has_page_and_404() -> None:
    files = site(listing())
    assert files["index.html"].startswith("<!doctype html>")
    assert json.loads(files["errors/404.json"]) == NOT_FOUND


def test_card_links_the_plugin_that_installs_the_server() -> None:
    page = render_index(listing(entry("ai.example/a")), {"ai.example/a": "example"})
    assert 'href="/plugins/example.zip"' in page
    assert 'href="/marketplace.json"' in page
    assert 'rel="ai-catalog"' in page
