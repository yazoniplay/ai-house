from pathlib import Path

target = Path("worker/autonomous_engine.py")
code = target.read_text(encoding="utf-8")

ark_line = 'ARK= os. getenv("AGENTROUTER_API_KEY",""); ARM= os. getenv("AGENTROUTER_MODEL","deepseek-v4-flash"); ARB= os. getenv("AGENTROUTER_BASE_URL","https://agentrouter.org"). rstrip("/")'
headers_block = ark_line + '''
AGENTROUTER_HEADERS = {
    "User-Agent": "claude-cli/2.0.30 (external, cli)",
    "x-app": "cli",
    "anthropic-version": "2023-06-01",
    "anthropic-beta": "claude-code-20250219,interleaved-thinking-2025-05-14",
    "x-stainless-lang": "js",
    "x-stainless-package-version": "0.39.0",
    "x-stainless-os": "Windows",
    "x-stainless-arch": "x64",
    "x-stainless-runtime": "node",
    "x-stainless-runtime-version": "v22.12.0",
}'''

assert ark_line in code, "Could not find ARK line"
code = code.replace(ark_line, headers_block, 1)

old_models_req = '**({"User-Agent":"Mozilla/5.0 AIHouse/1.0"} if provider=="routeway" else {})}, timeout= 12)'
new_models_req = '**({"User-Agent":"Mozilla/5.0 AIHouse/1.0"} if provider=="routeway" else {}), **(AGENTROUTER_HEADERS if provider=="agentrouter" else {})}, timeout= 12)'
assert old_models_req in code, "Could not find /models request line"
code = code.replace(old_models_req, new_models_req, 1)

old_chat_req = '**({"User-Agent":"Mozilla/5.0 AIHouse/1.0"} if p=="routeway" else {})}, json= payload, timeout= timeout_seconds)'
new_chat_req = '**({"User-Agent":"Mozilla/5.0 AIHouse/1.0"} if p=="routeway" else {}), **(AGENTROUTER_HEADERS if p=="agentrouter" else {})}, json= payload, timeout= timeout_seconds)'
assert old_chat_req in code, "Could not find /chat/completions request line"
code = code.replace(old_chat_req, new_chat_req, 1)

target.write_text(code, encoding="utf-8")
print("SUCCESS! AgentRouter patched.")
