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
ROOMS_FILE = STATE_DIR / "rooms.json"
NORTH_FACE_FILE = STATE_DIR / "north_face.json"
CONTROL_FILE = STATE_DIR / "autonomy_control.json"
HOUSE_CONTROL_FILE = STATE_DIR / "control.json"
DAILY_DIR = STATE_DIR / "daily"
ACTIONS_FILE = STATE_DIR / "actions.jsonl"
BUSINESSES_DIR = WORKSPACE / "businesses"
PID_FILE = STATE_DIR / "engine.pid"
ENGINE_LOG = STATE_DIR / "engine.log"
ENGINE = WORKER_DIR / "autonomous_engine.py"
HERE = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from worker.channel_connectors import connection_status, gumroad_products, youtube_channel, ConnectorError

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


def house_settings():
    defaults = {"active_hours": "09:00-23:00", "summary_time": "22:00", "max_new_businesses_per_day": "2"}
    env_names = {"active_hours": "AI_HOUSE_ACTIVE_HOURS", "summary_time": "AI_HOUSE_SUMMARY_TIME", "max_new_businesses_per_day": "AI_HOUSE_MAX_NEW_BUSINESSES_PER_DAY"}
    values = {}
    for key, default in defaults.items():
        env_name = env_names[key]
        value = os.getenv(env_name)
        if value is None:
            for path in (WORKER_DIR / ".env", ROOT / ".env"):
                try:
                    for line in path.read_text(encoding="utf-8").splitlines():
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            name, raw = line.split("=", 1)
                            if name.strip() == env_name:
                                value = raw.strip().strip('"').strip("'")
                                break
                except Exception:
                    continue
                if value is not None:
                    break
        values[key] = value if value is not None else default
    return values


def house_control_running():
    return bool(read_json(HOUSE_CONTROL_FILE, {"running": True}).get("running", True))


def local_active_now(window):
    try:
        start, end = window.split("-", 1)
        def minute(value):
            hour, mins = value.strip().split(":")
            return int(hour) * 60 + int(mins)
        local = time.localtime()
        current = local.tm_hour * 60 + local.tm_min
        a, b = minute(start), minute(end)
        return a <= current < b if a < b else (current >= a or current < b)
    except Exception:
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


def room_registry():
    data = read_json(ROOMS_FILE, {})
    rooms = data.get("rooms") if isinstance(data, dict) else None
    if not isinstance(rooms, list) or not rooms:
        rooms = [{"id": "room-001", "name": "Room 1", "state_file": str(STATE_FILE), "status": "active"}]
        data = {"rooms": rooms, "cursor": 0, "past_businesses": []}
    return data


def room_state_path(room):
    raw = room.get("state_file") or str(STATE_FILE)
    path = Path(raw)
    if not path.is_absolute():
        path = ROOT / path
    return path


# Owner-managed briefs, recipes, skills, and recurring schedules.
if str(WORKER_DIR) not in sys.path:
    sys.path.insert(0, str(WORKER_DIR))
from briefs import answer_brief, list_briefs
from recipes import list_recipes
from skills import list_skills
from studio import StudioError, create_project, list_projects, list_approvals, update_project, move_stage, decide_approval
SCHEDULES_FILE = STATE_DIR / "schedules.json"

@app.get("/api/briefs")
def briefs_api():
    return jsonify(briefs=[{key: item.get(key) for key in ("id", "room", "question", "options", "context")} for item in list_briefs(WORKSPACE, True)])

@app.post("/api/briefs/<brief_id>")
def answer_brief_api(brief_id):
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict) or "choice" not in body:
        return jsonify(error='JSON body must contain "choice".'), 400
    try:
        item = answer_brief(WORKSPACE, brief_id, body["choice"])
        return jsonify(id=item["id"], status=item["status"], choice=item["choice"])
    except (ValueError, OSError) as exc:
        return jsonify(error=str(exc)), 400

@app.get("/api/recipes")
def recipes_api():
    return jsonify(recipes=list_recipes(WORKSPACE))

@app.get("/api/skills")
def skills_api():
    return jsonify(skills=list_skills(WORKSPACE))

@app.get("/api/schedules")
def schedules_get_api():
    return jsonify(schedules=read_json(SCHEDULES_FILE, [{"name": "daily_summary", "every_hours": 24, "action": "daily_summary", "last_run": None}]))

@app.post("/api/schedules")
def schedules_post_api():
    body = request.get_json(silent=True)
    entries = body.get("schedules") if isinstance(body, dict) else body
    if not isinstance(entries, list):
        return jsonify(error="JSON body must be a list or contain schedules: []."), 400
    clean = []
    for item in entries:
        if not isinstance(item, dict):
            return jsonify(error="Each schedule must be an object."), 400
        name = str(item.get("name", "")).strip()
        try:
            hours = int(item.get("every_hours"))
        except (TypeError, ValueError):
            return jsonify(error="every_hours must be an integer from 1 to 168."), 400
        action = item.get("action")
        if not name or not 1 <= hours <= 168:
            return jsonify(error="Schedule name is required and every_hours must be 1-168."), 400
        if action not in ("daily_summary", "status_report"):
            return jsonify(error='action must be "daily_summary" or "status_report".'), 400
        clean.append({"name": name[:120], "every_hours": hours, "action": action, "last_run": item.get("last_run")})
    write_json(SCHEDULES_FILE, clean)
    return jsonify(schedules=clean)

@app.get("/api/control")
def house_control_get():
    settings = house_settings()
    return jsonify(running=house_control_running(), active_hours=settings["active_hours"], summary_time=settings["summary_time"], max_new_businesses_per_day=int(settings["max_new_businesses_per_day"]), active_now=local_active_now(settings["active_hours"]))


@app.post("/api/control")
def house_control_post():
    body = request.get_json(silent=True) or {}
    if not isinstance(body.get("running"), bool):
        return jsonify(error="JSON body must contain running: true or false."), 400
    write_json(HOUSE_CONTROL_FILE, {"running": body["running"], "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    return jsonify(running=body["running"])


@app.get("/api/summary")
def daily_summary_api():
    try:
        root = DAILY_DIR.resolve()
        candidates = []
        if root.is_dir():
            for path in root.glob("*.md"):
                resolved = path.resolve()
                try:
                    resolved.relative_to(root)
                except ValueError:
                    continue
                if resolved.is_file():
                    candidates.append(resolved)
        if not candidates:
            return jsonify(None)
        newest = max(candidates, key=lambda path: path.stat().st_mtime)
        return jsonify(date=newest.stem, text=newest.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return jsonify(None)



def dashboard_budget_settings():
    names = ("AI_HOUSE_BUSINESS_BUDGET_USD", "AI_HOUSE_BUSINESS_BUDGET_MAX_USD")
    values = {}
    for name, default in ((names[0], "0"), (names[1], "50")):
        value = os.getenv(name)
        if value is None:
            for path in (WORKER_DIR / ".env", ROOT / ".env"):
                try:
                    for line in path.read_text(encoding="utf-8").splitlines():
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            key, raw = line.split("=", 1)
                            if key.strip() == name:
                                value = raw.strip().strip('"').strip("'")
                                break
                except Exception:
                    continue
                if value is not None:
                    break
        values[name] = float(value if value is not None else default)
    return min(values[names[0]], values[names[1]])


def workspace_contained(path):
    resolved = path.resolve()
    try:
        resolved.relative_to(WORKSPACE)
    except ValueError:
        return None
    return resolved


def outbox_path(relative_path):
    if not relative_path or Path(relative_path).is_absolute():
        return None
    parts = Path(relative_path.replace("\\", "/")).parts
    if not parts or parts[0] != "businesses" or any(part in (".ai-house", ".git", "node_modules", ".venv", "venv") for part in parts):
        return None
    if len(parts) < 3 or parts[1] in ("", ".", "..") or parts[2] not in ("reports", "build", "drafts"):
        return None
    candidate = workspace_contained(WORKSPACE.joinpath(*parts))
    business_root = workspace_contained(BUSINESSES_DIR / parts[1])
    allowed_root = workspace_contained(BUSINESSES_DIR / parts[1] / parts[2])
    if candidate is None or business_root is None or allowed_root is None:
        return None
    if business_root not in candidate.parents or allowed_root not in candidate.parents:
        return None
    return candidate


@app.get("/api/ledger")
def action_ledger_api():
    entries = []
    total_cost = 0.0
    kinds = {}
    business_spend = {}
    try:
        lines = ACTIONS_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        lines = []
    for line in lines:
        try:
            item = json.loads(line)
            if not isinstance(item, dict):
                continue
            cost = float(item.get("cost_usd", 0) or 0)
            kind = str(item.get("kind", "unknown"))
            business = str(item.get("business", ""))
            total_cost += cost
            kinds[kind] = kinds.get(kind, 0) + 1
            if business:
                business_spend[business] = business_spend.get(business, 0.0) + cost
            entries.append(item)
        except Exception:
            continue
    newest = list(reversed(entries[-200:]))
    totals = {
        "cost_usd": round(total_cost, 6),
        "kinds": kinds,
        "business_spend_usd": {name: round(value, 6) for name, value in business_spend.items()},
        "business_budget_usd": dashboard_budget_settings(),
    }
    return jsonify(entries=newest, totals=totals)


@app.get("/api/outbox")
def outbox_api():
    output = []
    root = workspace_contained(BUSINESSES_DIR)
    if root is None or not root.is_dir():
        return jsonify(files=[])
    blocked = {".ai-house", ".git", "node_modules", ".venv", "venv"}
    try:
        businesses = list(root.iterdir())
    except OSError:
        businesses = []
    for business_dir in businesses:
        safe_business = workspace_contained(business_dir)
        if safe_business is None or not safe_business.is_dir() or safe_business.parent != root:
            continue
        for folder in ("reports", "build", "drafts"):
            target_dir = workspace_contained(safe_business / folder)
            if target_dir is None or not target_dir.is_dir():
                continue
            try:
                paths = target_dir.rglob("*")
            except OSError:
                continue
            for path in paths:
                if not path.is_file() or any(part in blocked for part in path.parts):
                    continue
                resolved = workspace_contained(path)
                if resolved is None or not resolved.is_file() or target_dir not in resolved.parents:
                    continue
                try:
                    stat = resolved.stat()
                    output.append({
                        "business": safe_business.name,
                        "path": str(resolved.relative_to(WORKSPACE)).replace("\\", "/"),
                        "bytes": stat.st_size,
                        "modified": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(stat.st_mtime)),
                    })
                except OSError:
                    continue
    output.sort(key=lambda item: item["modified"], reverse=True)
    return jsonify(files=output[:200])


@app.get("/api/outbox/file")
def outbox_file_api():
    relative_path = request.args.get("path", "")
    candidate = outbox_path(relative_path)
    if candidate is None:
        return jsonify(error="Path must identify a file inside a business reports, build, or drafts folder."), 400
    if not candidate.is_file():
        return jsonify(error="Outbox file not found."), 404
    try:
        content = candidate.read_text(encoding="utf-8", errors="replace")[:200000]
    except OSError:
        return jsonify(error="Outbox file could not be read."), 404
    return jsonify(path=str(candidate.relative_to(WORKSPACE)).replace("\\", "/"), content=content)



@app.get("/api/rooms")
def rooms_api():
    registry = room_registry()
    output = []
    for room in registry.get("rooms", []):
        if not isinstance(room, dict):
            continue
        state = read_json(room_state_path(room), {})
        business = state.get("business")
        output.append({
            "id": room.get("id", "room-001"),
            "name": room.get("name", room.get("id", "Room")),
            "status": room.get("status", "active"),
            "business_name": business.get("name") if isinstance(business, dict) else None,
        })
    return jsonify(rooms=output, cursor=registry.get("cursor", 0))


@app.get("/api/live")
def live():
    registry = room_registry()
    requested_room = request.args.get("room")
    rooms = registry.get("rooms", [])
    room = next((item for item in rooms if isinstance(item, dict) and item.get("id") == requested_room), None) if requested_room else (rooms[0] if rooms else None)
    if room is None:
        room = {"id": "room-001", "state_file": str(STATE_FILE)}
    room_id = str(room.get("id", "room-001"))
    state = read_json(room_state_path(room), {})
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
        events=[event for event in read_event_tail(1000) if str(event.get('room', 'room-001')) == room_id][-150:],
    )


@app.get("/api/local/state")
def local_state():
    registry = room_registry()
    requested_room = request.args.get("room")
    rooms = registry.get("rooms", [])
    room = next((item for item in rooms if isinstance(item, dict) and item.get("id") == requested_room), None) if requested_room else (rooms[0] if rooms else None)
    if room is None:
        room = {"id": "room-001", "state_file": str(STATE_FILE)}
    room_id = str(room.get("id", "room-001"))
    state = read_json(room_state_path(room), {})
    memory = read_json(NORTH_FACE_FILE, {})
    selected_business_dir = str(state.get("business_dir") or "").strip("/")
    artifacts = collect_artifacts()
    if selected_business_dir:
        artifacts = [item for item in artifacts if item.get("path", "").startswith(selected_business_dir + "/")]
    else:
        artifacts = []
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
        events=[event for event in read_events(1000) if str(event.get('room', 'room-001')) == room_id][-100:],
        artifacts=artifacts,
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



@app.get("/api/integrations/status")
def integrations_status_api():
    status = connection_status()
    # Validate the configured YouTube OAuth token without exposing it.
    if status["youtube"]["connected"]:
        try:
            status["youtube"]["channel"] = youtube_channel()
        except ConnectorError as exc:
            status["youtube"]["connected"] = False
            status["youtube"]["error"] = str(exc)
    return jsonify(connections=status)


@app.get("/api/integrations/gumroad/products")
def gumroad_products_api():
    try:
        products = gumroad_products()
        # Return only public/product-management fields; never echo credentials.
        safe = [{k: item.get(k) for k in ("id", "name", "price", "currency", "url", "published", "sales_count")} for item in products]
        return jsonify(products=safe)
    except ConnectorError as exc:
        return jsonify(error=str(exc)), 503


# Studio: YouTube production and marketing campaign workflow APIs.
@app.get("/api/studio/projects")
def studio_projects_api():
    kind = request.args.get("kind")
    try:
        return jsonify(projects=list_projects(WORKSPACE, kind))
    except StudioError as exc:
        return jsonify(error=str(exc)), 400


@app.post("/api/studio/projects")
def studio_create_project_api():
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        return jsonify(error="JSON body must be an object."), 400
    try:
        project = create_project(
            WORKSPACE, body.get("kind"), body.get("title"),
            owner=body.get("owner", "owner"), brief=body.get("brief", ""),
        )
        return jsonify(project=project), 201
    except StudioError as exc:
        return jsonify(error=str(exc)), 400


@app.patch("/api/studio/projects/<project_id>")
def studio_update_project_api(project_id):
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(project=update_project(WORKSPACE, project_id, body))
    except StudioError as exc:
        return jsonify(error=str(exc)), 400


@app.post("/api/studio/projects/<project_id>/stage")
def studio_move_stage_api(project_id):
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(project=move_stage(WORKSPACE, project_id, body.get("stage")))
    except StudioError as exc:
        return jsonify(error=str(exc)), 400


@app.get("/api/studio/approvals")
def studio_approvals_api():
    return jsonify(approvals=list_approvals(WORKSPACE, pending_only=False))


@app.post("/api/studio/approvals/<approval_id>")
def studio_decide_approval_api(approval_id):
    body = request.get_json(silent=True) or {}
    try:
        item = decide_approval(WORKSPACE, approval_id, body.get("decision"), body.get("note", ""))
        return jsonify(approval=item)
    except StudioError as exc:
        return jsonify(error=str(exc)), 400



@app.get("/studio")
def studio_page():
    return send_from_directory(HERE, "studio.html")

if __name__ == "__main__":
    if autonomy_enabled():
        try:
            launch_engine()
        except Exception as exc:
            print("AI House auto-start failed:", exc, file=sys.stderr)
    threading.Thread(target=supervisor_loop, name="ai-house-supervisor", daemon=True).start()
    app.run(host="127.0.0.1", port=8000, debug=False, threaded=True)
