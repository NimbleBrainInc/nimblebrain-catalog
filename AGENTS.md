# nimblebrain-registry

Builds `registry.nimblebrain.ai`: NimbleBrain's catalog of the connectors it offers,
served in the official MCP Registry API (`/v0.1/servers`). It is a subregistry: it
mirrors the servers named in `members.yaml` from the official registry
(`registry.modelcontextprotocol.io`), publishes the ones authored in `servers/`, and
serves both through the same API. Each server is also packaged as a plugin (Agent
Plugins 1.0), with the skill for using it, and listed in `marketplace.json` and
`.well-known/ai-catalog.json`. ADR-0068 in the runtime repo (`adr/`) sets what the
catalog is for.

## How data flows

```
product repo server.json ──(product CI: mcp-publisher)──► official registry
official registry + servers/*.yaml ──(registry build)──► /v0.1/servers, the catalog page
servers + plugins.yaml + plugins/*/skills ──(registry build)──► plugins/<name>.zip, marketplace.json, .well-known/ai-catalog.json
dist/ ──(registry publish)──► S3 ──► CloudFront ──► registry.nimblebrain.ai
```

- **A server's identity, versions, and status belong to the official registry.** Each
  product publishes its own `server.json` there from its own release CI. This repo
  never publishes upstream and holds no upstream credentials. To change what a server
  says, change its `server.json` in the product repo and release.
- **A mirrored server is copied unchanged.** Adding one is one entry in `members.yaml`;
  its records, upstream `_meta` included, are served as upstream serves them.
- **An authored server is a `ServerDetail` in `servers/*.yaml`.** It is for a connector
  whose vendor has not published a server under the name NimbleBrain installs it by.
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
| `src/nimblebrain_registry/build.py` | Pure: members + upstream entries + authored servers → objects keyed by API path |
| `src/nimblebrain_registry/render.py` | Pure: the server list → the catalog page at `/` and the 404 body. A Composio connector's remote is a placeholder, so the page does not show it |
| `src/nimblebrain_registry/plugins.py` | Pure: plugins + servers + skills → each plugin's zip, `marketplace.json`, and the AI Catalog |
| `src/nimblebrain_registry/cli.py` | `registry build` (fetch upstream, write `dist/`) and `registry publish` (upload to S3) |
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
- **A failed build publishes nothing**, so the registry keeps serving the last good copy
  when upstream is down or a member is missing. `publish` deletes keys under `v0.1/`
  and `plugins/` the build no longer produces.
- **Every site file's content type comes from its key**: the page and the 404 body by
  name, `.json` as `application/json`, `.zip` as `application/zip`.
- The bucket, distribution, certificate, DNS, and the deploy role are Terraform in the
  `infra` repo. The deploy role trusts only this repo's `main`.

## Commands

```sh
uv sync
uv run pytest -q
uv run ruff format . && uv run ruff check . && uv run ty check src tests
uv run registry build          # writes dist/ from members.yaml, servers/, plugins, and the live upstream
```

Publishing runs in CI only (`deploy.yml`), with the role in the
`REGISTRY_DEPLOY_ROLE_ARN` repo variable and the distribution in
`REGISTRY_CF_DISTRIBUTION_ID`.
