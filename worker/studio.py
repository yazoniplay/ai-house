"""AI House Studio: durable YouTube and marketing workflows with owner approval gates.

This module manages project metadata and workflow state only. It does not claim to
render videos, upload to YouTube, or publish campaigns; those require connected
production/publishing adapters.
"""
import json
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

YOUTUBE_STAGES = [
    "idea", "research", "script", "storyboard", "assets", "editing",
    "review", "approval_pending", "approved", "published",
]
MARKETING_STAGES = [
    "brief", "research", "strategy", "content_drafts", "campaign_review",
    "approval_pending", "approved", "published", "analysis",
]
STAGES = {"youtube": YOUTUBE_STAGES, "marketing": MARKETING_STAGES}


class StudioError(ValueError):
    """Invalid or unsafe Studio operation."""


def _now():
    return datetime.now(timezone.utc).isoformat()


def _store(workspace):
    return Path(workspace).resolve() / ".ai-house" / "studio" / "projects.json"


def _read(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {"projects": [], "approvals": []}
    if not isinstance(data, dict):
        data = {"projects": [], "approvals": []}
    data.setdefault("projects", [])
    data.setdefault("approvals", [])
    return data


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    temp.replace(path)


def list_projects(workspace, kind=None):
    data = _read(_store(workspace))
    projects = data["projects"]
    if kind is not None:
        if kind not in STAGES:
            raise StudioError("kind must be youtube or marketing")
        projects = [p for p in projects if p.get("kind") == kind]
    return sorted(projects, key=lambda p: p.get("updated_at", ""), reverse=True)


def list_approvals(workspace, pending_only=True):
    items = _read(_store(workspace))["approvals"]
    if pending_only:
        items = [a for a in items if a.get("status") == "pending"]
    return sorted(items, key=lambda a: a.get("created_at", ""), reverse=True)


def create_project(workspace, kind, title, owner="owner", brief=""):
    if kind not in STAGES:
        raise StudioError("kind must be youtube or marketing")
    title = str(title or "").strip()
    if not title or len(title) > 180:
        raise StudioError("title is required and must be at most 180 characters")
    project = {
        "id": uuid.uuid4().hex[:12],
        "kind": kind,
        "title": title,
        "owner": str(owner or "owner")[:80],
        "brief": str(brief or "")[:12000],
        "stage": STAGES[kind][0],
        "status": "active",
        "artifacts": [],
        "notes": [],
        "created_at": _now(),
        "updated_at": _now(),
    }
    path = _store(workspace)
    data = _read(path)
    data["projects"].append(project)
    _write(path, data)
    return project


def update_project(workspace, project_id, fields):
    if not isinstance(fields, dict):
        raise StudioError("fields must be an object")
    allowed = {"brief", "notes", "artifacts", "owner"}
    if set(fields) - allowed:
        raise StudioError("only brief, notes, artifacts, and owner can be edited")
    path = _store(workspace)
    data = _read(path)
    project = next((p for p in data["projects"] if p.get("id") == project_id), None)
    if project is None:
        raise StudioError("project not found")
    for key, value in fields.items():
        if key == "brief":
            project[key] = str(value or "")[:12000]
        elif key == "owner":
            project[key] = str(value or "owner")[:80]
        elif key == "notes":
            if not isinstance(value, list):
                raise StudioError("notes must be a list")
            project[key] = [str(x)[:2000] for x in value][-100:]
        elif key == "artifacts":
            if not isinstance(value, list):
                raise StudioError("artifacts must be a list")
            safe = []
            for item in value:
                if not isinstance(item, dict) or not item.get("path"):
                    raise StudioError("each artifact must contain a workspace-relative path")
                p = Path(str(item["path"]))
                if p.is_absolute() or ".." in p.parts:
                    raise StudioError("artifact path must stay inside the workspace")
                safe.append({"path": p.as_posix(), "label": str(item.get("label", p.name))[:160]})
            project[key] = safe[-100:]
    project["updated_at"] = _now()
    _write(path, data)
    return project


def move_stage(workspace, project_id, stage):
    path = _store(workspace)
    data = _read(path)
    project = next((p for p in data["projects"] if p.get("id") == project_id), None)
    if project is None:
        raise StudioError("project not found")
    stages = STAGES.get(project.get("kind"))
    if stage not in stages:
        raise StudioError("stage is not valid for this project")
    current = project.get("stage")
    current_index = stages.index(current)
    next_index = stages.index(stage)
    if next_index != current_index + 1:
        raise StudioError("move one stage at a time; workflow history must stay auditable")
    if stage in ("approval_pending",):
        approval = {
            "id": uuid.uuid4().hex[:12],
            "project_id": project_id,
            "project_title": project["title"],
            "kind": project["kind"],
            "requested_action": "publish",
            "status": "pending",
            "created_at": _now(),
            "decided_at": None,
            "decision_note": "",
        }
        data["approvals"].append(approval)
        project["approval_id"] = approval["id"]
    if stage == "published":
        approval = next((a for a in data["approvals"] if a.get("id") == project.get("approval_id")), None)
        if not approval or approval.get("status") != "approved":
            raise StudioError("owner approval is required before publishing")
        project["publication_note"] = "Marked published by an authorized owner action; external upload is not performed by Studio."
    project["stage"] = stage
    project["updated_at"] = _now()
    _write(path, data)
    return project


def decide_approval(workspace, approval_id, decision, note="", actor="leader"):
    if decision not in ("approve", "reject"):
        raise StudioError("decision must be approve or reject")
    path = _store(workspace)
    data = _read(path)
    approval = next((a for a in data["approvals"] if a.get("id") == approval_id), None)
    if approval is None:
        raise StudioError("approval not found")
    if approval.get("status") != "pending":
        raise StudioError("approval has already been decided")
    approval["status"] = "approved" if decision == "approve" else "rejected"
    approval["decision_actor"] = str(actor or "leader")[:80]
    approval["decision_note"] = str(note or "")[:2000]
    approval["decided_at"] = _now()
    project = next((p for p in data["projects"] if p.get("id") == approval.get("project_id")), None)
    if project:
        if decision == "approve":
            project["stage"] = "approved"
        else:
            project["stage"] = "review" if project["kind"] == "youtube" else "campaign_review"
        project["updated_at"] = _now()
    _write(path, data)
    return approval



def leader_review_approval(workspace, approval_id):
    """Ask the actual AI House orchestrator to review Studio work and record its decision."""
    path = _store(workspace)
    data = _read(path)
    approval = next((a for a in data["approvals"] if a.get("id") == approval_id), None)
    if approval is None:
        raise StudioError("approval not found")
    if approval.get("status") != "pending":
        raise StudioError("approval has already been decided")
    project = next((p for p in data["projects"] if p.get("id") == approval.get("project_id")), None)
    if project is None:
        raise StudioError("project not found")
    root = Path(workspace).resolve()
    evidence = []
    for item in project.get("artifacts", []):
        rel = Path(str(item.get("path", "")))
        if not rel.parts or rel.is_absolute() or ".." in rel.parts:
            continue
        target = (root / rel).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            continue
        if not target.is_file():
            evidence.append({"path": rel.as_posix(), "exists": False})
            continue
        try:
            raw = target.read_text(encoding="utf-8", errors="replace")
            evidence.append({"path": rel.as_posix(), "exists": True, "content": raw[:12000]})
        except OSError:
            evidence.append({"path": rel.as_posix(), "exists": False})
    prompt = (
        "Review this AI House Studio approval as the accountable Leader/CEO. "
        "You, not the owner, decide routine production quality. Inspect evidence and reject or return work "
        "for revision when deliverables are missing, unsafe, misleading, infringing, or not ready. "
        "Do not claim external publishing happened. For publishing requests, approve only if the requested "
        "asset is complete and the connected channel is intended; the actual publisher still must enforce "
        "channel permissions and use private/unlisted defaults where applicable. "
        "Return strict JSON with decision (approve|reject), reason, and required_changes.\n"
        "Approval: " + json.dumps(approval, ensure_ascii=False) +
        "\nProject: " + json.dumps(project, ensure_ascii=False) +
        "\nPhysical artifact evidence: " + json.dumps(evidence, ensure_ascii=False)[:30000]
    )
    try:
        worker_dir = str(Path(__file__).resolve().parent)
        if worker_dir not in sys.path:
            sys.path.insert(0, worker_dir)
        import autonomous_engine
        result = autonomous_engine.leader_json(prompt)
        decision = str(result.get("decision", "")).lower()
        if decision not in ("approve", "reject"):
            decision = "reject"
        note = str(result.get("reason", ""))[:1800]
        changes = result.get("required_changes", [])
        if changes:
            note += "\\nRequired changes: " + json.dumps(changes, ensure_ascii=False)[:1000]
        return decide_approval(workspace, approval_id, decision, note, actor="AI House Leader")
    except Exception as exc:
        raise StudioError("Leader review could not complete; approval remains pending: " + str(exc)[:300])
