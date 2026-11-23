"""Local desktop control for AI House with deterministic action gates.

Runs only on the user's machine through the local dashboard. It is not a remote
shell. App launching is allowlisted; high-impact actions require an owner approval.
"""
import base64
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from approvals import create_request, get_answer, list_requests

SAFE_HOTKEYS = {
    ("ctrl", "c"), ("ctrl", "v"), ("ctrl", "x"), ("ctrl", "a"),
    ("ctrl", "f"), ("ctrl", "s"), ("ctrl", "z"), ("ctrl", "y"),
    ("ctrl", "shift", "s"), ("ctrl", "tab"), ("alt", "tab"),
    ("home",), ("end",), ("pageup",), ("pagedown",),
}
HIGH_RISK_WORDS = {
    "send", "submit", "publish", "upload", "purchase", "buy", "pay",
    "delete", "remove", "install", "uninstall", "transfer", "deploy",
    "share", "invite", "change_password", "change_permissions", "post",
}
ALLOWED_ACTIONS = {"screenshot", "click", "move", "type", "hotkey", "scroll", "launch_app"}


class ComputerUseError(ValueError):
    pass


def _config(workspace):
    path = Path(workspace).resolve() / ".ai-house" / "computer_apps.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    return data if isinstance(data, dict) else {}


def status(workspace):
    config = _config(workspace)
    return {
        "available": os.name == "nt" or sys.platform in ("darwin", "linux"),
        "backend": "PyAutoGUI (local desktop)",
        "configured_apps": sorted(k for k, v in config.get("apps", {}).items() if isinstance(v, str) and v.strip()),
        "fail_safe": True,
        "owner_approval_for_risky_actions": True,
    }


def _pyautogui():
    try:
        import pyautogui
    except ImportError as exc:
        raise ComputerUseError("Install the desktop dependency with: pip install -r worker/requirements.txt") from exc
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.15
    return pyautogui


def _clean_action(action):
    if not isinstance(action, dict):
        raise ComputerUseError("action must be an object")
    kind = str(action.get("kind", "")).strip().lower()
    if kind not in ALLOWED_ACTIONS:
        raise ComputerUseError("unsupported desktop action")
    clean = {"kind": kind}
    if kind in ("click", "move"):
        try:
            clean["x"], clean["y"] = int(action["x"]), int(action["y"])
        except (KeyError, TypeError, ValueError):
            raise ComputerUseError("click/move requires integer x and y")
        if not (0 <= clean["x"] <= 10000 and 0 <= clean["y"] <= 10000):
            raise ComputerUseError("coordinates out of range")
        clean["button"] = str(action.get("button", "left")).lower()
        if clean["button"] not in ("left", "right", "middle"):
            raise ComputerUseError("unsupported mouse button")
    elif kind == "type":
        clean["text"] = str(action.get("text", ""))[:10000]
        if not clean["text"]:
            raise ComputerUseError("text cannot be empty")
    elif kind == "hotkey":
        keys = action.get("keys")
        if not isinstance(keys, list) or not 1 <= len(keys) <= 4:
            raise ComputerUseError("hotkey keys must be a list of 1-4 keys")
        clean["keys"] = tuple(str(k).lower() for k in keys)
    elif kind == "scroll":
        try:
            clean["amount"] = max(-20, min(20, int(action.get("amount", 0))))
        except (TypeError, ValueError):
            raise ComputerUseError("scroll amount must be an integer")
    elif kind == "launch_app":
        clean["app"] = str(action.get("app", "")).strip()[:80]
        if not clean["app"]:
            raise ComputerUseError("app alias is required")
    clean["intent"] = str(action.get("intent", ""))[:500]
    clean["target"] = str(action.get("target", ""))[:200]
    return clean


def _risk_reason(action):
    kind = action["kind"]
    intent = (action.get("intent", "") + " " + action.get("target", "")).lower()
    tokens = {word.strip(".,:;!?()[]{}") for word in intent.split()}
    if tokens & HIGH_RISK_WORDS:
        return "High-impact desktop action: " + ", ".join(sorted(tokens & HIGH_RISK_WORDS))
    if kind == "hotkey" and action.get("keys") not in SAFE_HOTKEYS:
        return "Unlisted keyboard shortcut requires owner review."
    return None


def _digest(action):
    raw = json.dumps(action, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def execute(workspace, action, approval_id=None):
    clean = _clean_action(action)
    reason = _risk_reason(clean)
    digest = _digest(clean)
    if reason:
        if not approval_id or get_answer(workspace, approval_id) != "yes":
            request_id = create_request(
                workspace, "computer", "desktop_action",
                "AI House requests permission to perform: " + reason,
                options=["yes", "no"],
                summary="action_sha256:" + digest,
            )
            return {"status": "approval_required", "approval_id": request_id, "reason": reason}
        req = next((r for r in list_requests(workspace, pending_only=False) if r.get("id") == approval_id), None)
        if not req or req.get("summary") != "action_sha256:" + digest or req.get("room") != "computer":
            raise ComputerUseError("approval does not match this exact action")
    pg = _pyautogui()
    kind = clean["kind"]
    if kind == "screenshot":
        image = pg.screenshot()
        from io import BytesIO
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return {"status": "ok", "image_png_base64": base64.b64encode(buffer.getvalue()).decode("ascii"), "width": image.width, "height": image.height}
    if kind == "click":
        pg.click(clean["x"], clean["y"], button=clean["button"])
    elif kind == "move":
        pg.moveTo(clean["x"], clean["y"], duration=0.2)
    elif kind == "type":
        pg.write(clean["text"], interval=0.015)
    elif kind == "hotkey":
        if clean["keys"] not in SAFE_HOTKEYS and not approval_id:
            raise ComputerUseError("hotkey was not approved by the local policy")
        pg.hotkey(*clean["keys"])
    elif kind == "scroll":
        pg.scroll(clean["amount"])
    elif kind == "launch_app":
        apps = _config(workspace).get("apps", {})
        app_path = apps.get(clean["app"])
        if not isinstance(app_path, str) or not app_path.strip():
            raise ComputerUseError("app alias is not configured in workspace/.ai-house/computer_apps.json")
        target = Path(app_path).expanduser().resolve()
        if not target.is_file():
            raise ComputerUseError("configured application path does not exist")
        # No shell and no caller-supplied command-line arguments.
        subprocess.Popen([str(target)], shell=False, close_fds=True)
    return {"status": "ok", "action": kind}
