# Local autonomous business lab

**Local-first is the primary development and testing path.** Run this on your PC from the repository root before relying on the cloud worker or Supabase execution. The local engine researches, builds into a local workspace, runs recognized tests/build scripts, and lets the leader/orchestrator approve or request improvements automatically. Supabase is an optional later control-plane/sync path; it is not required to test the local engine.

## Setup

1. Install Python 3.10+.
2. Copy `worker/.env.example` to `worker/.env` and fill in the actual API key values locally. Do not commit `worker/.env` or paste secret values into chat.
3. Install the Python dependency:

   ```powershell
   python -m pip install -r worker/requirements.txt
   ```

4. Run one iteration:

   ```powershell
   python worker/autonomous_engine.py --once
   ```

5. Run continuously:

   ```powershell
   python worker/autonomous_engine.py --loop
   ```

Or use the Windows launcher:

```powershell
powershell -ExecutionPolicy Bypass -File worker/run-autonomous.ps1
```

Press Ctrl+C to stop. State and logs are saved under `workspace/.ai-house/`; generated business files are placed in `workspace/`.

## Model roles

- Leader/orchestrator: Gemini 3.5 Flash Lite (`GEMINI_LEADER_MODEL=gemini-3.5-flash-lite`). The leader is pinned to this Gemini model for approval decisions; it does not silently switch to another provider.
- Worker agents: Gemini 3.1 Flash Lite (`GEMINI_WORKER_MODEL=gemini-3.1-flash-lite`) first. Groq and Hugging Face are fallback providers if Gemini fails.
- Tavily supplies live market research when `TAVILY_API_KEY` is set.

## The North Face — self-improvement is the top priority

The North Face is the house's persistent self-improvement system. It is not a decorative reflection or just a chat memory: it records task reviews, root causes, lessons, operational improvement rules, recurring mistake patterns, and business postmortems in `workspace/.ai-house/north_face.json`.

- **After every task:** the leader examines what happened, why the result was approved/retried/failed, and writes a specific behavior-changing rule.
- **Before future tasks:** The North Face memory is included in the leader's planning/review context and in the specialist agent's task context, so agents can apply past lessons rather than repeat known mistakes.
- **After every business cycle:** the leader distinguishes completed work from actual business success, evaluates evidence and failed assumptions, records what worked/failed, and changes the next cycle's approach.
- **Recurring mistakes:** similar root causes are counted and surfaced prominently, helping the leader notice repeated failure patterns.
- **Priority:** self-improvement is explicitly the highest operating priority; speed or task completion must not replace learning and better decisions.

This is persistent experience-based learning, not automatic model-weight training or guaranteed human-like intelligence. The system improves its prompts, plans, and agent behavior using saved experience; it does not fine-tune Gemini itself.
 
The leader acts as CEO/chief of staff: creates a 4–8 step dependency-aware roadmap, sets a success metric, prioritizes tasks by impact and unblock value, assigns specialist roles, tracks attempts and acceptance criteria, reviews actual outputs, retries weak work, and replans blocked work (up to three recovery plans). It saves postmortem lessons and process improvements in local state and `LEADER_MEMORY.json`. Each loop advances one task so progress is visible and resumable. The orchestrator can approve routine business execution—including publishing, relevant outreach, and deployment—when it is goal-aligned, truthful, scoped, reviewed, and platform-compliant. The system must not spend/transfer money, expose secrets, irreversibly delete important data, or change account permissions without explicit owner authorization.

## Configuration

Optional:

- `AI_HOUSE_WORKSPACE`: workspace path.
- `AI_HOUSE_MAX_ITERATIONS`: iterations per business hypothesis (default 5).
- `AI_HOUSE_POLL_SECONDS`: delay between loop iterations (default 30).
- `AI_HOUSE_MAX_FILES_PER_BUILD`: generated file limit (default 12).
- `AI_HOUSE_MAX_FILE_BYTES`: per-file byte limit (default 120000).
- `GROQ_MODEL`, `HF_MODEL`: fallback model overrides.
- `GEMINI_LEADER_MODEL`, `GEMINI_WORKER_MODEL`: requested model role overrides.

The same `worker/.env` template also includes the existing Supabase worker's Supabase, Token Harbor, NVIDIA, and Ollama variables. The local business engine itself does not use the Supabase service-role key.

## Local safety boundary

For local testing, the engine writes inside its workspace and runs recognized test/build scripts without a shell. It does not install dependencies automatically or access your personal folders. Publishing, outreach, and deployment are intended autonomous capabilities after their connectors/action adapters are implemented and orchestrator-reviewed; they are not currently implemented by this local engine. Money movement, secret exposure, irreversible deletion, and account/permission changes remain owner-controlled. Review generated code before running or releasing it. Autonomous building and validation do not guarantee customers or revenue.
