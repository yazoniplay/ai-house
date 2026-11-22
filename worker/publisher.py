"""Conservative publisher for owner-approved listings and owned static websites.

Gumroad is deliberately fail-closed until its current product-creation API
contract can be verified from readable official documentation.
"""
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

def _now():
    return datetime.now(timezone.utc)

def _stamp():
    return _now().isoformat()

def _read_json(path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return default

def _append_jsonl(path, row):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")

def _event(meta, name, **fields):
    _append_jsonl(meta / "events.jsonl", {"at": _stamp(), "event": name, **fields})

def _platform_config(config, platform):
    platforms = config.get("platforms")
    if isinstance(platforms, dict) and isinstance(platforms.get(platform), dict):
        return platforms[platform]
    value = config.get(platform)
    return value if isinstance(value, dict) else {}

def _safe_slug(value):
    slug = re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-")
    return (slug or "listing")[:80]

def _approval_and_rules(item, workspace):
    approval = item.get("reviewer_approval", item.get("review"))
    approved = item.get("reviewer_approved") is True
    if isinstance(approval, dict):
        approved = approved or str(approval.get("decision", approval.get("status", ""))).lower() in ("approve", "approved")
    if not approved:
        return False, "reviewer_not_approved"

    rules = item.get("platform_rules")
    rules_file = item.get("platform_rules_file")
    if isinstance(rules_file, str) and rules_file.strip():
        p = (workspace / rules_file).resolve()
        root = workspace.resolve()
        if p != root and root not in p.parents:
            return False, "platform_rules_path_outside_workspace"
        rules = _read_json(p)
    if not isinstance(rules, dict):
        return False, "platform_rules_missing"
    result = str(rules.get("result", rules.get("decision", rules.get("status", "")))).lower()
    passed = rules.get("passed") is True or result in ("pass", "passed", "approved", "ok")
    if not passed:
        return False, "platform_rules_not_passed"
    return True, ""

def _daily_count(log_path, platform, today):
    count = 0
    try:
        with log_path.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    row = json.loads(line)
                    stamp = datetime.fromisoformat(str(row.get("timestamp", "")).replace("Z", "+00:00"))
                    if stamp.tzinfo is None:
                        stamp = stamp.replace(tzinfo=timezone.utc)
                    if row.get("platform") == platform and stamp.astimezone(timezone.utc).date() == today:
                        count += 1
                except (ValueError, TypeError, json.JSONDecodeError):
                    continue
    except OSError:
        pass
    return count

def _publish_website(item, config, workspace):
    folder_value = config.get("folder", config.get("static_folder"))
    if not isinstance(folder_value, str) or not folder_value.strip():
        raise ValueError("website_folder_missing")
    folder = Path(folder_value).expanduser()
    if not folder.is_absolute():
        folder = workspace / folder
    folder = folder.resolve()
    folder.mkdir(parents=True, exist_ok=True)

    base_url = str(config.get("base_url", "")).strip().rstrip("/")
    if not base_url.startswith(("https://", "http://")):
        raise ValueError("website_base_url_missing")

    html = item.get("html", item.get("content"))
    if not isinstance(html, str) or not html.strip():
        raise ValueError("website_html_missing")
    ident = item.get("slug") or item.get("id") or item.get("title") or "listing"
    filename = _safe_slug(ident) + ".html"
    target = (folder / filename).resolve()
    if target.parent != folder:
        raise ValueError("website_path_outside_configured_folder")

    # Exclusive creation means existing files (including files not made by us)
    # are never overwritten. It also fails safely if a competing writer wins.
    created = False
    try:
        with target.open("x", encoding="utf-8", newline="") as f:
            created = True
            f.write(html)
    except Exception:
        if created:
            try:
                target.unlink()
            except OSError:
                pass
        raise
    return base_url + "/" + filename.lstrip("/"), target

def run_publisher(workspace: Path, http) -> int:
    """Publish approved ready queue items to explicitly enabled owner channels."""
    workspace = Path(workspace).resolve()
    meta = workspace / ".ai-house"
    config_path = meta / "publish_config.json"
    config = _read_json(config_path)
    if not isinstance(config, dict) or config.get("enabled") is not True:
        return 0

    queue_path = meta / "publish_queue.json"
    queue = _read_json(queue_path)
    if not isinstance(queue, list):
        return 0

    state_path = meta / "publish_state.json"
    state = _read_json(state_path, {})
    if not isinstance(state, dict):
        state = {}
    platform_state = state.setdefault("platforms", {})
    if not isinstance(platform_state, dict):
        platform_state = {}
        state["platforms"] = platform_state

    log_path = meta / "publish_log.jsonl"
    published = 0
    today = _now().date()

    for item in queue:
        if not isinstance(item, dict) or item.get("status") != "ready":
            continue
        platform = str(item.get("platform", "")).lower()
        if platform not in ("gumroad", "website"):
            _event(meta, "publish_skipped", platform=platform or "unknown", item=item.get("id"), reason="platform_not_allowed")
            continue

        pc = _platform_config(config, platform)
        if pc.get("enabled") is not True:
            continue

        ps = platform_state.setdefault(platform, {"consecutive_failures": 0, "auto_paused": False})
        if not isinstance(ps, dict):
            ps = {"consecutive_failures": 0, "auto_paused": False}
            platform_state[platform] = ps

        # Auto-pause is cleared only by an explicit config edit to paused:false.
        if ps.get("auto_paused") and pc.get("paused") is False:
            ps["auto_paused"] = False
            ps["consecutive_failures"] = 0
            _event(meta, "publish_resumed", platform=platform, reason="owner_unpaused_in_config")
        if pc.get("paused") is True or ps.get("auto_paused"):
            continue

        cap_value = pc.get("daily_cap", 2)
        try:
            cap = max(0, int(cap_value))
        except (TypeError, ValueError):
            cap = 2
        if _daily_count(log_path, platform, today) >= cap:
            _event(meta, "publish_skipped", platform=platform, item=item.get("id"), reason="daily_cap")
            continue

        ok, reason = _approval_and_rules(item, workspace)
        if not ok:
            _event(meta, "publish_skipped", platform=platform, item=item.get("id"), reason=reason)
            continue

        content = item.get("html", item.get("content", ""))
        if not isinstance(content, str):
            content = json.dumps(content, ensure_ascii=False)
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

        try:
            if platform == "gumroad":
                # Official docs are currently not sufficiently readable to verify
                # the product-create endpoint and payload. Never guess a write API.
                _event(meta, "publish_skipped", platform=platform, item=item.get("id"), reason="api_unverified")
                continue

            url, created_path = _publish_website(item, pc, workspace)
            stamp = _stamp()
            try:
                _append_jsonl(log_path, {"timestamp": stamp, "platform": platform, "url": url, "content_hash": content_hash})
            except Exception:
                # Roll back the newly created page if its required publication
                # record could not be written, allowing a safe retry next pass.
                try:
                    created_path.unlink()
                except OSError:
                    pass
                raise
            item["status"] = "published"
            item["url"] = url
            item["published_at"] = stamp
            item["content_hash"] = content_hash
            ps["consecutive_failures"] = 0
            ps["auto_paused"] = False
            published += 1
            _event(meta, "publish_succeeded", platform=platform, item=item.get("id"), url=url, content_hash=content_hash)
        except Exception as exc:
            ps["consecutive_failures"] = int(ps.get("consecutive_failures", 0)) + 1
            _event(meta, "publish_failed", platform=platform, item=item.get("id"), failures=ps["consecutive_failures"], error=str(exc)[:400])
            if ps["consecutive_failures"] >= 3 and not ps.get("auto_paused"):
                ps["auto_paused"] = True
                _event(meta, "publish_paused", platform=platform, failures=ps["consecutive_failures"], reason="three_consecutive_failures")

    # Persist queue and failure/pause state atomically.
    queue_tmp = queue_path.with_suffix(".tmp")
    queue_tmp.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")
    queue_tmp.replace(queue_path)
    state_tmp = state_path.with_suffix(".tmp")
    state_tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    state_tmp.replace(state_path)
    return published
