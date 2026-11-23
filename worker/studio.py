"""AI House Studio: durable YouTube and marketing workflows with owner approval gates.

This module manages project metadata and workflow state only. It does not claim to
render videos, upload to YouTube, or publish campaigns; those require connected
production/publishing adapters.
"""
import json
import re
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


def decide_approval(workspace, approval_id, decision, note=""):
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
