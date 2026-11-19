# nimblebrain-catalog

NimbleBrain's catalog of the connectors it offers. Browse it at
[catalog.nimblebrain.ai](https://catalog.nimblebrain.ai), or read it through the
[official MCP Registry API](https://registry.modelcontextprotocol.io/docs).

Each connector is also a plugin with the skill for using it. Add the catalog to Claude
Code as a marketplace with `/plugin marketplace add https://catalog.nimblebrain.ai/marketplace.json`.

```sh
curl https://catalog.nimblebrain.ai/v0.1/servers
curl https://catalog.nimblebrain.ai/marketplace.json
curl https://catalog.nimblebrain.ai/.well-known/ai-catalog.json
curl https://catalog.nimblebrain.ai/v0.1/servers/ai.bassethound%2Fbassethound/versions/latest
```

To list a server, follow `docs/publishing.md`: what belongs here, how publishing works,
and the steps. `AGENTS.md` covers how the build works.
