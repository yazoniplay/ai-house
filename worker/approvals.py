"""Owner approval requests stored as atomic JSON files."""
import json
import secrets
from datetime import datetime, timezone
from pathlib import Path


def _root(workspace):
    return Path(workspace).resolve() / ".ai-house" / "approvals"


def _now():
    return datetime.now(timezone.utc).isoformat()


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def create_request(workspace, room_id, kind, question, options=None, summary=""):
    root = _root(workspace)
    root.mkdir(parents=True, exist_ok=True)
    for path in root.glob("*.json"):
        try:
            item = _read(path)
            if item.get("status") == "pending" and item.get("room") == room_id and item.get("kind") == kind:
                return str(item["id"])
        except (OSError, ValueError, TypeError):
            continue
    choices = list(options) if options is not None else ["yes", "no"]
    if not choices:
        raise ValueError("Approval options must not be empty")
    request_id = secrets.token_hex(4)
    item = {
        "id": request_id,
        "room": str(room_id),
        "kind": str(kind),
        "question": str(question),
        "options": choices,
        "summary": str(summary),
        "status": "pending",
        "created_at": _now(),
    }
    _write(root / (request_id + ".json"), item)
    return request_id


def answer(workspace, request_id, choice):
    request_id = str(request_id)
    if not request_id or any(ch not in "0123456789abcdefABCDEF" for ch in request_id):
        raise ValueError("Unknown approval request id: " + request_id)
    path = _root(workspace) / (request_id + ".json")
    if not path.is_file():
        raise ValueError("Unknown approval request id: " + request_id)
    item = _read(path)
    if item.get("status") != "pending":
        raise ValueError("Approval request " + request_id + " has already been answered")
    options = item.get("options", ["yes", "no"])
    if choice not in options:
        raise ValueError("Invalid choice " + repr(choice) + "; available options: " + ", ".join(map(str, options)))
    item["status"] = "answered"
    item["choice"] = choice
    item["answered_at"] = _now()
    _write(path, item)
    return item


def get_answer(workspace, request_id):
    if not request_id:
        return None
    path = _root(workspace) / (str(request_id) + ".json")
    try:
        item = _read(path)
        return item.get("choice") if item.get("status") == "answered" else None
    except (OSError, ValueError, TypeError):
        return None


def list_requests(workspace, pending_only=True):
    root = _root(workspace)
    output = []
    try:
        paths = list(root.glob("*.json"))
    except OSError:
        paths = []
    for path in paths:
        try:
            item = _read(path)
            if not isinstance(item, dict):
                continue
            if pending_only and item.get("status") != "pending":
                continue
            output.append(item)
        except (OSError, ValueError, TypeError):
            continue
    output.sort(key=lambda item: str(item.get("created_at", "")))
    return output
