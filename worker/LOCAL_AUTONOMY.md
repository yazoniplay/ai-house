# Local autonomous business lab

Run this on your PC from the repository root. The local engine researches business opportunities, builds a local MVP, runs recognized tests/build scripts, and lets the leader/orchestrator approve or request improvements automatically.

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

The leader automatically approves good internal work and sends weak work back to the builder for up to two improvement rounds. External or destructive actions such as spending, public publishing, messaging, deployment, account changes, and deleting important data are rejected by policy rather than waiting for owner approval.

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

The engine writes only inside its workspace and runs recognized test/build scripts without a shell. It does not install dependencies automatically, access your personal folders, spend money, publish, deploy, message people, or change external accounts. Review generated code before running or releasing it. Autonomous building and validation do not guarantee customers or revenue.
