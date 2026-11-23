"""Single-active flagship application queue for AI House Coding Room."""
import json
import secrets
from datetime import datetime, timezone
from pathlib import Path


class CodingRoomError(ValueError):
    pass


def _path(workspace):
    return Path(workspace).resolve() / ".ai-house" / "coding_room.json"


def _read(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {"projects": []}
    if not isinstance(data, dict):
        data = {"projects": []}
    data.setdefault("projects", [])
    return data


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    temp.replace(path)


def list_projects(workspace):
    items = _read(_path(workspace))["projects"]
    return sorted(items, key=lambda x: (x.get("status") != "active", x.get("created_at", "")))


def create_project(workspace, title, target_user, problem, brief, success_metric=""):
    title = str(title or "").strip()
    target_user = str(target_user or "").strip()
    problem = str(problem or "").strip()
    brief = str(brief or "").strip()
    if not title or len(title) > 160:
        raise CodingRoomError("App name is required (max 160 characters)")
    if not target_user or len(target_user) > 240:
        raise CodingRoomError("Target user is required (max 240 characters)")
    if not problem or len(problem) > 3000:
        raise CodingRoomError("Customer problem is required (max 3000 characters)")
    if not brief or len(brief) > 8000:
        raise CodingRoomError("App brief is required (max 8000 characters)")
    path = _path(workspace)
    data = _read(path)
    open_projects = [p for p in data["projects"] if p.get("status") in ("queued", "active")]
    if len(open_projects) >= 3:
        raise CodingRoomError("Coding Room keeps a small queue: one active app and at most two queued apps.")
    if any(p.get("title", "").casefold() == title.casefold() for p in open_projects):
        raise CodingRoomError("An app with this name is already queued or active")
    project = {
        "id": secrets.token_hex(6), "title": title, "target_user": target_user,
        "problem": problem, "brief": brief, "success_metric": str(success_metric or "")[:1000],
        "status": "queued", "active_room": None, "created_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": None, "result": None,
    }
    data["projects"].append(project)
    _write(path, data)
    return project


def claim_next(workspace, room_id):
    """Atomically claim one queued app; never allow two active Coding Room apps."""
    path = _path(workspace)
    data = _read(path)
    active = next((p for p in data["projects"] if p.get("status") == "active"), None)
    if active:
        return active if active.get("active_room") == str(room_id) else None
    queued = sorted((p for p in data["projects"] if p.get("status") == "queued"), key=lambda p: p.get("created_at", ""))
    if not queued:
        return None
    project = queued[0]
    project["status"] = "active"
    project["active_room"] = str(room_id)
    _write(path, data)
    return project


def complete_project(workspace, project_id, room_id, result=None):
    path = _path(workspace)
    data = _read(path)
    project = next((p for p in data["projects"] if p.get("id") == str(project_id)), None)
    if project is None:
        raise CodingRoomError("Coding Room project not found")
    if project.get("status") != "active" or project.get("active_room") != str(room_id):
        raise CodingRoomError("Only the room currently owning this app can complete it")
    project["status"] = "completed"
    project["completed_at"] = datetime.now(timezone.utc).isoformat()
    project["result"] = str(result or "")[:3000]
    _write(path, data)
    return project


def cancel_project(workspace, project_id):
    path = _path(workspace)
    data = _read(path)
    project = next((p for p in data["projects"] if p.get("id") == str(project_id)), None)
    if project is None:
        raise CodingRoomError("Coding Room project not found")
    if project.get("status") != "queued":
        raise CodingRoomError("Only queued apps can be cancelled from the owner UI")
    project["status"] = "cancelled"
    _write(path, data)
    return project
