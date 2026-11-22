"""Local-first autonomy dashboard for AI House. Binds to localhost only."""
import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from flask import Flask, jsonify, request, send_from_directory

ROOT = Path(__file__).resolve().parents[1]
WORKER_DIR = ROOT / "worker"
WORKSPACE = Path(os.getenv("AI_HOUSE_WORKSPACE", ROOT / "workspace")).resolve()
STATE_DIR = WORKSPACE / ".ai-house"
STATE_FILE = STATE_DIR / "state.json"
EVENT_FILE = STATE_DIR / "events.jsonl"
NORTH_FACE_FILE = STATE_DIR / "north_face.json"
ENGINE = WORKER_DIR / "autonomous_engine.py"
HERE = Path(__file__).resolve().parent
app = Flask(__name__)
lock = threading.Lock()
engine_process = None
engine_log_handle = None

def read_json(path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback

def read_events(limit=80):
    if not EVENT_FILE.exists():
        return []
    try:
        lines = EVENT_FILE.read_text(encoding="utf-8").splitlines()[-limit:]
        out = []
        for line in lines:
            try:
                out.append(json.loads(line))
            except Exception:
                pass
        return list(reversed(out))
    except Exception:
        return []

def process_running():
    global engine_process
    return engine_process is not None and engine_process.poll() is None

@app.get("/")
def index():
    return send_from_directory(HERE, "index.html")

@app.get("/api/local/state")
def local_state():
    state = read_json(STATE_FILE, {})
    memory = read_json(NORTH_FACE_FILE, {})
    roadmap = state.get("roadmap") or {}
    tasks = roadmap.get("tasks") or []
    events = read_events()
    try:
        artifacts = sorted(
            str(p.relative_to(WORKSPACE)).replace("\\", "/")
            for p in WORKSPACE.rglob("*") if p.is_file()
            and not any(part in (".ai-house", ".git", "node_modules", ".venv", "venv") for part in p.parts)
        )[:80]
    except Exception:
        artifacts = []
    return jsonify(
        running=process_running(),
        configured=bool(os.getenv("GEMINI_API_KEY") or os.getenv("GROQ_API_KEY") or os.getenv("HF_TOKEN")),
        cycle=state.get("cycle", 0),
        business=state.get("business"),
        business_completed=state.get("business_completed", False),
        roadmap=roadmap,
        tasks=tasks,
        lessons=state.get("lessons", [])[-20:],
        last_postmortem=state.get("last_business_postmortem"),
        memory={
            "lessons": memory.get("lessons", [])[-25:],
            "task_reviews": memory.get("task_reviews", [])[-30:],
            "mistake_patterns": memory.get("mistake_patterns", [])[:12],
            "business_postmortems": memory.get("business_postmortems", [])[-10:],
            "updated_at": memory.get("updated_at"),
        },
        events=events,
        artifacts=artifacts,
        workspace=str(WORKSPACE),
    )

@app.post("/api/local/start")
def start_engine():
    global engine_process, engine_log_handle
    with lock:
        if process_running():
            return jsonify(ok=True, running=True, message="Autonomy is already running.")
        if not ENGINE.exists():
            return jsonify(error=f"Engine file not found: {ENGINE}"), 404
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        engine_log_handle = (STATE_DIR / "engine.log").open("a", encoding="utf-8")
        engine_process = subprocess.Popen(
            [sys.executable, str(ENGINE), "--loop"],
            cwd=str(ROOT), stdout=engine_log_handle, stderr=subprocess.STDOUT,
            env=os.environ.copy(), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return jsonify(ok=True, running=True, pid=engine_process.pid)

@app.post("/api/local/stop")
def stop_engine():
    global engine_process, engine_log_handle
    with lock:
        if not process_running():
            return jsonify(ok=True, running=False, message="Autonomy is already stopped.")
        engine_process.terminate()
        try:
            engine_process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            engine_process.kill()
            engine_process.wait(timeout=5)
        if engine_log_handle:
            engine_log_handle.close()
            engine_log_handle = None
        return jsonify(ok=True, running=False)

@app.post("/api/local/once")
def run_once():
    global engine_process, engine_log_handle
    with lock:
        if process_running():
            return jsonify(error="Stop continuous autonomy before running a single cycle."), 409
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        log_handle = (STATE_DIR / "engine.log").open("a", encoding="utf-8")
        try:
            result = subprocess.run(
                [sys.executable, str(ENGINE), "--once"], cwd=str(ROOT),
                stdout=log_handle, stderr=subprocess.STDOUT, env=os.environ.copy(), timeout=900,
            )
            return jsonify(ok=result.returncode == 0, returncode=result.returncode)
        except subprocess.TimeoutExpired:
            return jsonify(error="One cycle exceeded 15 minutes. Check the engine log."), 504
        finally:
            log_handle.close()

@app.get("/api/local/log")
def local_log():
    path = STATE_DIR / "engine.log"
    try:
        return jsonify(text="\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-160:]))
    except Exception:
        return jsonify(text="No engine log yet. Start autonomy or run one cycle.")

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=False)
