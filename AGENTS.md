# nimblebrain-registry

Builds `registry.nimblebrain.ai`: NimbleBrain's catalog of MCP servers, served in the
official MCP Registry API (`/v0.1/servers`). It is a subregistry: it reads the official
registry (`registry.modelcontextprotocol.io`), keeps the servers named in
`members.yaml`, adds NimbleBrain's metadata, and serves the same API.

## How data flows

```
product repo server.json ──(product CI: mcp-publisher)──► official registry
official registry ──(this repo: registry build)──► S3 ──► CloudFront ──► registry.nimblebrain.ai
```

- **A server's identity, versions, and status belong to the official registry.** Each
  product publishes its own `server.json` there from its own release CI. This repo
  never publishes upstream and holds no upstream credentials. To change what a server
  says, change its `server.json` in the product repo and release.
- **This repo decides membership and NimbleBrain's metadata.** Adding a server is one
  entry in `members.yaml`. The `server` block is copied unchanged; NimbleBrain's fields
  go under `_meta["ai.nimblebrain/catalog"]`, beside upstream's own `_meta`.
- **Namespace follows who sells the server.** A product sold on its own publishes under
  its own domain (`ai.bassethound/…`, `com.todosforagents/…`); a server that exists only
  as part of NimbleBrain publishes under `ai.nimblebrain/…`. The catalog lists both.
  Registry names are permanent, so the namespace is chosen once, when a server first
  publishes.

## Layout

| Path | What |
|---|---|
| `members.yaml` | The catalog: which servers, and the fields NimbleBrain adds |
| `src/nimblebrain_registry/build.py` | Pure: member list + upstream entries → objects keyed by API path |
| `src/nimblebrain_registry/render.py` | Pure: the server list → the catalog page at `/` and the 404 body |
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
- **A failed build publishes nothing**, so the registry keeps serving the last good copy
  when upstream is down or a member is missing. `publish` deletes keys the build no
  longer produces.
- The bucket, distribution, certificate, DNS, and the deploy role are Terraform in the
  `infra` repo. The deploy role trusts only this repo's `main`.

## Commands

```sh
uv sync
uv run pytest -q
uv run ruff format . && uv run ruff check . && uv run ty check src tests
uv run registry build          # writes dist/ from members.yaml and the live upstream
```

Publishing runs in CI only (`deploy.yml`), with the role in the
`REGISTRY_DEPLOY_ROLE_ARN` repo variable and the distribution in
`REGISTRY_CF_DISTRIBUTION_ID`.
