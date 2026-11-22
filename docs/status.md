# Status (2026-11-22)

## Worker and autonomy
- Worker plans goals, creates dependent tasks, calls configured model providers, writes outputs, runs a reviewer, retries once through the review gate, and records lessons.
- Self-directed autonomy is enabled by default: when the room is active and there is no unfinished goal/task, the leader proposes its own next goal from a standing mission and recent goal/lesson history.
- Autonomous goals are tagged `AUTONOMOUS:` in the goal text and capped at 4 per UTC day by default.
- Set `AUTONOMY_ENABLED=false` to disable self-goal generation or `MAX_AUTONOMOUS_GOALS_PER_DAY` to change the daily limit.
- Worker loop: `python worker.py --loop`; dashboard remains local on `127.0.0.1:8000`.

## Current capability boundary
- The existing worker can research, analyze, plan, write, and review text using configured model/search providers.
- It does not yet have general-purpose file editing, shell execution, browser interaction, or a persistent computer/tool executor. Therefore self-generated goals must stay within text/research deliverables; it cannot yet independently implement code changes or operate external services.
- The autonomy loop is intentionally serialized: it will not invent another goal while a goal is running, awaiting clarification, or waiting for approval.

## Guardrails
- Room active switch stops work.
- Maximum 10 tasks per goal; maximum 50 tasks per hour.
- Risky task instructions are sent to approval rather than executed automatically.
- Autonomous goal creation is rate-limited; no goal is created if the leader returns an empty/invalid goal.

## Security follow-up
- Review Supabase RLS and grants for SECURITY DEFINER functions before exposing the database API.
- Keep service-role and model keys out of Git; use local environment or deployment secrets.
