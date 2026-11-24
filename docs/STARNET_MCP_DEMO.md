# StarNet × AI House MCP demo

This is a consent-first demo plan for connecting AI House to a friend's StarNet instance **only if they agree**.

## What is already in AI House

- The dashboard has an MCP page at `/mcp`.
- AI House supports locally launched MCP servers over **stdio**.
- The server is started only when you explicitly list its tools or call a tool; it is not auto-connected at startup.
- Tool calls are manual from the MCP page. AI House does not automatically run every tool it discovers.

## Demo flow with your friend

1. Show the MCP page and explain that connecting exposes only the tools the friend-approved MCP server provides.
2. Ask your friend to approve the exact StarNet instance, data scope, and tools.
3. Start with a read-only server/tool set (status, list, search, or inspect). Do not connect write/admin tools for the first demo.
4. Your friend provides or helps install the official/approved MCP bridge command and arguments. Do not guess a package name or endpoint.
5. Enter that command and its arguments in AI House → MCP, save it, then use **Connect & list tools**.
6. Inspect each tool description/schema together. Run only a harmless read-only tool that your friend explicitly approves.
7. Disconnect by disabling or removing the server configuration when the demo ends.

## Current transport boundary

The current MCP client is a local **stdio** client. If StarNet offers a local MCP bridge, configure that bridge's command and arguments. If StarNet only offers a remote Streamable HTTP/SSE endpoint, AI House needs a compatible remote-transport adapter first; do not paste a remote URL into the command field or assume it will work.

## Safety

- Never enter or store a friend's API key, bot token, password, or private URL in a public repo, screenshot, or demo recording.
- Keep secrets in the friend's own local environment/configuration and use the official bridge's documented secret handling.
- Do not call write, publish, delete, payment, or admin tools without explicit permission for that specific action.
- A successful MCP tool listing proves only that the bridge responded; it does not prove a full StarNet integration or authorization to act.
