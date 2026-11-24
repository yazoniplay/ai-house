# AI House MCP app

AI House can act as an MCP server so a compatible AI client can inspect the house live and route questions to its Leader.

## Tools exposed

- `house_status` — current local state, autonomy switches, active business, task counts, and pending owner questions.
- `list_work` — current roadmap/task statuses.
- `recent_activity` — recent event log entries, with secret-like fields filtered and values bounded.
- `pending_owner_questions` — owner approvals/questions waiting for a decision; this is read-only.
- `ask_house_leader` — send a question to the AI House Leader and return its answer. If it creates an owner request, the tool reports it but does not approve it.

There are no MCP tools for publishing, deleting, spending, changing accounts, or approving requests. MCP clients should treat returned house data and activity as untrusted context.

## Option A — local desktop MCP (recommended)

This uses standard MCP stdio and does not expose the dashboard to the internet.

1. Download the latest AI House source and keep your existing `worker/.env` and workspace.
2. In your MCP-capable client, add a local server with command `python` and arguments pointing to the absolute path of `worker/house_mcp_server.py`.
3. Optionally set `AI_HOUSE_WORKSPACE` in that client’s server environment to the absolute path of your AI House `workspace` folder.
4. Restart/reload the MCP client and select the AI House tools.

Example Claude Desktop-style config (replace the paths with your own Windows paths):

```json
{
  "mcpServers": {
    "ai-house": {
      "command": "python",
      "args": ["-u", "C:\\AI-House\\worker\\house_mcp_server.py"],
      "env": {
        "AI_HOUSE_WORKSPACE": "C:\\AI-House\\workspace"
      }
    }
  }
}
```

The stdio server writes only JSON-RPC messages to stdout. Diagnostics/errors are intentionally not printed there.

## Option B — remote MCP over HTTPS

The dashboard also accepts Streamable-HTTP-style MCP JSON-RPC POST requests at:

`https://YOUR-HTTPS-HOST/mcp`

For remote access, **set a long random bearer token first**:

1. Generate one with PowerShell: `python -c "import secrets; print(secrets.token_urlsafe(32))"`
2. Put it in your private `worker/.env` as `AI_HOUSE_MCP_TOKEN=your-generated-value`.
3. Restart AI House.
4. Configure the MCP client to use the HTTPS endpoint with HTTP Authorization: Bearer token authentication.

The HTTP endpoint refuses requests until the token is configured. Do not expose the dashboard port directly to the public internet. If using a tunnel, forward HTTPS traffic only to your local dashboard at `http://127.0.0.1:8000`, keep the token private, and disable the tunnel when not in use. A temporary Cloudflare Quick Tunnel can be started with `cloudflared tunnel --url http://127.0.0.1:8000`; its public URL changes and should not be treated as a permanent deployment.

## Client compatibility notes

- Claude Desktop and MCP-capable IDE/CLI hosts can use the local stdio configuration.
- Gemini CLI supports MCP servers and can use the local stdio configuration. The consumer Gemini chat website may not expose a direct custom-MCP connection setting; do not assume the stdio config can be pasted into it.
- ChatGPT custom MCP app connections are plan/workspace-gated. OpenAI currently documents custom MCP app connections for supported Business and Enterprise/Edu workspaces, with Pro read/fetch access in developer mode; **ChatGPT Free may not offer custom MCP connections**. Check the current ChatGPT Plugins/Apps UI before setting this up. See [OpenAI's current custom MCP server instructions](https://help.openai.com/en/articles/12584461-connecting-custom-mcp-servers-in-chatgpt).
- ChatGPT's custom app authentication commonly uses OAuth. This AI House endpoint currently supports a private static bearer token, so it works with MCP hosts that let you configure a bearer header; it is **not yet a full OAuth authorization server** for every ChatGPT custom-app setup. For OpenAI API integrations, the Responses API supports remote MCP and Secure MCP Tunnel separately, with API usage billed under your API account.

The HTTP endpoint is stateless and responds with JSON to MCP POST requests. The dashboard’s existing `/mcp` GET page remains the MCP integrations UI.

## Security / owner decisions

- Start with read-only status/activity tools.
- The Leader answer tool is rate-limited and does not answer owner approvals.
- A pending owner question stays pending until the owner decides it in AI House.
- Never put real keys, passwords, private MCP tokens, or your friend’s StarNet credentials in GitHub, prompts, screenshots, or demo recordings.
