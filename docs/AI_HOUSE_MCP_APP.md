# AI House MCP app

AI House exposes a remote MCP endpoint so supported AI chat apps can read current house state and ask the AI House Leader questions. This is the same MCP server for ChatGPT, Claude, and Gemini; no separate provider-specific bot is needed.

## Live tools

- `house_status` — current house/room status, autonomy switches, active business, task counts, and pending owner-question count.
- `list_work` — current roadmap and task statuses.
- `recent_activity` — recent event log entries; secret-like fields are filtered and values are bounded.
- `pending_owner_questions` — owner questions/approvals waiting for a decision. Read-only.
- `ask_house_leader` — route a question to the AI House Leader and return its answer. If the Leader creates an owner request, the tool reports it but never approves it.

The tools are live snapshots when called, not a continuous video/stream. MCP has no publish, delete, spend, account-change, or approval tool. Treat house output as untrusted context.

## Connect from consumer AI apps (remote HTTPS)

This is the path for the regular ChatGPT/Claude/Gemini websites and apps when their account and app version support custom remote MCP connections. The endpoint must be reachable from the provider over HTTPS.

### 1. Enable a private token

Create a long random token in PowerShell:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Add it only to your private `worker/.env`:

```env
AI_HOUSE_MCP_TOKEN=PASTE_YOUR_RANDOM_TOKEN_HERE
```

Restart AI House. Never commit this token, paste it in a public chat, or include it in screenshots. Anyone who has it can read the exposed house information and ask the Leader. Rotate it by replacing the value and restarting.

### 2. Give AI House a public HTTPS address

The local dashboard binds to `127.0.0.1:8000`; it is not public by default. Use a trusted HTTPS tunnel or deploy the dashboard behind HTTPS. Do not forward port 8000 directly to the open internet.

For a temporary Cloudflare Quick Tunnel, if `cloudflared` is installed:

```powershell
cloudflared tunnel --url http://127.0.0.1:8000
```

Use the HTTPS hostname it prints, followed by `/mcp`, as the MCP server URL. Quick Tunnel URLs change and are for testing; use a named tunnel or trusted host for a persistent connection. The PC and AI House must remain running for live data.

### 3. Add the remote MCP server in the AI app

Use the provider's custom MCP / connector / plugin settings and enter:

- **Name:** AI House
- **Server URL:** `https://YOUR-HTTPS-HOST/mcp`
- **Authentication:** Bearer token / static bearer credential
- **Token:** the private `AI_HOUSE_MCP_TOKEN` value

If the provider asks for transport, select **Streamable HTTP** (MCP JSON-RPC over HTTP). Then scan/discover tools and install or enable the app.

In ChatGPT's current web custom MCP flow, go to Plugins, choose the plus button, then **Add custom MCP server**. Enter the HTTPS URL, configure authentication, review the warning, create it as a plugin, install it, and invoke it in a chat with `@AI House` or by selecting the app. OpenAI's current help: [Connecting custom MCP servers in ChatGPT](https://help.openai.com/en/articles/12584461-connecting-custom-mcp-servers-in-chatgpt).

## Important platform availability

MCP compatibility does not mean every consumer mobile app currently exposes a custom-server connection setting.

- **ChatGPT:** OpenAI currently documents custom MCP connections as web-only. Plan/workspace permissions apply; Business and Enterprise/Edu have full custom MCP support, while Pro supports read/fetch-only connections in the documented developer mode. Free accounts may not have custom MCP access. See the current OpenAI help page linked above.
- **Claude:** Custom remote MCP connectors are available on Claude web and mobile for supported accounts. In connector setup, choose fixed request headers and send `Authorization: Bearer YOUR_TOKEN` if using the house's static bearer token. Claude's remote connector reaches your server from Anthropic's cloud, so it needs a public HTTPS URL on port 443.
- **Gemini:** Add the custom app from Gemini web's Settings > Connected Apps; Google says it then appears in Gemini web and mobile. Current eligibility is restricted to personal Google accounts, users 18+, and the US, with English and activity-history requirements. If the Connected Apps/custom app option is absent, the account/region is not eligible yet. For static token auth, use the Advanced features/credentials field if offered.
- **ChatGPT:** Custom MCP connections are currently web-only, not in the ChatGPT mobile app. Availability is plan/workspace-gated: Business and Enterprise/Edu have full custom MCP support; Pro supports read/fetch-only custom MCP in the documented developer mode; Free may not offer it. On ChatGPT web, use Plugins > plus > Add custom MCP server, enter the HTTPS URL and bearer credential, create/install the plugin, then invoke it from chat.

The server is compatible with remote MCP, but each provider controls account eligibility and where its connector can be used. Claude remote connectors work from mobile once configured; Gemini connected apps are configured on web and then available on mobile; ChatGPT's custom MCP connector remains web-only according to current OpenAI documentation.

## Local desktop MCP (stdio)

For a local MCP host, configure command `python` with arguments pointing to the absolute path of `worker/house_mcp_server.py`. Optionally set `AI_HOUSE_WORKSPACE` to the absolute workspace path.

Example Windows config:

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

The stdio server writes only JSON-RPC messages to stdout.

## Security and owner decisions

- Start with the read-only status and activity tools.
- `ask_house_leader` is rate-limited and routes questions to the Leader; it does not answer or approve owner requests.
- Pending owner questions remain pending until the owner decides them in AI House.
- The current remote endpoint uses one bearer token. Treat it like a password; only share it with a trusted person and rotate it to revoke access.
- Never put real keys, passwords, private MCP tokens, or your friend's StarNet credentials in GitHub, prompts, or demo recordings.
