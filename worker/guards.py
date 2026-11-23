"""Safety helpers for the autonomous engine.

- Daily search budget: Tavily basic search costs 1 credit per call. The default
  daily cap keeps monthly use well under the 1,000-credit free allowance.
- Clean environment: test runs get no API keys or other secrets.
"""

import json
import os
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

def search_daily_limit():
    return int(os.getenv("AI_HOUSE_SEARCH_DAILY_LIMIT", "33"))

def search_monthly_limit():
    return int(os.getenv("AI_HOUSE_SEARCH_MONTHLY_LIMIT", "950"))

SECRET_MARKERS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")


def _today():
    return datetime.now(timezone.utc).date().isoformat()


def _read_budget(path: Path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    today = _today()
    month = today[:7]
    if data.get("date") != today:
        data["date"] = today
        data["count"] = 0
    if data.get("month") != month:
        data["month"] = month
        data["month_count"] = 0
    data.setdefault("count", 0)
    data.setdefault("month_count", 0)
    return data


def search_allowed(budget_file: Path) -> bool:
    data = _read_budget(budget_file)
    return data["count"] < search_daily_limit() and data["month_count"] < search_monthly_limit()


def record_search(budget_file: Path):
    data = _read_budget(budget_file)
    data["count"] += 1
    data["month_count"] += 1
    budget_file.parent.mkdir(parents=True, exist_ok=True)
    budget_file.write_text(json.dumps(data), encoding="utf-8")


def next_utc_midnight():
    now = datetime.now(timezone.utc)
    return (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)


def spend_daily_cap():
    return float(os.getenv("AI_HOUSE_DAILY_SPEND_CAP_USD", "0"))

def spend_monthly_cap():
    return float(os.getenv("AI_HOUSE_MONTHLY_SPEND_CAP_USD", "0"))

def _spend_path(budget_file: Path):
    return budget_file.parent / "spend-ledger.json"

def _read_spend(budget_file: Path):
    path = _spend_path(budget_file)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    today = _today()
    month = today[:7]
    if data.get("date") != today:
        data["date"] = today
        data["day_usd"] = 0.0
    if data.get("month") != month:
        data["month"] = month
        data["month_usd"] = 0.0
    data.setdefault("day_usd", 0.0)
    data.setdefault("month_usd", 0.0)
    return data, path

def spend_allowed(budget_file: Path, estimated_usd: float = 0.0) -> bool:
    data, _ = _read_spend(budget_file)
    return (data["day_usd"] + estimated_usd <= spend_daily_cap()
            and data["month_usd"] + estimated_usd <= spend_monthly_cap())

def record_spend(budget_file: Path, usd: float):
    data, path = _read_spend(budget_file)
    data["day_usd"] = round(data["day_usd"] + usd, 6)
    data["month_usd"] = round(data["month_usd"] + usd, 6)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


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
