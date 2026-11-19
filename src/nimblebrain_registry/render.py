"""The registry's human-facing files: the catalog page at `/` and the 404 body.

The page is rendered from the same list the API serves, in the same build, so it
cannot disagree with the API. It needs no script to show the list; the only
script copies an endpoint to the clipboard.

Colors, font, and radii are NimbleBrain's brand tokens, taken from the runtime's
`web/src/theme/palette.ts`, which is their source of truth. Change them there
first and copy the values here.
"""

from __future__ import annotations

import json
import urllib.parse
from collections.abc import Mapping
from html import escape
from typing import Any

from nimblebrain_registry.build import API_PREFIX, OFFICIAL_META_KEY

CONNECTOR_META_KEY = "ai.nimblebrain/connector"

INDEX_KEY = "index.html"
NOT_FOUND_KEY = "errors/404.json"

# Content type of each site file, by key. API objects are all application/json.
SITE_CONTENT_TYPES = {
    INDEX_KEY: "text/html; charset=utf-8",
    NOT_FOUND_KEY: "application/problem+json",
}

# The official registry's 404 body, so a client handles both registries alike.
NOT_FOUND = {"title": "Not Found", "status": 404, "detail": "Not found"}

API_DOCS_URL = "https://registry.modelcontextprotocol.io/docs"
ICON_URL = "https://static.nimblebrain.ai/logos/nimblebrain/{mode}.svg"
FAVICON_URL = "https://nimblebrain.ai/favicon.ico"
FONTS_URL = (
    "https://fonts.googleapis.com/css2?family=Hanken+Grotesk:wght@400;500;600;700"
    "&family=JetBrains+Mono:wght@400;500&display=swap"
)


def _e(value: object) -> str:
    return escape(str(value), quote=True)


def _safe_url(value: object) -> str | None:
    """An http(s) URL from upstream data, or None; anything else never reaches an href."""
    if not isinstance(value, str):
        return None
    return value if urllib.parse.urlsplit(value).scheme in ("http", "https") else None


def _server_json_path(name: str) -> str:
    return f"/{API_PREFIX}/servers/{urllib.parse.quote(name, safe='')}/versions/latest"


def _brokered(server: Mapping[str, Any]) -> bool:
    """A Composio connector's remote is a placeholder replaced at install."""
    connector = (server.get("_meta") or {}).get(CONNECTOR_META_KEY) or {}
    return connector.get("auth") == "composio"


def _endpoints(server: Mapping[str, Any]) -> str:
    rows: list[str] = []
    remotes = [] if _brokered(server) else server.get("remotes") or []
    for remote in remotes:
        url = _safe_url(remote.get("url"))
        if not url:
            continue
        rows.append(
            '<div class="endpoint">'
            f'<span class="kind">{_e(remote.get("type", "remote"))}</span>'
            f"<code>{_e(url)}</code>"
            f'<button type="button" class="copy" data-copy="{_e(url)}"'
            f' aria-label="Copy {_e(url)}">Copy</button>'
            "</div>"
        )
    for package in server.get("packages") or []:
        identifier = package.get("identifier")
        if not identifier:
            continue
        rows.append(
            '<div class="endpoint">'
            f'<span class="kind">{_e(package.get("registryType", "package"))}</span>'
            f"<code>{_e(identifier)}</code>"
            f'<button type="button" class="copy" data-copy="{_e(identifier)}"'
            f' aria-label="Copy {_e(identifier)}">Copy</button>'
            "</div>"
        )
    return "".join(rows)


def _card(entry: Mapping[str, Any], plugin: str | None = None) -> str:
    server = entry["server"]
    meta = entry.get("_meta", {})
    official = meta.get(OFFICIAL_META_KEY, {})
    name = server["name"]
    title = server.get("title") or name

    badges = []
    if official.get("status") == "deprecated":
        badges.append('<span class="badge warn">Deprecated</span>')

    links = [f'<a href="{_e(_server_json_path(name))}">server.json</a>']
    if plugin:
        links.append(f'<a href="/plugins/{_e(urllib.parse.quote(plugin))}.zip">Plugin</a>')
    website = _safe_url(server.get("websiteUrl"))
    if website:
        links.insert(0, f'<a href="{_e(website)}" rel="noopener">Website</a>')

    badges_html = f'<div class="badges">{"".join(badges)}</div>' if badges else ""
    updated = str(official.get("updatedAt") or "")[:10]
    subtitle = f'<p class="name">{_e(name)}</p>' if title != name else ""

    return (
        f'<article class="card" id="{_e(name)}">'
        '<header class="card-head">'
        f'<h2><a href="#{_e(name)}">{_e(title)}</a></h2>'
        f'<span class="version">v{_e(server.get("version", ""))}</span>'
        "</header>"
        f"{subtitle}"
        f'<p class="description">{_e(server.get("description", ""))}</p>'
        f"{badges_html}"
        f"{_endpoints(server)}"
        '<footer class="card-foot">'
        f"<span>{'Updated ' + _e(updated) if updated else ''}</span>"
        f'<span class="links">{" · ".join(links)}</span>'
        "</footer>"
        "</article>"
    )


STYLE = """
:root {
  --background: #ffffff; --foreground: #09090b; --card: #ffffff;
  --muted: #f4f4f5; --muted-foreground: #5c5c66; --border: #e4e4e7;
  --primary: #315EDB; --info-light: #eaf0ff; --warning: #8a5f0a;
  --radius-sm: 0.5rem; --radius-md: 0.75rem;
  --sans: 'Hanken Grotesk', system-ui, sans-serif;
  --mono: 'JetBrains Mono', ui-monospace, SFMono-Regular, monospace;
  color-scheme: light dark;
}
@media (prefers-color-scheme: dark) {
  :root {
    --background: #000000; --foreground: #fafafa; --card: #0e0e10;
    --muted: #161618; --muted-foreground: #9b9ba4; --border: #232326;
    --primary: #6a8fe4; --info-light: #0b1a33; --warning: #e0aa3c;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--background); color: var(--foreground);
  font-family: var(--sans); line-height: 1.5; -webkit-font-smoothing: antialiased;
}
main { max-width: 72rem; margin: 0 auto; padding: 3rem 1.5rem 4rem; }
a { color: var(--primary); text-decoration: none; }
a:hover { text-decoration: underline; }
.masthead { display: flex; align-items: center; gap: 0.875rem; }
.masthead img { width: 2.75rem; height: 2.75rem; }
h1 { font-size: 2.25rem; font-weight: 700; letter-spacing: -0.02em; margin: 0; }
.lede { color: var(--muted-foreground); font-size: 1.125rem; margin: 0.75rem 0 1.25rem; }
nav { display: flex; flex-wrap: wrap; gap: 0.5rem 1.5rem; font-weight: 500; }
.rule { border: 0; border-top: 1px solid var(--border); margin: 2rem 0; }
.count { color: var(--muted-foreground); font-size: 0.875rem; margin: 0 0 1rem; }
.grid {
  display: grid; gap: 1rem;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 22rem), 1fr));
}
.card {
  background: var(--card); border: 1px solid var(--border); border-radius: var(--radius-md);
  padding: 1.25rem; display: flex; flex-direction: column; gap: 0.625rem;
  scroll-margin-top: 1rem;
}
.card:target { border-color: var(--primary); box-shadow: 0 0 0 1px var(--primary); }
.card-head { display: flex; justify-content: space-between; align-items: baseline; gap: 1rem; }
.card h2 { font-size: 1.125rem; font-weight: 600; margin: 0; overflow-wrap: anywhere; }
.card h2 a { color: inherit; }
.version, .name, code, .kind { font-family: var(--mono); }
.version { color: var(--muted-foreground); font-size: 0.8125rem; white-space: nowrap; }
.name { color: var(--muted-foreground); font-size: 0.8125rem; margin: -0.375rem 0 0; }
.description { margin: 0; }
.badges { display: flex; flex-wrap: wrap; gap: 0.375rem; }
.badge {
  background: var(--info-light); color: var(--primary); border-radius: 999px;
  font-size: 0.75rem; font-weight: 600; padding: 0.125rem 0.625rem;
}
.badge.warn { background: var(--muted); color: var(--warning); }
.endpoint {
  display: grid; grid-template-columns: 1fr auto; align-items: center; gap: 0.125rem 0.5rem;
  background: var(--muted); border-radius: var(--radius-sm);
  padding: 0.5rem 0.5rem 0.5rem 0.75rem; font-size: 0.8125rem;
}
.kind { grid-column: 1 / -1; color: var(--muted-foreground); font-size: 0.6875rem; }
.endpoint code { min-width: 0; overflow-wrap: anywhere; }
.copy {
  font: inherit; font-family: var(--sans); font-weight: 500; font-size: 0.75rem;
  color: var(--foreground); background: var(--card); border: 1px solid var(--border);
  border-radius: 0.375rem; padding: 0.25rem 0.625rem; cursor: pointer;
}
.copy:hover { border-color: var(--primary); }
.copy:focus-visible, a:focus-visible { outline: 2px solid var(--primary); outline-offset: 2px; }
.card-foot {
  display: flex; justify-content: space-between; flex-wrap: wrap; gap: 0.5rem;
  color: var(--muted-foreground); font-size: 0.8125rem; margin-top: auto; padding-top: 0.25rem;
}
.empty { color: var(--muted-foreground); }
@media (max-width: 640px) {
  main { padding: 2rem 1rem 3rem; }
  h1 { font-size: 1.75rem; }
}
"""

SCRIPT = """
document.addEventListener("click", async (event) => {
  const button = event.target.closest("button.copy");
  if (!button) return;
  try {
    await navigator.clipboard.writeText(button.dataset.copy);
    button.textContent = "Copied";
  } catch {
    button.textContent = "Copy failed";
  }
  setTimeout(() => { button.textContent = "Copy"; }, 1500);
});
"""


def render_index(listing: Mapping[str, Any], plugins: Mapping[str, str] | None = None) -> str:
    """The catalog page, from the `v0.1/servers` list object.

    `plugins` maps a server's name to the plugin that installs it.
    """
    plugins = plugins or {}
    entries = sorted(
        listing.get("servers", []),
        key=lambda e: str(e["server"].get("title") or e["server"]["name"]).lower(),
    )
    count = len(entries)
    cards = "".join(_card(e, plugins.get(e["server"]["name"])) for e in entries)
    body = (
        f'<p class="count">{count} server{"" if count == 1 else "s"}</p>'
        f'<div class="grid">{cards}</div>'
        if entries
        else '<p class="empty">No servers are listed yet.</p>'
    )
    description = "The connectors NimbleBrain offers, each with the skill for using it."
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>NimbleBrain Registry</title>
<meta name="description" content="{_e(description)}">
<link rel="icon" href="{FAVICON_URL}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="{_e(FONTS_URL)}">
<link rel="alternate" type="application/json" href="/{API_PREFIX}/servers">
<link rel="ai-catalog" type="application/ai-catalog+json" href="/.well-known/ai-catalog.json">
<style>{STYLE}</style>
</head>
<body>
<main>
<div class="masthead">
<picture>
<source srcset="{ICON_URL.format(mode="dark")}" media="(prefers-color-scheme: dark)">
<img src="{ICON_URL.format(mode="light")}" alt="">
</picture>
<h1>NimbleBrain Registry</h1>
</div>
<p class="lede">{_e(description)}</p>
<nav>
<a href="/{API_PREFIX}/servers">API</a>
<a href="/marketplace.json">Plugin marketplace</a>
<a href="/.well-known/ai-catalog.json">AI Catalog</a>
<a href="{API_DOCS_URL}">API reference</a>
<a href="https://nimblebrain.ai">nimblebrain.ai</a>
</nav>
<hr class="rule">
{body}
</main>
<script>{SCRIPT}</script>
</body>
</html>
"""


def site(listing: Mapping[str, Any], plugins: Mapping[str, str] | None = None) -> dict[str, str]:
    """The page and the 404 body, keyed by path, as text."""
    return {
        INDEX_KEY: render_index(listing, plugins),
        NOT_FOUND_KEY: json.dumps(NOT_FOUND) + "\n",
    }
