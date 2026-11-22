# Status (2026-11-22)

## Worker and autonomy
- Worker plans goals, creates dependent tasks, calls configured model providers, writes outputs, has the leader/orchestrator review them, retries once through the review gate, and records lessons.
- Self-directed autonomy is enabled by default: when the room is active and there is no unfinished goal/task, the leader proposes its own next goal from a standing mission and recent goal/lesson history.
- Autonomous goals are tagged `AUTONOMOUS:` in the goal text and capped at 4 per UTC day by default.
- Set `AUTONOMY_ENABLED=false` to disable self-goal generation or `MAX_AUTONOMOUS_GOALS_PER_DAY` to change the daily limit.
- Worker loop: `python worker.py --loop`; dashboard remains local on `127.0.0.1:8000`.

## Local-first development path
- Local PC execution is the primary testing path. Supabase/cloud execution is a later integration and is not required to test the local engine.
- The user's budget target is $0; use free model tiers/providers and avoid paid dependencies by default.
- Target scale is about 107 agents, with rooms for each business plus dedicated marketing and approval rooms. Visual direction: pixel-station/StarNet-inspired but original and more polished.
- The house should discover trends and new projects (including social feeds and GitHub repositories), research business execution, and eventually create and upload videos. Existing landing-page service and hooks presale are explicitly out of scope; do not suggest new business ideas.

## Current capability boundary
- The Supabase worker remains a goal/task planner and text executor. It is not the local computer executor.
- A new local engine, `worker/autonomous_engine.py`, runs on the owner's PC. Its leader/CEO creates a 4–8 task dependency-aware roadmap, defines a success metric, prioritizes ready work, assigns specialist roles, tracks task status/attempts/outputs/reviews, verifies acceptance criteria, retries weak tasks, and creates up to three recovery roadmaps when work is blocked. It stores progress and postmortem lessons locally, writes artifacts inside `workspace/`, and runs recognized npm test/build/lint or pytest commands.
- Local worker model order: Gemini 3.1 Flash Lite first, then Groq, then Hugging Face Inference Router. Keys are loaded from ignored `worker/.env` or environment variables.
- Model roles: leader/orchestrator uses Gemini 3.5 Flash Lite (`GEMINI_LEADER_MODEL`, default `gemini-3.5-flash-lite`); worker agents use Gemini 3.1 Flash Lite (`GEMINI_WORKER_MODEL`, default `gemini-3.1-flash-lite`). Local workers try Gemini first, then Groq/Hugging Face fallback; the leader stays on its configured Gemini model.
- The orchestrator is the automatic approval and improvement gate: it approves routine goal-aligned publishing, relevant outreach, and deployment after quality/compliance checks; it sends weak local build outputs back for up to two improvement rounds. Routine business execution does not wait for the owner. Spending/transfers, secret exposure, irreversible important-data deletion, and account/permission changes remain owner-controlled.
- Local engine loop: `python worker/autonomous_engine.py --loop`; Windows launcher: `worker/run-autonomous.ps1`.
- Roadmaps and task progress are resumable from local state. After a business cycle, the leader runs a postmortem and saves reusable lessons/process changes in `LEADER_MEMORY.json`. The engine currently builds and tests local assets. Publishing, outreach, and deployment action adapters are planned but not yet implemented in the local engine. It does not guarantee revenue; customer validation and business performance still need to be measured.

## Guardrails
- Room active switch stops work.
- Maximum 10 tasks per goal; maximum 50 tasks per hour.
- The leader/orchestrator automatically decides routine business actions. It may approve publishing, relevant outreach, and deployment when scoped and compliant. Spending/transfers, secrets, irreversible deletion, and account/permission changes require owner authorization.
- Autonomous goal creation is rate-limited; no goal is created if the leader returns an empty/invalid goal.

## Security follow-up
- Review Supabase RLS and grants for SECURITY DEFINER functions before exposing the database API.
- Keep service-role and model keys out of Git; use local environment or deployment secrets.


### The North Face — self-improvement priority
- Added local persistent learning ledger `worker/north_face.py`.
- Records every roadmap task's review, root cause, lesson, improvement rule, and recurring mistake frequency.
- Injects accumulated lessons into leader and specialist task context so prior experience can alter future behavior.
- Runs a business postmortem after each cycle, distinguishing completed tasks from evidence of actual business success/failure, and stores lessons for the next cycle.
- Memory is experience/prompt/behavior based; it does not fine-tune Gemini model weights.
