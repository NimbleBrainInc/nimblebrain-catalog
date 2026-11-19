# nimblebrain-registry

NimbleBrain's catalog of the connectors it offers. Browse it at
[registry.nimblebrain.ai](https://registry.nimblebrain.ai), or read it through the
[official MCP Registry API](https://registry.modelcontextprotocol.io/docs).

Each connector is also a plugin with the skill for using it. Add the catalog to Claude
Code as a marketplace with `/plugin marketplace add https://registry.nimblebrain.ai/marketplace.json`.

```sh
curl https://registry.nimblebrain.ai/v0.1/servers
curl https://registry.nimblebrain.ai/marketplace.json
curl https://registry.nimblebrain.ai/.well-known/ai-catalog.json
curl https://registry.nimblebrain.ai/v0.1/servers/ai.bassethound%2Fbassethound/versions/latest
```

To list a server, follow `docs/publishing.md`: what belongs here, how publishing works,
and the steps. `AGENTS.md` covers how the build works.
