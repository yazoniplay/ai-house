# AI House

AI House is a local-first autonomous business lab. A CEO/orchestrator chooses and validates an opportunity, creates a roadmap, assigns specialist roles, reviews deliverables, and records experience in The North Face.

## Run the local dashboard

From the project root in PowerShell:

```powershell
python -m pip install -r worker/requirements.txt
python -m pip install flask
python dashboard/server.py
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). The first dashboard launch starts autonomy automatically; you do not need to press Start. Closing the browser tab does not stop the worker while the dashboard server remains running.

The dashboard has a persistent **Stop autonomy** control. Stop disables automatic restarts and remains in effect after the dashboard is restarted. **Resume autonomy** turns it back on.

## Start automatically when Windows signs in

To start the dashboard in the background each time you sign in to Windows, run this once from the project root:

```powershell
powershell -ExecutionPolicy Bypass -File dashboard\install_startup.ps1
```

This registers the current project folder in Windows Task Scheduler and starts the dashboard. Then visit http://127.0.0.1:8000. The dashboard server supervises the worker and restarts it after an unexpected exit, unless you have pressed Stop.

**Local-runtime limit:** the AI House process runs on this PC. It cannot work while the PC is shut down or asleep. Sign in to Windows and keep the machine awake for continuous local operation.

## Work and deliverables

Agent-created reports, business decisions, builder files, and learning summaries are saved under `workspace/`. The dashboard lists these files and lets you open or download them. They are local files; cloud storage uploads and automatic publishing are not configured by this local-first runtime.

The engine uses a CEO/orchestrator and specialist roles such as researcher, strategist, architect, builder, growth, and finance. The current local engine executes one roadmap task at a time and records task-level progress; the roster in the dashboard reflects roles assigned to the current roadmap, not concurrent agents.

## Providers and secrets

Put provider keys in `worker/.env` (copy `worker/.env.example` if needed). Never commit keys or share your `.env` file. Gemini, NVIDIA, Groq, Hugging Face, and Tavily settings are configured locally.

## The North Face: self-improvement

The local engine records task-level root causes, lessons, improvement rules, repeated mistakes, and business postmortems. Later tasks receive this experience as context. This is persistent experience memory, not automatic model-weight fine-tuning.

## Repository layout

- `worker/` — local autonomy engine, provider integrations, and North Face memory.
- `dashboard/` — localhost dashboard and Windows startup installer.
- `workspace/` — generated business work and local state.
- `supabase/` — later cloud/control-plane integration; not required for local testing.
