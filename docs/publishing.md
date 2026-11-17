# Publishing an MCP server to the NimbleBrain registry

How a server gets into the catalog at `registry.nimblebrain.ai`: which servers belong
there, how the two registries fit together, and the steps to list one.

## What belongs in the registry

List a server when someone outside NimbleBrain can connect to it or install it, and we
stand behind it as a product.

| Publish | Do not publish |
|---|---|
| A product's hosted MCP server (Bassethound at `mcp.bassethound.ai`, Todos for Agents at `mcp.todosforagents.com`) | Platform servers that run only inside a NimbleBrain workspace (people, memory, webhooks, and the rest of the fleet): they have no public endpoint, and listing them exposes how the platform is built |
| An installable server we release and support (an MCPB bundle, an npm or PyPI package) | A client's delivery server: it belongs to the client |
| | A prototype, a demo, or anything under `concepts/` |
| | A staging or preview endpoint (`*.preview.*`): the listing points at production only |

A server that a NimbleBrain workspace already runs can still be listed, when it also
stands alone (Todos for Agents is both). Mark it `includedInPlatform: true` in
`members.yaml`, and the catalog shows "Included in NimbleBrain".

### Naming

- **The namespace follows who sells the server.** A product sold on its own publishes
  under its own domain: `ai.bassethound/bassethound`, `com.todosforagents/todos`. A
  server that exists only as part of NimbleBrain publishes under `ai.nimblebrain/<server>`.
  Registry names are permanent (a server can be deprecated, never renamed), and a buyer of
  a product needs its name to go with it.
- **The part after the slash names the server**, not the protocol: `/todos`, not `/mcp`.
- **Never publish under `io.github.*`.** That namespace names a GitHub account, not a
  product, and its credential is GitHub-wide.
- **`title` is `<Product> by NimbleBrain`.** Clients and this catalog display the title in
  place of the name, so it is where the NimbleBrain name reaches every listing, whatever
  the namespace.

## How it works

```
product repo                      official MCP Registry                 registry.nimblebrain.ai
server.json ──release CI──►  registry.modelcontextprotocol.io  ──hourly build──►  API + catalog page
             (mcp-publisher,        owns name, versions,          (this repo: members.yaml
              DNS-signed)           status                         picks which servers)
```

- **The product repo owns the server's record.** Its `server.json` says what the server is
  and where it runs. Its release workflow publishes that file to the official registry
  after production has the release, so a listing never advertises a version production
  does not run.
- **The official registry owns identity and versions.** It checks that the publisher
  controls the namespace's domain, keeps every version, and marks one as latest.
- **This repo owns membership.** `members.yaml` names the servers in the NimbleBrain
  catalog. The build copies each one's records from the official registry unchanged, adds
  `_meta["ai.nimblebrain/catalog"]`, and publishes the API and the catalog page. It runs
  on every change to `members.yaml` and hourly, so a release appears within the hour.

This repo never publishes to the official registry and holds no signing key. A change to
what a server says is a change to its `server.json`, released from its own repo.

## Listing a server

Steps 1–4 happen once per server, in the product repo. Step 2 happens once per domain.

### 1. Write `server.json`

At the product repo's root. This one is illustrative; take the real endpoint, version,
and description from the product:

```json
{
  "$schema": "https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json",
  "name": "com.todosforagents/todos",
  "title": "Todos for Agents by NimbleBrain",
  "description": "To-do boards for AI agents: plan, track, and hand off work across sessions.",
  "version": "1.4.0",
  "websiteUrl": "https://todosforagents.com",
  "remotes": [
    { "type": "streamable-http", "url": "https://mcp.todosforagents.com/mcp" }
  ]
}
```

- `description` is at most 100 characters. Say what the server does for an agent, not
  what it is built with.
- `version` matches the version the release ships. Pin it with a test that compares it to
  the package version, so a release cannot publish one number and run another.
- A hosted server lists `remotes`. An installable one lists `packages` (`registryType` is
  `mcpb`, `npm`, `pypi`, or `oci`) and can list both.
- Check it against the schema before the first publish:
  `curl -fsSL <the $schema URL> -o server.schema.json` and validate with any JSON Schema
  validator.

### 2. Prove the domain (once per domain)

The official registry authenticates a namespace by a DNS record on its domain. GitHub
OIDC login grants only `io.github.*`, so our namespaces use DNS.

1. Generate an Ed25519 key. macOS's system `openssl` may be LibreSSL, which cannot; use
   `brew install openssl@3` and that binary.

   ```sh
   openssl genpkey -algorithm Ed25519 -out key.pem
   openssl pkey -in key.pem -outform DER | tail -c 32 | xxd -p -c 32      # private half, 64 hex chars
   openssl pkey -in key.pem -pubout -outform DER | tail -c 32 | base64    # public half
   ```

2. Add a TXT record on the **apex** of the domain (not a `_mcp-auth` subdomain, which fails
   with a generic signature error): `v=MCPv1; k=ed25519; p=<public half>`. Our domains are
   in Route53; the `route53-dns` skill adds the record.
3. Store the private half in 1Password ("<Product> MCP Registry Signing Key") and as the
   `MCP_REGISTRY_SIGNING_KEY` secret of a GitHub environment named `mcp-registry-publish`,
   restricted to `v*` tags. Keep it an environment secret, not a repo secret, and add
   required reviewers if the repo has several writers: the key can overwrite **any** server
   in the namespace.
4. Delete `key.pem`.

Every repo that publishes under one domain shares that domain's key. For `ai.nimblebrain`,
keep the publishing repos few.

### 3. Publish from the release workflow

Copy the `publish-registry` job from Bassethound's `.github/workflows/release.yml`
(NimbleBrainInc/bassethound), the reference implementation. It:

- runs only after the production promote succeeds (`needs:` on that job), in the
  `mcp-registry-publish` environment;
- fails first if the signing key is unreadable, so a release never goes green with the
  publish silently skipped;
- installs a pinned `mcp-publisher` and verifies its checksum before handing it the key;
- runs `mcp-publisher login dns --domain <domain> --private-key "$KEY"`, then
  `mcp-publisher publish`, treating only "cannot publish duplicate version" as success so a
  re-run of a finished release stays green.

The release also refuses a tag whose version disagrees with `server.json`; copy that guard
from the same workflow.

### 4. Release

Cut the release as usual. When the workflow finishes, the server is upstream:

```sh
curl -s "https://registry.modelcontextprotocol.io/v0.1/servers/<name with / as %2F>/versions/latest" | jq .server
```

### 5. Add it to the catalog

In this repo, add the server to `members.yaml` and open a PR:

```yaml
- name: com.todosforagents/todos
  includedInPlatform: true
```

CI builds against the live official registry, so a name that is not published there, or
is misspelled, fails the PR. Once merged, the deploy publishes it.

### 6. Check it

```sh
curl -s https://registry.nimblebrain.ai/v0.1/servers | jq '.servers[].server.name'
curl -s "https://registry.nimblebrain.ai/v0.1/servers/<name with / as %2F>/versions/latest" | jq .
```

and open `https://registry.nimblebrain.ai/#<name>`, which highlights the server's card.

## Changing or removing a server

- **New version or changed details:** edit `server.json` in the product repo and release.
  The catalog follows within the hour. Nothing changes here.
- **Leave the catalog, stay published:** remove the entry from `members.yaml`. The next
  deploy deletes its objects here; the official listing is untouched.
- **Retire it everywhere:** deprecate or delete it in the official registry (see its
  [publishing docs](https://registry.modelcontextprotocol.io/docs)). The catalog shows a
  deprecated server with a "Deprecated" badge and drops a deleted one from the list.
