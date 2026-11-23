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

def is_model_specific_error(error):
    message=str(error).lower()
    return any(token in message for token in (
        "model_not_found","model not found","unknown model","invalid model",
        "model does not exist","model_id_not_found","unsupported model",
        "404 not found","404 page not found","410","gone","end of life",
        "retired","no such model"
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
        "404","does not exist","no such model"
    ))

def cooldown_seconds(error, quota=900, billing=86400, config=3600, timeout=60, server=90):
    message=str(error).lower()
    if any(token in message for token in ("402","payment required","insufficient credits","pre-paid credits","billing limit","credits exhausted")):
        return int(billing)
    if any(token in message for token in ("401","403","unauthorized","invalid api key","authentication failed","permission denied")):
        return int(config)
    if any(token in message for token in ("429","quota","rate limit","resource_exhausted","usage limit","daily limit","monthly limit","capacity exhausted")):
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

def should_try_next_model(error):
    """Model errors, transient failures and per-model rate limits should try another model.

    Stop only for credentials, permissions or account-level billing failures.
    """
    message=str(error).lower()
    return not any(token in message for token in (
        "401", "403", "402", "unauthorized", "invalid api key",
        "authentication failed", "permission denied", "insufficient credits",
        "pre-paid credits", "payment required", "billing limit",
    ))
