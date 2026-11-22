# ai-house

Agent house: rooms of AI agents (leader, researcher, writer, reviewer) that take a goal, plan it, do the work, review it, and learn from results.

Backend: Supabase project `agent-house` (Postgres). Models: Gemini API free tier (`gemini-3.1-flash-lite`), with built-in Google Search, URL Context and Code Execution per agent.

## Layout

- `supabase/migrations/` - schema changes applied to the live project, in order.
- `supabase/seed/` - data changes applied to the live project (agent config).
- `supabase/snapshot/` - reference copy of the live schema. Do not run on the live project.
- `docs/status.md` - where things stand and what is next.

## Secrets

Never commit keys. Gemini and Supabase keys go in `.env` (ignored by git) or environment variables.
