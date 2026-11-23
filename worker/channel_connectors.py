"""Real Gumroad and YouTube adapters for AI House.

Credentials are read only from local environment variables; never returned by status.
Publishing functions are explicit calls so the Leader can invoke them after its review.
"""
import json
import os
from pathlib import Path
from datetime import datetime, timezone
import threading
import httpx

# Daily limits persist across worker restarts. Count attempts conservatively,
# including failed API attempts, to prevent retry-based bypass.
GUMROAD_DAILY_PRODUCT_CAP = 3
YOUTUBE_DAILY_UPLOAD_CAP = 1
PUBLISH_LIMITS_FILE = Path(os.getenv("AI_HOUSE_WORKSPACE", Path(__file__).resolve().parents[1] / "workspace")).resolve() / ".ai-house" / "publish-limits.json"
_PUBLISH_LIMITS_LOCK = threading.Lock()


def _reserve_publish_slot(platform, daily_cap, limits_file=None):
    """Atomically reserve one daily publish attempt; raises ConnectorError at cap."""
    path = Path(limits_file or PUBLISH_LIMITS_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    with _PUBLISH_LIMITS_LOCK:
        with lock_path.open("a+b") as lock_file:
            if os.name == "nt":
                import msvcrt
                if os.fstat(lock_file.fileno()).st_size == 0:
                    lock_file.write(b"0")
                    lock_file.flush()
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                today = datetime.now(timezone.utc).date().isoformat()
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    if not isinstance(data, dict):
                        data = {}
                except (OSError, ValueError, TypeError):
                    data = {}
                day = data.setdefault(today, {})
                count = int(day.get(platform, 0))
                if count >= int(daily_cap):
                    raise ConnectorError(
                        f"Daily {platform} limit reached ({daily_cap} per UTC day). Try again after UTC midnight."
                    )
                day[platform] = count + 1
                # Keep a short history while preserving today's counter.
                for old_day in list(data):
                    try:
                        if (datetime.fromisoformat(old_day).date() - datetime.now(timezone.utc).date()).days < -7:
                            data.pop(old_day, None)
                    except (ValueError, TypeError):
                        data.pop(old_day, None)
                tmp = path.with_name(path.name + "." + str(os.getpid()) + ".tmp")
                tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
                tmp.replace(path)
            finally:
                if os.name == "nt":
                    lock_file.seek(0)
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

TIMEOUT = 45


class ConnectorError(RuntimeError):
    pass


def connection_status():
    return {
        "gumroad": {"connected": bool(os.getenv("GUMROAD_ACCESS_TOKEN")), "mode": "Gumroad API"},
        "youtube": {
            "connected": bool(os.getenv("YOUTUBE_ACCESS_TOKEN")),
            "mode": "YouTube Data API v3",
            "channel_id_set": bool(os.getenv("YOUTUBE_CHANNEL_ID")),
        },
    }


def _gumroad_token():
    token = os.getenv("GUMROAD_ACCESS_TOKEN", "").strip()
    if not token:
        raise ConnectorError("GUMROAD_ACCESS_TOKEN is not configured in worker/.env")
    return token


def gumroad_products():
    response = httpx.get(
        "https://api.gumroad.com/v2/products",
        params={"access_token": _gumroad_token()},
        timeout=TIMEOUT,
    )
    if response.is_error:
        raise ConnectorError(f"Gumroad products request failed ({response.status_code}): {response.text[:300]}")
    payload = response.json()
    if not payload.get("success"):
        raise ConnectorError("Gumroad rejected the products request")
    return payload.get("products", [])


def gumroad_create_product(name, price_cents, description="", published=False):
    name = str(name or "").strip()
    if not name or len(name) > 200:
        raise ConnectorError("Product name is required (max 200 characters)")
    try:
        price = int(price_cents)
    except (TypeError, ValueError):
        raise ConnectorError("price_cents must be an integer")
    if price < 0:
        raise ConnectorError("price_cents cannot be negative")
    token = _gumroad_token()
    _reserve_publish_slot("gumroad_products", GUMROAD_DAILY_PRODUCT_CAP)
    response = httpx.post(
        "https://api.gumroad.com/v2/products",
        data={
            "access_token": token,
            "name": name,
            "price": price,
            "description": str(description or "")[:10000],
            "published": "true" if published else "false",
        },
        timeout=TIMEOUT,
    )
    if response.is_error:
        raise ConnectorError(f"Gumroad create product failed ({response.status_code}): {response.text[:300]}")
    payload = response.json()
    if not payload.get("success"):
        raise ConnectorError("Gumroad rejected product creation")
    return payload.get("product", {})


def _youtube_token():
    token = os.getenv("YOUTUBE_ACCESS_TOKEN", "").strip()
    if not token:
        raise ConnectorError("YOUTUBE_ACCESS_TOKEN is not configured in worker/.env")
    return token


def youtube_channel():
    response = httpx.get(
        "https://www.googleapis.com/youtube/v3/channels",
        params={"part": "snippet", "mine": "true"},
        headers={"Authorization": "Bearer " + _youtube_token()},
        timeout=TIMEOUT,
    )
    if response.is_error:
        raise ConnectorError(f"YouTube channel request failed ({response.status_code}): {response.text[:300]}")
    items = response.json().get("items", [])
    if not items:
        raise ConnectorError("No YouTube channel is available for this OAuth account")
    item = items[0]
    return {"id": item.get("id"), "title": item.get("snippet", {}).get("title", "")}


def youtube_upload_video(file_path, title, description="", privacy_status="private", category_id="22"):
    """Upload a video using a pre-authorized OAuth access token.

    Google OAuth access tokens expire; refresh them externally and update the local
    YOUTUBE_ACCESS_TOKEN. Upload is intentionally explicit and defaults to private.
    """
    path = Path(file_path).expanduser().resolve()
    if not path.is_file():
        raise ConnectorError("Video file does not exist")
    if path.stat().st_size <= 0:
        raise ConnectorError("Video file is empty")
    if privacy_status not in ("private", "unlisted", "public"):
        raise ConnectorError("privacy_status must be private, unlisted, or public")
    title = str(title or "").strip()
    if not title or len(title) > 100:
        raise ConnectorError("YouTube title is required (max 100 characters)")
    metadata = {
        "snippet": {"title": title, "description": str(description or "")[:5000], "categoryId": str(category_id)},
        "status": {"privacyStatus": privacy_status, "selfDeclaredMadeForKids": False},
    }
    token = _youtube_token()
    _reserve_publish_slot("youtube_uploads", YOUTUBE_DAILY_UPLOAD_CAP)
    start = httpx.post(
        "https://www.googleapis.com/upload/youtube/v3/videos",
        params={"uploadType": "resumable", "part": "snippet,status"},
        headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Type": "video/*",
            "X-Upload-Content-Length": str(path.stat().st_size),
        },
        content=json.dumps(metadata),
        timeout=TIMEOUT,
    )
    if start.is_error:
        raise ConnectorError(f"YouTube upload session failed ({start.status_code}): {start.text[:300]}")
    upload_url = start.headers.get("Location")
    if not upload_url:
        raise ConnectorError("YouTube did not return a resumable upload URL")
    with path.open("rb") as video:
        uploaded = httpx.put(
            upload_url,
            content=video,
            headers={"Content-Type": "video/*", "Content-Length": str(path.stat().st_size)},
            timeout=300,
        )
    if uploaded.is_error:
        raise ConnectorError(f"YouTube video upload failed ({uploaded.status_code}): {uploaded.text[:300]}")
    result = uploaded.json()
    return {"id": result.get("id"), "url": "https://www.youtube.com/watch?v=" + str(result.get("id", "")), "privacy_status": privacy_status}
