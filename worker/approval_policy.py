"""Decision policy: owner attention is reserved for consequential external actions."""
import re

# Routine planning, product choices, research, and internal drafting are reversible.
# These terms describe actions that cross an external or destructive boundary.
OWNER_GATE_PATTERNS = (
    r"\bpublish(?:\s+(?:this|that|the|it|to|on|publicly))?\b",
    r"\bpost\s+(?:this|that|it|to|on)\b",
    r"\bsend\s+(?:this|that|it|an?\s+(?:email|message|request|invite))\b",
    r"\b(?:email|message|contact|reach out to|interview)\s+(?:a person|people|customers?|users?|the customer|the user)\b",
    r"\b(?:purchase|buy|pay for|spend money|subscribe to)\b",
    r"\b(?:delete|erase|destroy|overwrite)\b",
    r"\bdeploy\s+(?:to\s+)?production\b",
    r"\b(?:change|modify|update)\s+(?:a|the|this|live|production)\s+(?:account|setting|permission|record)\b",
    r"\b(?:upload|share)\s+(?:this|that|it|the|a)\s+(?:to|with|public|externally)\b",
    r"\b(?:grant|revoke)\s+(?:access|permission)\b",
    r"\b(?:api key|access token|password|credential|secret)\b",
    r"\b(?:authorize|approve)\s+(?:a|the|this)\s+(?:payment|purchase|external action)\b",
)
OWNER_GATE_RE = re.compile("|".join("(?:%s)" % pattern for pattern in OWNER_GATE_PATTERNS), re.I)


def requires_owner_approval(question, summary=""):
    """True only when a generated decision crosses an external/destructive boundary."""
    text = (str(question or "") + " " + str(summary or "")).strip()
    return bool(OWNER_GATE_RE.search(text))
