# ai-house

Agent house: rooms of AI agents (leader, researcher, writer, reviewer) that take a goal, plan it, do the work, review it, and learn from results.

**Testing path: local-first on your PC.** The local engine is the first place to test the agent house; cloud/Supabase execution comes later and is optional for local iteration. Models: Gemini 3.1 Flash Lite workers and a Gemini 3.5 Flash Lite leader/orchestrator, with configured free-provider fallbacks. Supabase project `agent-house` remains the later cloud/control-plane integration.

## Local-first testing\n\nSee [`worker/LOCAL_AUTONOMY.md`](worker/LOCAL_AUTONOMY.md). Run `python worker/autonomous_engine.py --once` for one local cycle or `--loop` to keep running. Local state and generated business work stay in the workspace.\n\nThe orchestrator is expected to approve ordinary, reviewed business actions such as publishing, relevant outreach, and deployment when scoped and compliant. It must not spend or transfer money, expose secrets, irreversibly delete important data, or change account permissions without explicit owner authorization.\n\n## Layout

- `supabase/migrations/` - schema changes applied to the live project, in order.
- `supabase/seed/` - data changes applied to the live project (agent config).
- `supabase/snapshot/` - reference copy of the live schema. Do not run on the live project.
- `docs/status.md` - where things stand and what is next.

## Secrets

Never commit keys. Gemini and Supabase keys go in `.env` (ignored by git) or environment variables.
