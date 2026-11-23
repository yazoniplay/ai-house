"""Task classification helpers for deterministic roadmap gates."""

def is_usage_verification_task(task):
    """Only a dedicated adoption/usage verification task may receive the 10-user gate.

    Do not infer an adoption gate from generic references to users in an analyst,
    research, instrumentation, or analytics-framework task.
    """
    if not isinstance(task, dict):
        return False
    text = " ".join(
        str(task.get(key, "") or "")
        for key in ("title", "objective", "success_metric")
    ).lower()
    markers = (
        "adoption verification",
        "user adoption verification",
        "verify product usage",
        "product usage verification",
        "usage verification",
        "verify usage",
        "verify adoption",
        "verify 10 real product users",
        "verify 10 users",
        "verify ten users",
        "10-user adoption",
    )
    return any(marker in text for marker in markers)
