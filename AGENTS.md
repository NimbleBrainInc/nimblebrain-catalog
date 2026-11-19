# nimblebrain-catalog

Builds `catalog.nimblebrain.ai`: NimbleBrain's catalog of the connectors it offers,
served in the official MCP Registry API (`/v0.1/servers`). It is a subregistry: it
mirrors the servers named in `members.yaml` from the official registry
(`registry.modelcontextprotocol.io`), publishes the ones authored in `servers/`, and
serves both through the same API. Each server is also packaged as a plugin (Agent
Plugins 1.0), with the skill for using it, listed in an install index for each kind
of reader and in `.well-known/ai-catalog.json`. ADR-0068 in the runtime repo (`adr/`)
sets what the catalog is for.

## How data flows

```
product repo server.json ──(product CI: mcp-publisher)──► official registry
official registry + servers/*.yaml ──(catalog build)──► /v0.1/servers, the catalog page
servers + plugins.yaml + plugins/*/skills ──(catalog build)──► plugins/<name>.zip, marketplace.json, nimblebrain/marketplace.json, nimblebrain/connectors.yaml, .well-known/ai-catalog.json
dist/ ──(catalog publish)──► S3 ──► CloudFront ──► catalog.nimblebrain.ai
```

- **A server's identity, versions, and status belong to the official registry.** Each
  product publishes its own `server.json` there from its own release CI. This repo
  never publishes upstream and holds no upstream credentials. To change what a server
  says, change its `server.json` in the product repo and release.
- **A mirrored server is copied unchanged.** Adding one is one entry in `members.yaml`;
  its records, upstream `_meta` included, are served as upstream serves them.
- **An authored server is a `ServerDetail` in `servers/*.yaml`.** It is for a connector
  whose vendor has not published a server under the name NimbleBrain installs it by, or
  for an upstream server whose NimbleBrain auth a mirrored record cannot carry
  (Bassethound). It keeps the upstream name and is pinned: it changes only when its
  entry here is edited, not when the product releases.
  NimbleBrain's fields sit in the server's own `_meta`, under `ai.nimblebrain/connector`
  (auth, tags, OAuth setup, brokering) and `ai.nimblebrain/host` (placements), which is
  where the runtime reads them. The file shape (`{servers: [...]}`) is the one the
  runtime's catalog directory reads. Only remote servers are accepted.
- **A name appears once.** The build fails when a name is both mirrored and authored,
  or authored twice.
- **A plugin is one catalog server plus its skill.** `plugins.yaml` names each plugin
  and its server. Its skills are written by hand in `plugins/<name>/skills/<skill>/SKILL.md`
  (an Agent Skill whose `name` is its folder), and a skill bound to the connector says
  so with `metadata.nimblebrain.server: <plugin name>`. Everything else restates the
  server, so the build generates it into the plugin's zip and the repo never stores it:
  `plugin.json` (with `extensions["ai.nimblebrain"].servers` naming the catalog
  server), `mcp.json`, and Claude Code's `.mcp.json`. A Composio plugin has no MCP
  config, since its remote is a placeholder only NimbleBrain can replace.
- **A plugin's name is short and unique in this catalog** (`notion`, installed as
  `notion@nimblebrain`). Claude Code requires the marketplace entry's name to equal the
  manifest's and prefixes each skill with it. Its global identifier is the AI Catalog's
  `urn:air:nimblebrain.ai:<name>:plugin`.
- **Each install index lists only what its reader can run** (ADR-0068). A listing
  promises the reader that the plugin installs and signs in. `marketplace.json`, for
  any host, lists a plugin when every server it names is reached by URL and signs in
  by DCR, or is mirrored with no NimbleBrain auth stated. `nimblebrain/marketplace.json`,
  for the NimbleBrain runtime, lists every plugin. A Composio connector (only
  NimbleBrain can reach it) or an `auth: static` server (it needs an operator's OAuth
  app) is NimbleBrain-only, and the AI Catalog marks it with
  `extensions["ai.nimblebrain"].nimblebrainOnly`. The build derives this from each
  server's auth, so no one keeps a list.
- **A fresh install starts with the portable servers.** The build writes them as a
  runtime catalog file, `nimblebrain/connectors.yaml` (`{servers: [...]}`), which the
  runtime image takes at build as its in-image catalog. Every entry installs with
  nothing to configure, by the same `portable()` rule as `marketplace.json`.
- **The zip is the install source.** This repo is private, so no host can clone it.
  `marketplace.json` names each plugin's zip by URL with its sha256, and the AI Catalog
  entry carries the same digest. Zips are built with fixed timestamps, so a plugin's
  digest changes only when its content does.
- **Nothing reads the catalog yet.** Hosted instances read their own copy of the
  servers, a local install reads the example built into the runtime image, and the
  runtime fetches connector skills from the `connector-skills` repo. Keep `servers/`
  and the skills equal to those copies until instances read the catalog instead.
- **Namespace follows who sells the server.** A product sold on its own publishes under
  its own domain (`ai.bassethound/…`, `com.todosforagents/…`); a server that exists only
  as part of NimbleBrain publishes under `ai.nimblebrain/…`. The catalog lists both.
  Registry names are permanent, so the namespace is chosen once, when a server first
  publishes.

To list a server, or to decide whether one belongs here: `docs/publishing.md`.

## Layout

| Path | What |
|---|---|
| `members.yaml` | Servers mirrored from the official registry |
| `servers/*.yaml` | Servers the catalog authors: `curated.yaml` (DCR and static OAuth), `composio.yaml` (brokered by Composio) |
| `plugins.yaml` | The plugins: each one's name and the catalog server it installs |
| `plugins/<name>/skills/` | Each plugin's hand-written skills |
| `src/nimblebrain_catalog/build.py` | Pure: members + upstream entries + authored servers → objects keyed by API path |
| `src/nimblebrain_catalog/render.py` | Pure: the server list → the catalog page at `/` and the 404 body. A Composio connector's remote is a placeholder, so the page does not show it |
| `src/nimblebrain_catalog/plugins.py` | Pure: plugins + servers + skills → each plugin's zip, both install indexes, and the AI Catalog |
| `src/nimblebrain_catalog/cli.py` | `catalog build` (fetch upstream, write `dist/`) and `catalog publish` (upload to S3) |
| `.github/workflows/deploy.yml` | Builds and publishes on push to `main`, hourly, and on `repository_dispatch` |

## Hosting rules

- **Served from S3 behind CloudFront, not a static file host.** `v0.1/servers` and the
  keys under `v0.1/servers/…` are separate objects, which a file tree cannot hold, and
  every API object is served as `application/json`. Locally each one is written as
  `dist/api/<key>.json`; `publish` strips the suffix.
- **The catalog page at `/` is rendered by the same build, from the same list.** It is
  `index.html`, which CloudFront serves for `/`, and needs no script to show the list.
  It is the only catalog UI, so it cannot disagree with the API. Its brand tokens are
  copied from the runtime's `web/src/theme/palette.ts`; change them there first.
- **Unknown paths return 404 with the official registry's problem body.** S3 answers a
  missing key with 403, since CloudFront cannot list the bucket; CloudFront maps that 403
  to 404 and serves `errors/404.json`. The site files live in `dist/site/` under their
  own keys.
- **A server name's `/` is a literal `/` in the object key.** The API encodes it as
  `%2F`; S3 decodes the path, so `ai.bassethound%2Fbassethound` and the raw form reach
  the same object.
- **The list holds each server's latest version only**, since a static object cannot
  honor `?version=latest`. Query parameters are ignored, and the catalog is small
  enough that no client needs `cursor` or `search`.
- **An authored server has one version**, the one its entry states, served as its
  `latest`.
- **A failed build publishes nothing**, so the catalog keeps serving the last good copy
  when upstream is down or a member is missing. `publish` deletes keys under `v0.1/`
  and `plugins/` the build no longer produces.
- **Every site file's content type comes from its key**: the page and the 404 body by
  name, `.json` as `application/json`, `.yaml` as `application/yaml`, `.zip` as
  `application/zip`.
- **registry.nimblebrain.ai, the catalog's first host, redirects.** Every request
  gets a 301 to the same path on catalog.nimblebrain.ai, so old links and clients keep
  working. The bucket keeps that first host's name, since a bucket cannot be renamed.
- The bucket, distribution, certificate, DNS, and the deploy role are managed outside
  this repo. The deploy role trusts only this repo's `main`.

## Commands

```sh
uv sync
uv run pytest -q
uv run ruff format . && uv run ruff check . && uv run ty check src tests
uv run catalog build          # writes dist/ from members.yaml, servers/, plugins, and the live upstream
```

Publishing runs in CI only (`deploy.yml`), with the role in the
`REGISTRY_DEPLOY_ROLE_ARN` repo variable and the distribution in
`REGISTRY_CF_DISTRIBUTION_ID`.
