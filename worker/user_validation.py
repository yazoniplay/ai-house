"""Evidence-based verification of real product usage.

Usage is counted from production analytics events, not visits, page views,
marketing clicks, bots, test accounts, or the owner's own account.
"""
from __future__ import annotations
import hashlib
from datetime import datetime, timezone, timedelta

QUALIFYING_EVENTS={
    "activation","core_action","completed_workflow","product_use",
    "feature_used","core_feature_used","key_action"
}
PRODUCTION_VALUES={"production","prod","live"}

def _timestamp(value):
    if isinstance(value,(int,float)):
        try:return datetime.fromtimestamp(float(value),timezone.utc)
        except (ValueError,OverflowError,OSError):return None
    text=str(value or "").strip()
    if not text:return None
    try:return datetime.fromisoformat(text.replace("Z","+00:00")).astimezone(timezone.utc)
    except ValueError:return None

def verify_usage_events(events, owner_user_ids=(), minimum_users=10, window_days=30, now=None):
    """Return a conservative, privacy-minimized distinct-user verification report."""
    now=_timestamp(now) if now is not None else datetime.now(timezone.utc)
    if now is None:now=datetime.now(timezone.utc)
    minimum=max(1,int(minimum_users));window=max(1,int(window_days))
    cutoff=now-timedelta(days=window)
    owners={str(x).strip() for x in (owner_user_ids or []) if str(x).strip()}
    users=set();qualified=0;rejected={"missing_user":0,"owner_or_internal":0,"non_production":0,"non_usage_event":0,"invalid_or_old_timestamp":0,"test_or_bot":0}
    for item in events or []:
        if not isinstance(item,dict):continue
        uid=str(item.get("user_id") or item.get("distinct_id") or item.get("anonymous_user_id") or "").strip()
        if not uid:rejected["missing_user"]+=1;continue
        if uid in owners or item.get("is_internal") or item.get("is_owner"):
            rejected["owner_or_internal"]+=1;continue
        if item.get("is_test") or item.get("test") or item.get("is_bot") or item.get("bot"):
            rejected["test_or_bot"]+=1;continue
        environment=str(item.get("environment") or item.get("env") or "").strip().lower()
        if environment not in PRODUCTION_VALUES:
            rejected["non_production"]+=1;continue
        event=str(item.get("event_name") or item.get("event") or item.get("type") or "").strip().lower()
        if event not in QUALIFYING_EVENTS:
            rejected["non_usage_event"]+=1;continue
        stamp=_timestamp(item.get("timestamp") or item.get("at") or item.get("created_at"))
        if stamp is None or stamp<cutoff or stamp>now+timedelta(minutes=5):
            rejected["invalid_or_old_timestamp"]+=1;continue
        users.add(uid);qualified+=1
    status="verified" if len(users)>=minimum else "pending"
    return {
        "status":status,"minimum_users":minimum,"distinct_production_users":len(users),
        "qualifying_events":qualified,"window_days":window,
        "window_start":cutoff.isoformat(),"window_end":now.isoformat(),
        "owner_and_internal_excluded":True,"test_and_bot_events_excluded":True,
        "evidence_quality":"production_events" if qualified else "no_qualifying_production_events",
        "rejected_events":rejected,
        "privacy_safe_user_fingerprints":sorted(hashlib.sha256(uid.encode("utf-8")).hexdigest()[:16] for uid in users),
        "claim":"Distinct production user accounts observed performing a core action; not a guarantee that each account represents a separate person."
    }
