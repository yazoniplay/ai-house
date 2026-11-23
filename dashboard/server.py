"""Local-first AI House dashboard. Starts autonomy automatically on launch."""
import json
import os
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
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
if str(WORKER_DIR) not in sys.path:
    sys.path.insert(0, str(WORKER_DIR))
from channel_connectors import connection_status, gumroad_products, gumroad_create_product, youtube_channel, youtube_upload_video, ConnectorError
from computer_use import ComputerUseError, execute as computer_execute, status as computer_status
from approvals import list_requests as list_owner_approvals, answer as answer_owner_approval
from desktop_agent import DesktopAgentError, create_task as create_desktop_task, run_task as run_desktop_task, resume_task as resume_desktop_task, list_tasks as list_desktop_tasks
from coding_room import CodingRoomError, create_project as create_coding_project, list_projects as list_coding_projects, cancel_project as cancel_coding_project

app = Flask(__name__)
lock = threading.RLock()
engine_process = None
engine_log_handle = None
ask_rate_lock = threading.Lock()
ask_last_question = 0.0


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


def read_jsonl_tail(path, limit=150, max_bytes=8 * 1024 * 1024):
    """Read at most the newest max_bytes and limit JSONL records from a growing log."""
    try:
        if not path.exists():
            return []
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            end = handle.tell()
            start = max(0, end - max_bytes)
            handle.seek(start)
            raw = handle.read(max_bytes)
        if start:
            # Drop the possibly incomplete first record from a mid-file slice.
            first_newline = raw.find(b"\n")
            raw = raw[first_newline + 1:] if first_newline >= 0 else b""
        parsed = []
        for line in raw.splitlines()[-limit:]:
            try:
                item = json.loads(line.decode("utf-8", errors="replace"))
                if isinstance(item, dict):
                    parsed.append(item)
            except Exception:
                continue
        return parsed
    except (OSError, ValueError, TypeError):
        return []


def jsonl_tail_truncated(path, max_bytes=8 * 1024 * 1024):
    try:
        return path.exists() and path.stat().st_size > max_bytes
    except OSError:
        return False


def read_events(limit=100):
    # Recent events only; never load an unbounded log during status polling.
    return list(reversed(read_jsonl_tail(EVENT_FILE, limit)))


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


def collect_artifacts(selected_business_dir=None):
    """Collect deliverables only from the selected business, not the whole workspace."""
    if not selected_business_dir:
        return []
    relative = Path(str(selected_business_dir).replace("\\", "/"))
    if relative.is_absolute() or any(part in ("", ".", "..") for part in relative.parts):
        return []
    try:
        target = (WORKSPACE / relative).resolve()
        target.relative_to(WORKSPACE)
    except (OSError, ValueError):
        return []
    if not target.is_dir():
        return []

    blocked_names = {".env", "credentials.json", "secrets.json"}
    blocked_parts = {".ai-house", ".git", "node_modules", ".venv", "venv", "__pycache__"}
    files = []
    try:
        for root, dirs, names in os.walk(target, topdown=True, followlinks=False):
            dirs[:] = [name for name in dirs if name not in blocked_parts]
            for name in names:
                if name.lower() in blocked_names or Path(name).suffix.lower() in (".key", ".pem"):
                    continue
                path = Path(root) / name
                try:
                    resolved = path.resolve()
                    resolved.relative_to(WORKSPACE)
                    if not resolved.is_file():
                        continue
                    stat = resolved.stat()
                    files.append({
                        "path": str(resolved.relative_to(WORKSPACE)).replace("\\", "/"),
                        "name": resolved.name,
                        "size": stat.st_size,
                        "modified": stat.st_mtime,
                    })
                except (OSError, ValueError):
                    continue
                if len(files) >= 2000:
                    break
            if len(files) >= 2000:
                break
        files.sort(key=lambda item: item["modified"], reverse=True)
        return files[:120]
    except OSError:
        return []


@app.get("/")
def index():
    return send_from_directory(HERE, "index.html")


@app.post("/api/ask")
def ask_leader_api():
    global ask_last_question
    body = request.get_json(silent=True)
    text = body.get("text") if isinstance(body, dict) else None
    if not isinstance(text, str) or not text.strip():
        return jsonify(error="Please enter a question."), 400
    if len(text) > 1000:
        return jsonify(error="Question must be 1,000 characters or fewer."), 400
    text = text.strip()
    now = time.monotonic()
    with ask_rate_lock:
        if now - ask_last_question < 5:
            return jsonify(error="Wait a few seconds before asking again."), 429
        ask_last_question = now
    try:
        worker_path = str(WORKER_DIR)
        if worker_path not in sys.path:
            sys.path.insert(0, worker_path)
        from autonomous_engine import chat_with_leader
    except Exception:
        return jsonify(error="The leader is not available right now."), 503
    try:
        reply = chat_with_leader(text)
        return jsonify(reply=reply)
    except Exception:
        return jsonify(error="The leader could not answer."), 500


def read_event_tail(limit=150):
    """Compatibility wrapper for callers that need the recent event tail."""
    return read_jsonl_tail(EVENT_FILE, limit)


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
from studio import StudioError, create_project, list_projects, list_approvals, update_project, move_stage, decide_approval, leader_review_approval
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
    entries = read_jsonl_tail(ACTIONS_FILE, limit=12000)
    for item in entries:
        try:
            cost = float(item.get("cost_usd", 0) or 0)
            kind = str(item.get("kind", "unknown"))
            business = str(item.get("business", ""))
            total_cost += cost
            kinds[kind] = kinds.get(kind, 0) + 1
            if business:
                business_spend[business] = business_spend.get(business, 0.0) + cost
        except (TypeError, ValueError):
            continue
    newest = list(reversed(entries[-200:]))
    totals = {
        "cost_usd": round(total_cost, 6),
        "kinds": kinds,
        "business_spend_usd": {name: round(value, 6) for name, value in business_spend.items()},
        "business_budget_usd": dashboard_budget_settings(),
    }
    return jsonify(entries=newest, totals=totals, history_truncated=jsonl_tail_truncated(ACTIONS_FILE))


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



@app.get("/api/providers/usage")
def provider_usage():
    """Aggregate observed provider/model activity without exposing credentials."""
    providers = {}
    def entry(name):
        name = str(name or "unknown")
        return providers.setdefault(name, {"provider": name, "calls": 0, "estimated_cost_usd": 0.0, "models": {}, "last_call_at": None, "fallbacks": 0, "cooldown_until": None, "last_error": None})
    def parse_time(value):
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
        except Exception:
            return 0.0
    action_items = read_jsonl_tail(ACTIONS_FILE, limit=12000)
    for item in action_items:
        try:
            if item.get("kind") != "model_call":
                continue
            row = entry(item.get("provider"))
            row["calls"] += 1
            row["estimated_cost_usd"] += float(item.get("cost_usd", 0) or 0)
            row["last_call_at"] = max((row.get("last_call_at") or ""), str(item.get("at") or ""))
        except (TypeError, ValueError):
            continue
    event_items = read_jsonl_tail(EVENT_FILE, limit=12000)
    now = time.time()
    for item in event_items:
        try:
            name = item.get("provider")
            if not name:
                continue
            row = entry(name)
            event = str(item.get("event", ""))
            if event == "model_call_ok":
                model = str(item.get("model") or "unknown")
                row["models"][model] = row["models"].get(model, 0) + 1
                at = str(item.get("at") or "")
                row["last_call_at"] = max((row.get("last_call_at") or ""), at)
            elif event == "fallback":
                row["fallbacks"] += 1
                row["last_error"] = str(item.get("error") or "")[:220]
            elif event == "provider_cooldown":
                at = parse_time(item.get("at"))
                until = at + max(0, int(item.get("seconds", 0) or 0))
                if until > now and until > parse_time(row.get("cooldown_until")):
                    row["cooldown_until"] = datetime.fromtimestamp(until, timezone.utc).isoformat()
                    row["last_error"] = str(item.get("error") or "")[:220]
        except (TypeError, ValueError):
            continue
    result = []
    for row in providers.values():
        row["estimated_cost_usd"] = round(row["estimated_cost_usd"], 6)
        row["cooldown_seconds_left"] = max(0, int(parse_time(row.get("cooldown_until")) - now))
        row["status"] = "Cooling down" if row["cooldown_seconds_left"] else ("Observed" if row["calls"] else "Not yet used")
        row["models"] = [{"name": model, "calls": count} for model, count in sorted(row["models"].items(), key=lambda pair: pair[1], reverse=True)]
        result.append(row)
    result.sort(key=lambda row: (row["calls"], row["provider"]), reverse=True)
    truncated = jsonl_tail_truncated(ACTIONS_FILE) or jsonl_tail_truncated(EVENT_FILE)
    return jsonify(providers=result, total_calls=sum(row["calls"] for row in result), estimated_cost_usd=round(sum(row["estimated_cost_usd"] for row in result), 6), history_truncated=truncated, generated_at=datetime.now(timezone.utc).isoformat())

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
    artifacts = collect_artifacts(selected_business_dir)
    roadmap = state.get("roadmap") or {}
    tasks = roadmap.get("tasks") or []
    return jsonify(
        running=process_running(),
        autonomy_enabled=autonomy_enabled(),
        configured=configured(),
        cycle=state.get("cycle", 0),
        business=state.get("business"),
        room_missions=state.get("room_missions") or {},
        computer_room_task_id=state.get("computer_room_task_id"),
        computer_room_task_cycle=state.get("computer_room_task_cycle"),
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
            "decision_reviews": memory.get("decision_reviews", [])[-30:],
            "experiments": memory.get("experiments", [])[-20:],
            "updated_at": memory.get("updated_at"),
        },
        events=[event for event in read_event_tail(1000) if str(event.get('room', 'room-001')) == room_id][-100:],
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



@app.get("/api/coding-room/projects")
def coding_room_projects_api():
    state = read_json(STATE_FILE, {})
    return jsonify(projects=list_coding_projects(WORKSPACE), business=state.get("business"), room_missions=state.get("room_missions") or {}, autonomous=True)


@app.post("/api/coding-room/projects")
def coding_room_create_project_api():
    body = request.get_json(silent=True) or {}
    try:
        project = create_coding_project(
            WORKSPACE, body.get("title"), body.get("target_user"), body.get("problem"),
            body.get("brief"), body.get("success_metric", ""),
        )
        return jsonify(project=project), 201
    except CodingRoomError as exc:
        return jsonify(error=str(exc)), 400


@app.post("/api/coding-room/projects/<project_id>/cancel")
def coding_room_cancel_project_api(project_id):
    try:
        return jsonify(project=cancel_coding_project(WORKSPACE, project_id))
    except CodingRoomError as exc:
        return jsonify(error=str(exc)), 400


@app.get("/api/computer/tasks")
def computer_tasks_api():
    return jsonify(tasks=list_desktop_tasks(WORKSPACE))


@app.post("/api/computer/task")
def computer_create_task_api():
    body = request.get_json(silent=True) or {}
    try:
        task = create_desktop_task(WORKSPACE, body.get("goal", ""), body.get("max_steps", 24))
        threading.Thread(target=run_desktop_task, args=(WORKSPACE, task["id"]), daemon=True, name="desktop-task-" + task["id"]).start()
        return jsonify(task=task), 202
    except (DesktopAgentError, TypeError, ValueError) as exc:
        return jsonify(error=str(exc)), 400


@app.post("/api/computer/tasks/<task_id>/resume")
def computer_resume_task_api(task_id):
    try:
        # Validate the task and approval before starting background continuation.
        thread = threading.Thread(target=resume_desktop_task, args=(WORKSPACE, task_id), daemon=True, name="desktop-resume-" + task_id)
        thread.start()
        return jsonify(status="resuming", task_id=task_id), 202
    except DesktopAgentError as exc:
        return jsonify(error=str(exc)), 400


@app.get("/api/computer/status")
def computer_status_api():
    return jsonify(computer=computer_status(WORKSPACE))


@app.post("/api/computer/action")
def computer_action_api():
    body = request.get_json(silent=True) or {}
    try:
        result = computer_execute(WORKSPACE, body.get("action"), approval_id=body.get("approval_id"))
        return jsonify(result)
    except ComputerUseError as exc:
        return jsonify(error=str(exc)), 400


@app.get("/api/computer/approvals")
def computer_approvals_api():
    items = [item for item in list_owner_approvals(WORKSPACE, pending_only=True) if item.get("room") == "computer"]
    return jsonify(approvals=items)


@app.post("/api/computer/approvals/<approval_id>")
def computer_answer_approval_api(approval_id):
    body = request.get_json(silent=True) or {}
    choice = body.get("choice")
    if choice not in ("yes", "no"):
        return jsonify(error="choice must be yes or no"), 400
    try:
        item = answer_owner_approval(WORKSPACE, approval_id, choice)
        if choice == "yes":
            pending = next((task for task in list_desktop_tasks(WORKSPACE) if task.get("approval_id") == approval_id and task.get("status") == "waiting_approval"), None)
            if pending:
                threading.Thread(target=resume_desktop_task, args=(WORKSPACE, pending["id"]), daemon=True, name="desktop-approved-" + pending["id"]).start()
        return jsonify(approval=item)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400


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


def leader_approved(approval_id):
    approval = next((item for item in list_approvals(WORKSPACE, pending_only=False) if item.get("id") == approval_id), None)
    return bool(approval and approval.get("status") == "approved" and approval.get("decision_actor") == "AI House Leader")


@app.post("/api/integrations/gumroad/products")
def gumroad_create_product_api():
    body = request.get_json(silent=True) or {}
    if not leader_approved(body.get("approval_id")):
        return jsonify(error="A completed AI House Leader approval is required."), 403
    try:
        product = gumroad_create_product(body.get("name"), body.get("price_cents"), body.get("description", ""), published=bool(body.get("published", False)))
        return jsonify(product={k: product.get(k) for k in ("id", "name", "price", "url", "published")}), 201
    except ConnectorError as exc:
        return jsonify(error=str(exc)), 503


@app.post("/api/integrations/youtube/upload")
def youtube_upload_api():
    body = request.get_json(silent=True) or {}
    approval_id = body.get("approval_id")
    if not leader_approved(approval_id):
        return jsonify(error="A completed AI House Leader approval is required."), 403
    relative = Path(str(body.get("path", "")))
    if not relative.parts or relative.is_absolute() or ".." in relative.parts:
        return jsonify(error="Video path must be workspace-relative."), 400
    video_path = (WORKSPACE / relative).resolve()
    try:
        video_path.relative_to(WORKSPACE)
    except ValueError:
        return jsonify(error="Video path must stay inside the workspace."), 400
    suffix = video_path.suffix.lower()
    if suffix not in (".mp4", ".mov", ".m4v", ".webm"):
        return jsonify(error="Unsupported video file type."), 400
    # Upload only a file listed as a deliverable of the Leader-approved project.
    approval = next(item for item in list_approvals(WORKSPACE, pending_only=False) if item.get("id") == approval_id)
    project = next((p for p in list_projects(WORKSPACE) if p.get("id") == approval.get("project_id")), None)
    if not project or not any(str(a.get("path", "")) == relative.as_posix() for a in project.get("artifacts", [])):
        return jsonify(error="Video must be a recorded deliverable of the approved Studio project."), 403
    try:
        result = youtube_upload_video(video_path, body.get("title", project.get("title", "")), body.get("description", ""), body.get("privacy_status", "private"))
        return jsonify(upload=result), 201
    except ConnectorError as exc:
        return jsonify(error=str(exc)), 503


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


@app.post("/api/studio/approvals/<approval_id>/leader-review")
def studio_leader_review_api(approval_id):
    try:
        item = leader_review_approval(WORKSPACE, approval_id)
        return jsonify(approval=item)
    except StudioError as exc:
        return jsonify(error=str(exc)), 503


@app.post("/api/studio/approvals/<approval_id>")
def studio_decide_approval_api(approval_id):
    return jsonify(error="Studio approvals are decided by the AI House Leader. Use the leader-review endpoint."), 403



@app.get("/coding-room")
def coding_room_page():
    return send_from_directory(HERE, "coding_room.html")


@app.get("/computer-room")
def computer_room_page():
    return send_from_directory(HERE, "computer_room.html")


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
