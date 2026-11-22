"""Local dashboard for the agent house. Listens on 127.0.0.1 only.

Run from the dashboard folder:
  pip install flask
  python server.py
Then open http://127.0.0.1:8000
"""

import os
import re
import sys
import threading
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

HERE = Path(__file__).resolve().parent
WORKER_DIR = HERE.parent / "worker"
UUID_RE = re.compile(r"^[0-9a-fA-F-]{36}$")


def load_env(path):
    """Read worker/.env into the environment, without overriding existing values."""
    if not path.exists():
        raise SystemExit(f"Missing {path}. Create worker/.env first.")
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" not in line or line.lstrip().startswith("#"):
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if value and key not in os.environ:
            os.environ[key] = value


load_env(WORKER_DIR / ".env")
sys.path.insert(0, str(WORKER_DIR))
import worker  # noqa: E402  (reads its settings from the environment at import)

app = Flask(__name__)
step_lock = threading.Lock()


@app.get("/")
def index():
    return send_from_directory(HERE, "index.html")


@app.get("/api/state")
def state():
    goals = worker.sb("GET", "goals", params={
        "select": "id,text,status,question,created_at",
        "order": "created_at.desc", "limit": "20",
    }) or []
    raw_tasks = worker.sb("GET", "tasks", params={
        "select": "id,goal_id,agent_id,status,instruction,error,attempts,output,review,created_at",
        "order": "created_at.desc", "limit": "40",
    }) or []
    tasks = []
    for t in raw_tasks:
        out = t.pop("output", None) or {}
        t["provider"] = out.get("provider")
        t["output_preview"] = (out.get("text") or "")[:800]
        tasks.append(t)
    approvals = worker.sb("GET", "approvals", params={
        "select": "id,task_id,reason,decision,created_at",
        "decision": "eq.pending", "order": "created_at.desc",
    }) or []
    lessons = worker.sb("GET", "lessons", params={
        "select": "id,goal,outcome,lesson,created_at",
        "order": "created_at.desc", "limit": "10",
    }) or []
    room = worker.sb("GET", "rooms", params={
        "select": "active", "id": f"eq.{worker.DEFAULT_ROOM}",
    }) or [{"active": False}]
    return jsonify(goals=goals, tasks=tasks, approvals=approvals,
                   lessons=lessons, room_active=room[0]["active"])


@app.post("/api/goals")
def add_goal():
    text = str((request.get_json(silent=True) or {}).get("text", "")).strip()
    if not text or len(text) > 1000:
        return jsonify(error="goal text must be 1 to 1000 characters"), 400
    worker.sb("POST", "goals", json={"text": text, "room_id": worker.DEFAULT_ROOM},
              headers={"Prefer": "return=minimal"})
    return jsonify(ok=True)


@app.post("/api/approvals/<task_id>")
def decide(task_id):
    if not UUID_RE.match(task_id):
        return jsonify(error="bad task id"), 400
    approve = bool((request.get_json(silent=True) or {}).get("approve"))
    worker.sb("POST", "rpc/decide_approval", json={"p_task": task_id, "p_approve": approve})
    return jsonify(ok=True, approved=approve)


@app.post("/api/step")
def step():
    if not step_lock.acquire(blocking=False):
        return jsonify(error="a step is already running"), 409
    try:
        return jsonify(did_work=worker.run_one())
    except Exception as e:
        return jsonify(error=str(e)[:500]), 500
    finally:
        step_lock.release()


@app.post("/api/room")
def room():
    active = bool((request.get_json(silent=True) or {}).get("active"))
    worker.sb("PATCH", "rooms", params={"id": f"eq.{worker.DEFAULT_ROOM}"},
              json={"active": active}, headers={"Prefer": "return=minimal"})
    return jsonify(ok=True, active=active)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=False)
