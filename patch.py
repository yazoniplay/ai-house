import re
from pathlib import Path

target = Path("worker/autonomous_engine.py")
code = target.read_text(encoding="utf-8")

# Add automatic /v1/responses fallback for AgentRouter models that require it
old_block = '''        if r. status_code>= 400:
            last_error= RuntimeError( p+" "+ str( r. status_code)+": "+ r. text[: 220])
            break'''

new_block = '''        if r. status_code == 400 and p == "agentrouter" and "/v1/responses" in r. text:
            resp_url = ARB + "/responses"
            resp_payload = {"model": candidate, "instructions": sys, "input": ask, "max_output_tokens": 8192}
            r2 = HTTP. post(resp_url, headers={"Authorization": "Bearer " + key, "Content-Type": "application/json", **AGENTROUTER_HEADERS}, json=resp_payload, timeout=timeout_seconds)
            if r2. status_code < 400:
                d2 = r2. json()
                out = d2. get("output_text") or "". join(c. get("text", "") for item in d2. get("output", []) for c in item. get("content", []) if isinstance(c, dict))
                if out and str(out). strip():
                    record_usage(p, d2. get("usage"))
                    log("model_call_ok", provider=p, model=candidate, role=role, endpoint="responses")
                    return out
            last_error = RuntimeError(p + " responses " + str(r2. status_code) + ": " + r2. text[: 220])
            break
        if r. status_code>= 400:
            last_error= RuntimeError( p+" "+ str( r. status_code)+": "+ r. text[: 220])
            break'''

# Normalize spacing check
pattern = re.compile(
    r'if r\.\s*status_code\s*>=\s*400:\s*\n\s*last_error\s*=\s*RuntimeError\(\s*p\s*\+\s*" "\s*\+\s*str\(\s*r\.\s*status_code\s*\)\s*\+\s*": "\s*\+\s*r\.\s*text\[:\s*220\]\s*\)\s*\n\s*break'
)
code, count = pattern.subn(new_block, code, count=1)
assert count == 1, "Could not locate HTTP error block in _raw_once"

target.write_text(code, encoding="utf-8")
print("SUCCESS! Added /v1/responses support for AgentRouter.")
