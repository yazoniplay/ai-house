"""Local-first AI House dashboard. Starts autonomy automatically on launch."""
import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from flask import Flask, jsonify, request, send_file, send_from_directory

ROOT = Path(__file__).resolve().parents[1]
WORKER_DIR = ROOT / "worker"
WORKSPACE = Path(os.getenv("AI_HOUSE_WORKSPACE", ROOT / "workspace")).resolve()
STATE_DIR = WORKSPACE / ".ai-house"
STATE_FILE = STATE_DIR / "state.json"
EVENT_FILE = STATE_DIR / "events.jsonl"
NORTH_FACE_FILE = STATE_DIR / "north_face.json"
CONTROL_FILE = STATE_DIR / "autonomy_control.json"
PID_FILE = STATE_DIR / "engine.pid"
ENGINE_LOG = STATE_DIR / "engine.log"
ENGINE = WORKER_DIR / "autonomous_engine.py"
HERE = Path(__file__).resolve().parent

app = Flask(__name__)
lock = threading.RLock()
engine_process = None
engine_log_handle = None


def read_json(path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    temp.replace(path)


def autonomy_enabled():
    # First launch defaults to ON. A deliberate Stop persists across dashboard restarts.
    return bool(read_json(CONTROL_FILE, {"enabled": True}).get("enabled", True))


def set_autonomy_enabled(enabled):
    write_json(CONTROL_FILE, {
        "enabled": bool(enabled),
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })


def configured():
    names = ("GEMINI_API_KEY", "GROQ_API_KEY", "NVIDIA_API_KEY", "HF_TOKEN")
    if any(os.getenv(name) for name in names):
        return True
    for path in (WORKER_DIR / ".env", ROOT / ".env"):
        try:
            content = path.read_text(encoding="utf-8")
        except Exception:
            continue
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() in names and value.strip().strip("\"'"):
                return True
    return False


def read_events(limit=100):
    if not EVENT_FILE.exists():
        return []
    try:
        lines = EVENT_FILE.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]
        events = []
        for line in lines:
            try:
                events.append(json.loads(line))
            except Exception:
                continue
        return list(reversed(events))
    except Exception:
        return []


def pid_is_running(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except PermissionError:
        return True
    except (ProcessLookupError, ValueError, OSError, TypeError):
        return False


def stored_pid():
    try:
        return int(PID_FILE.read_text(encoding="utf-8").strip())
    except Exception:
        return None


def process_running():
    global engine_process, engine_log_handle
    with lock:
        if engine_process is not None:
            if engine_process.poll() is None:
                return True
            engine_process = None
            if engine_log_handle:
                engine_log_handle.close()
                engine_log_handle = None
        pid = stored_pid()
        if pid and pid_is_running(pid):
            return True
        if PID_FILE.exists():
            try:
                PID_FILE.unlink()
            except OSError:
                pass
        return False


def launch_engine():
    global engine_process, engine_log_handle
    with lock:
        if process_running():
            return {"ok": True, "running": True, "message": "Autonomy is already running."}
        if not ENGINE.exists():
            return {"ok": False, "error": "Engine file not found: " + str(ENGINE)}
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        engine_log_handle = ENGINE_LOG.open("a", encoding="utf-8", buffering=1)
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        try:
            engine_process = subprocess.Popen(
                [sys.executable, "-u", str(ENGINE), "--loop"],
                cwd=str(ROOT), stdout=engine_log_handle, stderr=subprocess.STDOUT,
                env=env, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            PID_FILE.write_text(str(engine_process.pid), encoding="utf-8")
            return {"ok": True, "running": True, "pid": engine_process.pid}
        except Exception:
            engine_log_handle.close()
            engine_log_handle = None
            raise


def stop_engine_process():
    global engine_process, engine_log_handle
    with lock:
        pid = stored_pid()
        if engine_process is not None and engine_process.poll() is None:
            engine_process.terminate()
            try:
                engine_process.wait(timeout=12)
            except subprocess.TimeoutExpired:
                engine_process.kill()
                engine_process.wait(timeout=5)
        elif pid and pid_is_running(pid):
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    capture_output=True, text=True, timeout=10,
                )
            else:
                os.kill(pid, signal.SIGTERM)
        engine_process = None
        if engine_log_handle:
            engine_log_handle.close()
            engine_log_handle = None
        try:
            PID_FILE.unlink()
        except OSError:
            pass


def supervisor_loop():
    # Keep autonomy alive while enabled. A deliberate Stop turns this supervisor off.
    last_launch = 0.0
    while True:
        time.sleep(6)
        if not autonomy_enabled() or not configured() or process_running():
            continue
        if time.monotonic() - last_launch < 25:
            continue
        last_launch = time.monotonic()
        try:
            launch_engine()
        except Exception as exc:
            try:
                STATE_DIR.mkdir(parents=True, exist_ok=True)
                with ENGINE_LOG.open("a", encoding="utf-8") as handle:
                    handle.write("dashboard_supervisor_error: " + str(exc)[:400] + "\\n")
            except Exception:
                pass


def collect_artifacts():
    if not WORKSPACE.exists():
        return []
    blocked_names = {".env", "credentials.json", "secrets.json"}
    blocked_parts = {".ai-house", ".git", "node_modules", ".venv", "venv", "__pycache__"}
    files = []
    try:
        for path in WORKSPACE.rglob("*"):
            if not path.is_file() or any(part in blocked_parts for part in path.parts):
                continue
            if path.name.lower() in blocked_names or path.suffix.lower() in (".key", ".pem"):
                continue
            try:
                stat = path.stat()
                files.append({
                    "path": str(path.relative_to(WORKSPACE)).replace("\\", "/"),
                    "name": path.name,
                    "size": stat.st_size,
                    "modified": stat.st_mtime,
                })
            except OSError:
                continue
        files.sort(key=lambda item: item["modified"], reverse=True)
        return files[:120]
    except Exception:
        return []


@app.get("/")
def index():
    return send_from_directory(HERE, "index.html")


def read_event_tail(limit=150):
    """Read only the end of the event log and return valid JSON events."""
    if not EVENT_FILE.exists():
        return []
    try:
        with EVENT_FILE.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            position = handle.tell()
            chunks = []
            newline_count = 0
            while position > 0 and newline_count <= limit:
                size = min(8192, position)
                position -= size
                handle.seek(position)
                chunk = handle.read(size)
                chunks.insert(0, chunk)
                newline_count += chunk.count(b"\n")
            lines = b"".join(chunks).decode("utf-8", errors="replace").splitlines()[-limit:]
        events = []
        for line in lines:
            try:
                events.append(json.loads(line))
            except Exception:
                continue
        return events
    except Exception:
        return []


@app.get("/api/live")
def live():
    state = read_json(STATE_FILE, {})
    raw_roadmap = state.get("roadmap")
    roadmap = None
    if isinstance(raw_roadmap, dict):
        roadmap = {
            "strategy": raw_roadmap.get("strategy"),
            "success_metric": raw_roadmap.get("success_metric"),
            "tasks": [
                {
                    "id": task.get("id"),
                    "title": task.get("title"),
                    "agent_role": task.get("agent_role"),
                    "status": task.get("status"),
                    "attempts": task.get("attempts"),
                    "last_error": task.get("last_error"),
                }
                for task in (raw_roadmap.get("tasks") or [])
                if isinstance(task, dict)
            ],
        }
    business = state.get("business")
    if isinstance(business, dict):
        business = {
            key: business.get(key)
            for key in ("name", "score", "sources", "validation")
        }
    else:
        business = None
    return jsonify(
        activity=state.get("activity"),
        business=business,
        roadmap=roadmap,
        events=read_event_tail(150),
    )


@app.get("/api/local/state")
def local_state():
    state = read_json(STATE_FILE, {})
    memory = read_json(NORTH_FACE_FILE, {})
    roadmap = state.get("roadmap") or {}
    tasks = roadmap.get("tasks") or []
    return jsonify(
        running=process_running(),
        autonomy_enabled=autonomy_enabled(),
        configured=configured(),
        cycle=state.get("cycle", 0),
        business=state.get("business"),
        business_completed=state.get("business_completed", False),
        roadmap=roadmap,
        tasks=tasks,
        activity=state.get("activity") or {},
        lessons=state.get("lessons", [])[-20:],
        last_postmortem=state.get("last_business_postmortem"),
        memory={
            "lessons": memory.get("lessons", [])[-25:],
            "task_reviews": memory.get("task_reviews", [])[-30:],
            "mistake_patterns": memory.get("mistake_patterns", [])[:12],
            "business_postmortems": memory.get("business_postmortems", [])[-10:],
            "updated_at": memory.get("updated_at"),
        },
        events=read_events(100),
        artifacts=collect_artifacts(),
        workspace=str(WORKSPACE),
    )


@app.get("/api/local/artifact/<path:relative_path>")
def open_artifact(relative_path):
    candidate = (WORKSPACE / relative_path).resolve()
    try:
        candidate.relative_to(WORKSPACE)
    except ValueError:
        return jsonify(error="Invalid artifact path."), 400
    if not candidate.is_file():
        return jsonify(error="Artifact not found."), 404
    if candidate.name.lower() in (".env", "credentials.json", "secrets.json") or candidate.suffix.lower() in (".key", ".pem"):
        return jsonify(error="This file type is not available from the dashboard."), 403
    return send_file(candidate, as_attachment=request.args.get("download") == "1")


@app.post("/api/local/start")
def start_engine():
    set_autonomy_enabled(True)
    try:
        return jsonify(launch_engine())
    except Exception as exc:
        return jsonify(error=str(exc)), 500


@app.post("/api/local/stop")
def stop_engine():
    set_autonomy_enabled(False)
    stop_engine_process()
    return jsonify(ok=True, running=False, autonomy_enabled=False)


@app.post("/api/local/once")
def run_once():
    if process_running():
        return jsonify(error="Continuous autonomy is already running."), 409
    if not ENGINE.exists():
        return jsonify(error="Engine file not found: " + str(ENGINE)), 404
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with ENGINE_LOG.open("a", encoding="utf-8", buffering=1) as handle:
        try:
            result = subprocess.run(
                [sys.executable, "-u", str(ENGINE), "--once"],
                cwd=str(ROOT), stdout=handle, stderr=subprocess.STDOUT,
                env={**os.environ, "PYTHONUNBUFFERED": "1"}, timeout=900,
            )
            return jsonify(ok=result.returncode == 0, returncode=result.returncode)
        except subprocess.TimeoutExpired:
            return jsonify(error="One cycle exceeded 15 minutes. Check the engine log."), 504


@app.get("/api/local/log")
def local_log():
    try:
        lines = ENGINE_LOG.read_text(encoding="utf-8", errors="replace").splitlines()[-180:]
        return jsonify(text="\n".join(lines))
    except Exception:
        return jsonify(text="No engine log yet.")


if __name__ == "__main__":
    if autonomy_enabled():
        try:
            launch_engine()
        except Exception as exc:
            print("AI House auto-start failed:", exc, file=sys.stderr)
    threading.Thread(target=supervisor_loop, name="ai-house-supervisor", daemon=True).start()
    app.run(host="127.0.0.1", port=8000, debug=False, threaded=True)
