# Local autonomous business engine

This engine runs on your PC and uses your configured model APIs. It researches a business idea, saves a decision record, builds a local MVP in the workspace, runs recognized tests/build scripts, and has a reviewer agent critique the result. It repeats for a limited number of iterations before researching a new idea.

## Setup

1. Install Python 3.10+.
2. From the repository root, install the existing dependency:

   ```powershell
   python -m pip install -r worker/requirements.txt
   ```

3. Add your keys to `worker/.env` (this file is ignored by Git):

   ```dotenv
   GROQ_API_KEY=your_groq_key
   HF_TOKEN=your_huggingface_token
   GEMINI_API_KEY=your_gemini_key
   TAVILY_API_KEY=your_tavily_key
   ```

   The leader/orchestrator uses Gemini 3.5 Flash Lite (`GEMINI_LEADER_MODEL`) and is the final approver. Worker agents use Gemini 3.1 Flash Lite (`GEMINI_WORKER_MODEL`) first, with Groq and Hugging Face as worker fallbacks if Gemini fails. Tavily enables current web research; without it, market research is not live.

4. Run one iteration:

   ```powershell
   python worker/autonomous_engine.py --once
   ```

5. Run continuously:

   ```powershell
   python worker/autonomous_engine.py --loop
   ```

Press Ctrl+C to stop. Progress and memory are saved under `workspace/.ai-house/`; generated project files are placed in `workspace/`.

## Configuration

Optional environment variables:

- `AI_HOUSE_WORKSPACE`: workspace folder path.
- `AI_HOUSE_MAX_ITERATIONS`: iterations per business before researching a new idea (default 5).
- `AI_HOUSE_MAX_FILES_PER_BUILD`: maximum generated files per iteration (default 12).
- `AI_HOUSE_MAX_FILE_BYTES`: per-file size limit (default 120000).
- `AI_HOUSE_POLL_SECONDS`: delay between iterations in loop mode (default 30).
- `GROQ_MODEL`, `HF_MODEL`, `GEMINI_LEADER_MODEL`, `GEMINI_WORKER_MODEL`: override model names.

## Local safety boundary

The engine can create and overwrite files inside its workspace and run recognized project checks (npm test/build/lint or pytest) without a shell. The orchestrator automatically approves good work and sends weak work back to the builder for up to two improvements. It does not install packages automatically, access your personal folders, use Supabase service credentials, spend money, publish, deploy, message people, or change external accounts; unsafe external/destructive actions are rejected by the orchestrator instead of being sent to you for routine approval. Review generated code before running or releasing it. It is an autonomous builder and validator, not a guarantee of customers or revenue.
