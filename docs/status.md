# Status (2026-11-22)

## Worker and autonomy
- Worker plans goals, creates dependent tasks, calls configured model providers, writes outputs, has the leader/orchestrator review them, retries once through the review gate, and records lessons.
- Self-directed autonomy is enabled by default: when the room is active and there is no unfinished goal/task, the leader proposes its own next goal from a standing mission and recent goal/lesson history.
- Autonomous goals are tagged `AUTONOMOUS:` in the goal text and capped at 4 per UTC day by default.
- Set `AUTONOMY_ENABLED=false` to disable self-goal generation or `MAX_AUTONOMOUS_GOALS_PER_DAY` to change the daily limit.
- Worker loop: `python worker.py --loop`; dashboard remains local on `127.0.0.1:8000`.

## Current capability boundary
- The Supabase worker remains a goal/task planner and text executor. It is not the local computer executor.
- A new local engine, `worker/autonomous_engine.py`, runs on the owner's PC. It autonomously researches opportunities with Tavily (if configured), selects a business hypothesis, coordinates researcher/strategist/architect/builder/growth/finance agents with the orchestrator as final approver, writes files inside `workspace/`, runs recognized npm test/build/lint or pytest commands, and stores state/logs locally.
- Local worker model order: Gemini 3.1 Flash Lite first, then Groq, then Hugging Face Inference Router. Keys are loaded from ignored `worker/.env` or environment variables.
- Model roles: leader/orchestrator uses Gemini 3.5 Flash Lite (`GEMINI_LEADER_MODEL`, default `gemini-3.5-flash-lite`); worker agents use Gemini 3.1 Flash Lite (`GEMINI_WORKER_MODEL`, default `gemini-3.1-flash-lite`). Local workers try Gemini first, then Groq/Hugging Face fallback; the leader stays on its configured Gemini model.
- The orchestrator is now the automatic approval and improvement gate: it approves good internal work, rejects unsafe external/destructive tasks, and sends local build outputs back for up to two improvement rounds. Routine safe work no longer waits for the owner.
- Local engine loop: `python worker/autonomous_engine.py --loop`; Windows launcher: `worker/run-autonomous.ps1`.
- Iterations and opportunity cycles are configurable. The engine can build and test local assets; it does not autonomously spend money, publish, deploy, contact customers, or change accounts. It does not guarantee revenue; customer validation and business performance still need to be measured.

## Guardrails
- Room active switch stops work.
- Maximum 10 tasks per goal; maximum 50 tasks per hour.
- The leader/orchestrator automatically decides gated tasks; external side effects and destructive actions are rejected rather than routed to owner approval.
- Autonomous goal creation is rate-limited; no goal is created if the leader returns an empty/invalid goal.

## Security follow-up
- Review Supabase RLS and grants for SECURITY DEFINER functions before exposing the database API.
- Keep service-role and model keys out of Git; use local environment or deployment secrets.
