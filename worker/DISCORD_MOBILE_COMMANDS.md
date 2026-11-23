# Discord mobile command center

The Discord bridge is owner-only and accepts commands or natural-language messages in the configured private channel. It runs on the local AI House worker, so the PC must be on and the worker running for PC actions.

## Required environment variables

Set these in the local worker environment (do not paste tokens into chat or commit them):

- `DISCORD_BOT_TOKEN`: the bot token from Discord Developer Portal
- `DISCORD_OWNER_ID`: your Discord numeric user ID; only this user can issue commands or click decision buttons
- `DISCORD_CHANNEL_ID`: the private channel where you want to talk to AI House

In Discord Developer Portal, enable **Message Content Intent** for the bot. Give it only the channel permissions it needs: View Channel, Send Messages, Read Message History, and use message components.

## Phone workflow

- Send a normal message in the configured channel to talk to the Leader.
- The Leader replies normally. When a genuine owner decision is needed, it sends a question with buttons and a short explanation. Specialist task briefs that previously appeared only in the dashboard also arrive as multi-choice buttons.
- Choose an option from the buttons. The answer is saved in the local approval ledger and the Leader is called again with that answer in context.
- Choose **Other / type a reply** when offered, then type the detail in the channel.
- Desktop/PC access and other risky tasks use the existing approval ledger. The Discord approval alert now includes **yes/no** buttons. The action still runs only after the approval is recorded and the local worker processes it.
- Use `!directive Your instruction` to persist a direction that the CEO applies to current task priorities or replans; `!directive clear` clears active directions. The directive is included in future Leader calls until cleared.
- Use `!status`, `!pending`, `!start`, or `!stop` for quick controls.

Button interactions are restricted to the configured owner ID. Approval IDs are checked against pending requests; stale buttons cannot approve a different request. Pending button views are restored from the local approval ledger after a bot restart, so a pending request does not lose its buttons just because the PC worker reconnects.

## Decision memo

Each new business writes `BUSINESS_DECISION.txt` in its business workspace. It is a human-readable memo with customer, problem, solution, validation, rationale, alternatives, risks, sources, and success metric. A later North Face outcome review is appended after the business cycle. The engine removes the old generated `BUSINESS_DECISION.json` artifact when migrating; JSON remains for internal machine state only.
