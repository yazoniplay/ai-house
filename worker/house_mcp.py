"""Read-only MCP tools for observing AI House and routing owner questions to its Leader."""
import json
import os
import re
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_ask_lock = threading.Lock()
_last_ask = 0.0
_SECRET_KEY = re.compile(r"(api.?key|token|secret|password|credential|authorization|service.?key|private.?key)", re.I)
_SECRET_VALUE = re.compile(r"(?i)(api[_ -]?key|access[_ -]?token|secret|password|authorization)\s*[:=]\s*([^\s,;]+)")
_BEARER_VALUE = re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+)


def workspace_path(workspace=None):
    value = workspace or os.environ.get("AI_HOUSE_WORKSPACE") or (ROOT / "workspace")
    return Path(value).expanduser().resolve()


def _read_json(path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return fallback


def _clean(value, depth=0):
    if depth > 5:
        return "[nested data omitted]"
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            key = str(key)
            if _SECRET_KEY.search(key):
                continue
            out[key[:100]] = _clean(item, depth + 1)
        return out
    if isinstance(value, list):
        return [_clean(item, depth + 1) for item in value[-100:]]
    if isinstance(value, str):
        text = _SECRET_VALUE.sub(lambda match: match.group(1) + "=[REDACTED]", value)
        text = _BEARER_VALUE.sub("Bearer [REDACTED]", text)
        return text[:1200]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:300]


def _state(workspace, room_id=None):
    root = workspace_path(workspace) / ".ai-house"
    registry = _read_json(root / "rooms.json", {})
    rooms = registry.get("rooms") if isinstance(registry, dict) else None
    rooms = [room for room in rooms if isinstance(room, dict)] if isinstance(rooms, list) else []
    room = next((item for item in rooms if str(item.get("id")) == str(room_id)), None) if room_id else (rooms[0] if rooms else None)
    if room and room.get("state_file"):
        path = Path(str(room["state_file"]))
        if not path.is_absolute():
            path = ROOT / path
    else:
        path = root / "state.json"
    state = _read_json(path, {})
    if not isinstance(state, dict):
        state = {}
    return root, state, room


def house_status(workspace=None):
    root, state, selected_room = _state(workspace)
    control = _read_json(root / "control.json", {"running": True})
    autonomy = _read_json(root / "autonomy_control.json", {"enabled": True})
    roadmap = state.get("roadmap") if isinstance(state.get("roadmap"), dict) else {}
    tasks = roadmap.get("tasks") if isinstance(roadmap.get("tasks"), list) else []
    pending = 0
    approval_dir = root / "approvals"
    try:
        for path in approval_dir.glob("*.json"):
            item = _read_json(path, {})
            if isinstance(item, dict) and item.get("status") == "pending":
                pending += 1
    except OSError:
        pass
    business = state.get("business") if isinstance(state.get("business"), dict) else {}
    engine_running = bool(state.get("running", False)) or bool(state.get("engine_running", False))
    try:
        pid = int((root / "engine.pid").read_text(encoding="utf-8").strip())
        os.kill(pid, 0)
        engine_running = True
    except PermissionError:
        engine_running = True
    except (OSError, ValueError, TypeError):
        pass
    registry = _read_json(root / "rooms.json", {})
    raw_rooms = registry.get("rooms") if isinstance(registry, dict) else []
    room_summaries = []
    for room in raw_rooms if isinstance(raw_rooms, list) else []:
        if not isinstance(room, dict):
            continue
        _, room_state, _ = _state(workspace, room.get("id"))
        room_business = room_state.get("business") if isinstance(room_state.get("business"), dict) else {}
        room_roadmap = room_state.get("roadmap") if isinstance(room_state.get("roadmap"), dict) else {}
        room_tasks = room_roadmap.get("tasks") if isinstance(room_roadmap.get("tasks"), list) else []
        room_summaries.append(_clean({"id": room.get("id"), "name": room.get("name"), "status": room.get("status"), "business": room_business.get("name"), "cycle": room_state.get("cycle", 0), "task_count": len(room_tasks), "task_status_counts": _status_counts(room_tasks), "activity": room_state.get("activity")}))
    return _clean({
        "house": "AI House",
        "rooms": room_summaries,
        "engine_running": engine_running,
        "autonomy_enabled": bool(autonomy.get("enabled", True)),
        "house_enabled": bool(control.get("running", True)),
        "cycle": state.get("cycle", 0),
        "business": business.get("name"),
        "business_completed": state.get("business_completed", False),
        "current_activity": state.get("activity"),
        "task_count": len(tasks),
        "task_status_counts": _status_counts(tasks),
        "pending_owner_questions": pending,
        "last_updated": state.get("updated_at") or state.get("last_updated"),
    })


def _status_counts(items):
    counts = {}
    for item in items:
        if isinstance(item, dict):
            status = str(item.get("status", "unknown"))[:80]
            counts[status] = counts.get(status, 0) + 1
    return counts


def list_work(workspace=None, limit=30, room_id=None):
    _, state, selected_room = _state(workspace, room_id)
    roadmap = state.get("roadmap") if isinstance(state.get("roadmap"), dict) else {}
    tasks = roadmap.get("tasks") if isinstance(roadmap.get("tasks"), list) else []
    safe = []
    for task in tasks[-max(1, min(int(limit or 30), 50)):]:
        if not isinstance(task, dict):
            continue
        safe.append(_clean({key: task.get(key) for key in (
            "id", "title", "agent_role", "status", "attempts", "last_error", "updated_at"
            ) if key in task}))
    return {"strategy": _clean(roadmap.get("strategy")), "success_metric": _clean(roadmap.get("success_metric")), "tasks": safe}


def recent_activity(workspace=None, limit=25):
    root, _, _ = _state(workspace)
    path = root / "events.jsonl"
    rows = []
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            end = handle.tell()
            handle.seek(max(0, end - 2 * 1024 * 1024))
            raw = handle.read(2 * 1024 * 1024)
        if end > 2 * 1024 * 1024:
            raw = raw.split(b"\n", 1)[-1]
        for line in raw.splitlines()[-max(1, min(int(limit or 25), 50)):]:
            try:
                item = json.loads(line.decode("utf-8", errors="replace"))
                if isinstance(item, dict):
                    rows.append(_clean(item))
            except ValueError:
                continue
    except OSError:
        pass
    return {"events": rows}


def pending_owner_questions(workspace=None):
    root, _, _ = _state(workspace)
    items = []
    approval_dir = root / "approvals"
    try:
        for path in approval_dir.glob("*.json"):
            item = _read_json(path, {})
            if isinstance(item, dict) and item.get("status") == "pending":
                items.append(_clean({key: item.get(key) for key in (
                    "id", "room", "kind", "question", "options", "summary", "created_at"
                ) if key in item}))
    except OSError:
        pass
    items.sort(key=lambda item: str(item.get("created_at", "")))
    return {"questions": items[:50], "count": len(items)}


def ask_house_leader(question, workspace=None):
    global _last_ask
    if not isinstance(question, str) or not question.strip():
        raise ValueError("Provide a non-empty question.")
    question = question.strip()
    if len(question) > 1200:
        raise ValueError("Question must be 1,200 characters or fewer.")
    with _ask_lock:
        now = time.monotonic()
        if now - _last_ask < 5:
            raise RuntimeError("Please wait a few seconds before asking AI House again.")
        _last_ask = now
    worker_dir = ROOT / "worker"
    import sys
    if str(worker_dir) not in sys.path:
        sys.path.insert(0, str(worker_dir))
    from autonomous_engine import chat_with_leader
    result = chat_with_leader(question)
    if isinstance(result, dict):
        reply = result.get("message") or result.get("reply") or "Leader returned no text."
        owner_request = result.get("request") if isinstance(result.get("request"), dict) else None
    else:
        reply = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, default=str)
        owner_request = None
    return {"reply": str(reply)[:12000], "owner_request": _clean(owner_request)}


TOOLS = [
    {"name": "house_status", "description": "Read the current AI House status, autonomy state, active business, task counts, and pending owner-question count. Read-only.", "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "list_work", "description": "Read the current roadmap and recent task statuses for the house. Read-only.", "inputSchema": {"type": "object", "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 30}, "room_id": {"type": "string", "description": "Optional room ID from house_status"}}, "additionalProperties": False}},
    {"name": "recent_activity", "description": "Read recent AI House event records. Secret-like fields are filtered and text is bounded. Read-only.", "inputSchema": {"type": "object", "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 25}}, "additionalProperties": False}},
    {"name": "pending_owner_questions", "description": "List questions/approvals that are waiting for the owner. This tool does not answer or approve them.", "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "ask_house_leader", "description": "Send an owner question to the AI House Leader and return its answer. If the Leader creates an approval request, it is reported but not automatically approved.", "inputSchema": {"type": "object", "properties": {"question": {"type": "string", "minLength": 1, "maxLength": 1200}}, "required": ["question"], "additionalProperties": False}},
]


def call_tool(name, arguments=None, workspace=None):
    arguments = arguments or {}
    if not isinstance(arguments, dict):
        raise ValueError("Tool arguments must be an object.")
    if name == "house_status":
        result = house_status(workspace)
    elif name == "list_work":
        result = list_work(workspace, arguments.get("limit", 30), arguments.get("room_id"))
    elif name == "recent_activity":
        result = recent_activity(workspace, arguments.get("limit", 25))
    elif name == "pending_owner_questions":
        result = pending_owner_questions(workspace)
    elif name == "ask_house_leader":
        result = ask_house_leader(arguments.get("question"), workspace)
    else:
        raise KeyError("Unknown AI House MCP tool: " + str(name))
    return {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, default=str)}], "structuredContent": result, "isError": False}
