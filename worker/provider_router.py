"""Provider/model routing helpers for resilient local AI House execution."""
from __future__ import annotations

def rotate(items, cursor=0):
    values=list(dict.fromkeys(x for x in items if x))
    if not values:
        return []
    offset=int(cursor or 0)%len(values)
    return values[offset:]+values[:offset]

def model_pool(primary, configured=""):
    values=[]
    for value in [primary]+str(configured or "").split(","):
        value=str(value or "").strip()
        if value and value not in values:
            values.append(value)
    return values

def gemini_chat_model_pool(catalog_ids, preferred=()):
    """Order all catalog-verified Gemini/Gemma chat models for task fallback.

    The caller's catalog is already filtered to generateContent-capable models.
    Exclude specialized audio, image, video, embedding, and realtime endpoints
    from ordinary text-agent requests.
    """
    excluded=("embedding", "imagen", "image", "veo", "audio", "live", "transcribe", "tts", "robotics", "video", "speech", "translate", "music", "lyria", "nano-banana", "antigravity", "deep-research", "computer-use", "spatial")
    available=list(dict.fromkeys(str(x).strip().removeprefix("models/") for x in catalog_ids if str(x).strip()))
    available=[x for x in available if not any(token in x.lower() for token in excluded)]
    preferred_order=[x for x in model_pool("", ",".join(preferred)) if x in available]
    rest=[x for x in available if x not in preferred_order]
    def rank(model):
        name=model.lower()
        if "flash-lite" in name:return (0,name)
        if "flash" in name:return (1,name)
        if "gemma" in name:return (2,name)
        if "pro" in name:return (3,name)
        return (4,name)
    return preferred_order+sorted(rest,key=rank)

def provider_chat_model_pool(provider, catalog_ids, preferred=(), free_ids=()):
    """Build a broad, text-chat-only provider pool from live catalog IDs."""
    excluded=("embedding", "embed-", "-embed", "rerank", "whisper", "transcription", "transcribe", "tts", "text-to-speech", "speech", "audio", "image-generation", "text-to-image", "video-generation", "text-to-video", "moderation-only", "deep-research", "computer-use", "antigravity", "lyria", "nano-banana", "robotics")
    available=list(dict.fromkeys(str(x).strip() for x in catalog_ids if str(x).strip()))
    available=[x for x in available if not any(token in x.lower() for token in excluded)]
    available_set=set(available)
    free=[x for x in dict.fromkeys(free_ids or ()) if x in available_set]
    preferred_order=[x for x in model_pool("", ",".join(preferred)) if x in available_set and x not in free]
    remaining=[x for x in available if x not in free and x not in preferred_order]
    def rank(model):
        name=model.lower()
        if any(token in name for token in ("flash-lite","flash_lite","-mini","_mini","-small","_small","-fast","_fast")):return (0,name)
        if any(token in name for token in ("8b","9b","12b","14b","20b","24b","32b")):return (1,name)
        if any(token in name for token in ("70b","72b","110b","120b","405b","550b")):return (3,name)
        return (2,name)
    remaining.sort(key=rank)
    if provider=="openrouter":return free+preferred_order+remaining
    return preferred_order+remaining

def is_model_specific_error(error):
    message=str(error).lower()
    return any(token in message for token in (
        "model_not_found","model not found","unknown model","invalid model",
        "model does not exist","model_id_not_found","unsupported model",
        "404 not found","404 page not found","410","gone","end of life",
        "retired","no such model", "developer instruction is not enabled",
        "not enabled for models", "unsupported developer instruction"
    ))

def filter_model_pool(candidates, available=None, unavailable=(), allow_unlisted=()):
    """Keep candidate order while filtering to live catalog IDs and cached dead IDs."""
    values=list(dict.fromkeys(str(x).strip() for x in candidates if str(x).strip()))
    blocked=set(unavailable or ())
    allowed_unlisted=set(allow_unlisted or ())
    if available is not None:
        allowed=set(available or ())
        values=[x for x in values if x in allowed or x in allowed_unlisted]
    return [x for x in values if x not in blocked]

def is_unavailable_model_error(error):
    message=str(error).lower()
    return any(token in message for token in (
        "410","gone","end of life","reached its end of life","retired",
        "model_not_found","model not found","unknown model","unsupported model",
        "404","does not exist","no such model", "developer instruction is not enabled",
        "not enabled for models", "unsupported developer instruction"
    ))

def cooldown_seconds(error, quota=900, billing=86400, config=3600, timeout=60, server=90):
    message=str(error).lower()
    if "daily free allocation" in message or "neurons" in message:
        return 21600
    if any(token in message for token in ("1113", "insufficient balance", "no resource package", "please recharge", "requires a valid credit card", "credit card on file")):
        return int(billing)
    if any(token in message for token in ("50609", "system is too busy", "system too busy", "high demand")):
        return int(server)
    if any(token in message for token in ("402","payment required","insufficient credits","pre-paid credits","billing limit","credits exhausted")):
        return int(billing)
    if any(token in message for token in ("401","403","unauthorized","invalid api key","authentication failed","permission denied")):
        return int(config)
    if any(token in message for token in ("daily free allocation", "neurons", "429","quota","rate limit","resource_exhausted","usage limit","daily limit","monthly limit","capacity exhausted")):
        return int(quota)
    if any(token in message for token in ("model_not_found","model not found","unknown model","invalid model","model does not exist","404 not found")):
        return int(config)
    if any(token in message for token in ("timeout","timed out","read operation")):
        return int(timeout)
    if any(token in message for token in ("503","502","500","temporarily unavailable","service unavailable")):
        return int(server)
    return 0

def openrouter_free_model_ids(rows):
    """Return catalog-listed OpenRouter models that are explicitly free-priced."""
    result=[]
    for item in rows or []:
        if not isinstance(item,dict):
            continue
        model_id=str(item.get("id") or "").strip()
        pricing=item.get("pricing") or {}
        try:
            prompt=float(pricing.get("prompt",-1))
            completion=float(pricing.get("completion",-1))
        except (TypeError,ValueError):
            prompt=completion=-1
        if model_id and (model_id.endswith(":free") or (prompt==0 and completion==0)) and model_id not in result:
            result.append(model_id)
    return result

def is_openrouter_credit_model_error(provider,error):
    message=str(error).lower()
    return provider=="openrouter" and ("402" in message or "insufficient credits" in message or "can only afford" in message) and any(token in message for token in ("credit","afford","payment","balance"))

def is_provider_wide_error(provider,error):
    """Identify failures that cannot be fixed by switching model IDs."""
    message=str(error).lower()
    if provider=="zai" and any(token in message for token in ("1113", "insufficient balance", "no resource package", "please recharge")):
        return True
    if provider=="vercel" and any(token in message for token in ("requires a valid credit card", "credit card on file")):
        return True
    if any(token in message for token in (
        "402", "payment required", "insufficient credits", "pre-paid credits",
        "billing limit", "credits exhausted", "account balance",
    )):
        return True
    if any(token in message for token in (
        "401", "403", "unauthorized", "invalid api key",
        "authentication failed", "permission denied",
    )):
        return True
    if any(token in message for token in (
        "daily free allocation", "neurons", "account quota", "account-level quota", "daily quota",
        "monthly quota", "daily limit", "monthly limit",
        "provider-wide quota", "shared quota exhausted",
    )):
        return True
    if provider=="openrouter" and "429" in message and any(token in message for token in (
        "free-models-per-day", "free models per day", "free model daily",
        "free-model daily", "daily free-model quota", "free model quota",
    )):
        return True
    return False

def should_try_next_model(error):
    """Model errors, transient failures and per-model rate limits should try another model.

    Stop only for credentials, permissions or account-level billing failures.
    """
    message=str(error).lower()
    return not any(token in message for token in (
        "401", "403", "402", "unauthorized", "invalid api key",
        "authentication failed", "permission denied", "insufficient credits",
        "pre-paid credits", "payment required", "billing limit",
        "free-models-per-day", "free models per day", "daily quota",
        "account quota", "monthly quota", "daily limit", "shared quota exhausted",
        "1113", "insufficient balance", "no resource package", "please recharge",
        "requires a valid credit card", "credit card on file",
    ))
