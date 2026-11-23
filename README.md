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

Put provider keys in `worker/.env` (copy `worker/.env.example` if needed). Never commit keys or share your `.env` file.

Provider order is Gemini first, Groq immediately second, NVIDIA third, and Hugging Face last. The main Groq model is `openai/gpt-oss-120b`; Groq fast reasoning and summaries use `openai/gpt-oss-20b`. If the 120B model returns unavailable/overloaded, the worker tries the 20B model before leaving Groq. Old Llama 3.3 70B / Llama 3.1 8B model IDs in an existing `.env` are automatically mapped to the current GPT-OSS model IDs. Gemini, NVIDIA, Groq, Hugging Face, and Tavily settings are configured locally.

Provider errors are handled separately: Gemini quota and temporary 5xx errors receive cooldowns; NVIDIA calls have a shorter timeout; Hugging Face billing/credit errors are paused for 24 hours instead of being retried each cycle. When Gemini is unavailable, the worker runs a fresh Tavily search before using a backup model. If all providers are unavailable, the current task is saved and waits without consuming its agent retry allowance; the local loop retries automatically after cooldowns.

Roadmap specialists must return physical deliverable files in the `files` array. The worker writes them under `workspace/`, enforces the exact path from the task deliverable, and sends the saved file content to the CEO for review. Interrupted attempts are retried once and then marked failed instead of looping indefinitely.

## The North Face: self-improvement

The local engine records task-level root causes, lessons, improvement rules, repeated mistakes, and business postmortems. Later tasks receive this experience as context. This is persistent experience memory, not automatic model-weight fine-tuning.

## Repository layout

- `worker/` — local autonomy engine, provider integrations, and North Face memory.
- `dashboard/` — localhost dashboard and Windows startup installer.
- `workspace/` — generated business work and local state.
- `supabase/` — later cloud/control-plane integration; not required for local testing.


## Gumroad and YouTube connections

AI House includes local API adapters for Gumroad product listing/creation and YouTube channel lookup/video upload. Copy the new variables from `worker/.env.example` into your private `worker/.env` and fill them locally:

- `GUMROAD_ACCESS_TOKEN`: Gumroad API access token.
- `YOUTUBE_ACCESS_TOKEN`: Google OAuth access token with YouTube Data API permissions. Access tokens expire; refresh them and replace the local value when needed.
- `YOUTUBE_CHANNEL_ID`: optional channel ID for your own reference; the adapter verifies the channel attached to the OAuth token.

Restart the dashboard and open `/api/integrations/status` to verify the connection without revealing credentials. Gumroad products are listed at `/api/integrations/gumroad/products`. YouTube uploads use resumable upload and default to **private**; publishing must be a separate Leader-approved action. Credentials are never stored in the dashboard/browser or committed to GitHub. This first adapter does not perform OAuth sign-in or token refresh automatically; that requires completing the Google/Gumroad authorization flow and storing the resulting secrets locally.


## Local desktop Computer Room

AI House can control the desktop session on the PC where its local dashboard is running. The first implementation uses PyAutoGUI for screenshots, mouse, keyboard, scrolling, and launching explicitly configured applications. Install dependencies with `pip install -r worker/requirements.txt`, then restart the dashboard. Endpoints are local-only on `127.0.0.1:8000`:

- `GET /api/computer/status`
- `POST /api/computer/action` with `{"action":{"kind":"screenshot"}}
- `GET /api/computer/approvals`
- `POST /api/computer/approvals/<id>` with `{"choice":"yes"}` or `no`

Supported action kinds: screenshot, click, move, type, hotkey, scroll, launch_app. App launch is restricted to aliases configured in `workspace/.ai-house/computer_apps.json`, e.g. `{"apps":{"vscode":"C:/Users/you/AppData/Local/Programs/Microsoft VS Code/Code.exe"}}`. No shell command or arbitrary launch arguments are exposed. PyAutoGUI's corner fail-safe remains enabled.

Actions whose declared intent/target indicates sending, publishing, uploading, purchasing, deleting, installing, changing permissions, or another nonstandard shortcut create an owner approval request. The approval is tied to the exact action payload; changing the action invalidates that approval. The Leader can continue routine work, but the local owner must answer risky computer actions. Treat this as an initial guarded computer-use bridge: desktop vision grounding, application-specific UI automation, stronger isolation, and a polished live computer view are still future work. Do not run it against a personal session containing private data; prefer a dedicated Windows user or VM with only business accounts and files.



## Original YouTube production pipeline

A roadmap task explicitly titled **YouTube video production** (or create/produce/edit video) now requires current source evidence from the existing Tavily/Exa research path and a structured `video_recipe`. The local engine uses the recipe to generate narration with Edge TTS, retrieve scene-matched Pexels footage, edit a 1080p video with FFmpeg, burn captions, and create a thumbnail and asset-credit manifest. The resulting MP4 and supporting files are saved under that business's `youtube/<video-slug>/` folder and included in the task's physical deliverables. The Leader reviews the result; this does not automatically publish it.

Local setup:

1. Add `PEXELS_API_KEY` to private `worker/.env`.
2. Install Python packages: `pip install -r worker/requirements.txt`.
3. Install FFmpeg and FFprobe on Windows and add both to PATH.
4. Keep `TAVILY_API_KEY` and/or `EXA_API_KEY` configured for current source-backed research.

This first renderer creates original narrated stock-footage videos and captions. It is a production foundation, not a guarantee of viral performance: the Leader must still reject weak scripts, generic visuals, inaccurate claims, poor pacing, or low-quality thumbnails before publishing.

## One flagship app at a time

The autonomous Leader roadmap now instructs software businesses to focus on one flagship app and finish its core workflow, usability, tests, security, and deployment-quality checks before starting another app. Gumroad product tasks are also instructed to validate a specific buyer problem and competitor alternatives, deliver a complete useful product with previews/instructions, and build a researched channel-specific acquisition plan rather than generating generic AI filler.



### Computer Room setup notes

Open `http://127.0.0.1:8000/computer-room` while the local dashboard is running. The vision operator is currently Gemini-based and reads `GEMINI_API_KEY` from the local environment or `worker/.env`. To allow app launching, copy `worker/computer_apps.example.json` to `workspace/.ai-house/computer_apps.json` and replace the example paths with the exact executable paths on your PC. Only those aliases can be launched; the desktop agent does not receive a general shell tool. Desktop tasks are queued in local JSON, visible in the Computer Room, and pause/resume through the owner approval queue. For safety, use a dedicated desktop account or VM with only business files and channel accounts.
