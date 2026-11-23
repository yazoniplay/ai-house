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
        "404 not found","no such model"
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
