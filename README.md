# nimblebrain-registry

NimbleBrain's catalog of MCP servers, at `registry.nimblebrain.ai`, in the
[official MCP Registry API](https://registry.modelcontextprotocol.io/docs).

```sh
curl https://registry.nimblebrain.ai/v0.1/servers
curl https://registry.nimblebrain.ai/v0.1/servers/ai.bassethound%2Fbassethound/versions/latest
```

To add a server: publish it to the official registry from its own repo, then add its
name to `members.yaml`. See `AGENTS.md` for how the build works.
