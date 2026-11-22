"""Safety helpers for the autonomous engine.

- Daily search budget: Tavily basic search costs 1 credit per call. The default
  daily cap keeps monthly use well under the 1,000-credit free allowance.
- Clean environment: test runs get no API keys or other secrets.
"""

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

SEARCH_DAILY_LIMIT = int(os.getenv("AI_HOUSE_SEARCH_DAILY_LIMIT", "25"))
SECRET_MARKERS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")


def _today():
    return datetime.now(timezone.utc).date().isoformat()


def _read_budget(path: Path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    if data.get("date") != _today():
        data = {"date": _today(), "count": 0}
    return data


def search_allowed(budget_file: Path) -> bool:
    """True if today's search count is still under the daily limit."""
    return _read_budget(budget_file)["count"] < SEARCH_DAILY_LIMIT


def record_search(budget_file: Path):
    """Count one search against today's budget."""
    data = _read_budget(budget_file)
    data["count"] += 1
    budget_file.parent.mkdir(parents=True, exist_ok=True)
    budget_file.write_text(json.dumps(data), encoding="utf-8")


def clean_env():
    """Environment for generated code: everything except secret-looking variables."""
    return {k: v for k, v in os.environ.items()
            if not any(marker in k.upper() for marker in SECRET_MARKERS)}


def run_pytest(cwd: Path, timeout: int = 240):
    """Run pytest in the workspace with no secrets in the environment."""
    try:
        p = subprocess.run(
            ["python", "-m", "pytest"],
            cwd=cwd, capture_output=True, text=True, timeout=timeout,
            shell=False, env=clean_env(),
        )
        return {"cmd": "python -m pytest", "exit": p.returncode,
                "output": (p.stdout + p.stderr)[-7000:]}
    except Exception as e:
        return {"cmd": "python -m pytest", "exit": -1, "output": str(e)}
