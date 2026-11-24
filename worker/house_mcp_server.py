"""AI House MCP server over standard newline-delimited stdio JSON-RPC."""
import json
import sys
from house_mcp import TOOLS, call_tool


def response(request_id, result=None, error=None):
    message = {"jsonrpc": "2.0", "id": request_id}
    if error is not None:
        message["error"] = error
    else:
        message["result"] = result
    sys.stdout.write(json.dumps(message, ensure_ascii=False, default=str) + "\n")
    sys.stdout.flush()


def handle(message):
    method = message.get("method")
    request_id = message.get("id")
    params = message.get("params") or {}
    if method == "notifications/initialized" or (request_id is None and method and method.startswith("notifications/")):
        return
    if request_id is None:
        return
    if method == "initialize":
        requested = params.get("protocolVersion", "2024-11-05")
        supported = {"2024-11-05", "2025-03-26", "2025-06-18"}
        response(request_id, {
            "protocolVersion": requested if requested in supported else "2024-11-05",
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "ai-house", "version": "1.0.0"},
            "instructions": "AI House live status and activity are read-only. ask_house_leader routes a question to the house Leader; it does not approve pending owner requests."
        })
    elif method == "ping":
        response(request_id, {})
    elif method == "tools/list":
        response(request_id, {"tools": TOOLS})
    elif method == "tools/call":
        try:
            result = call_tool(params.get("name"), params.get("arguments") or {})
            response(request_id, result)
        except KeyError as exc:
            response(request_id, error={"code": -32602, "message": str(exc)})
        except (ValueError, RuntimeError) as exc:
            response(request_id, result={"content": [{"type": "text", "text": str(exc)}], "isError": True})
        except Exception as exc:
            response(request_id, result={"content": [{"type": "text", "text": "AI House tool failed: " + type(exc).__name__}], "isError": True})
    else:
        response(request_id, error={"code": -32601, "message": "Method not found: " + str(method)})


def main():
    for line in sys.stdin:
        try:
            message = json.loads(line)
            if isinstance(message, dict) and message.get("jsonrpc") == "2.0":
                handle(message)
        except Exception:
            # Malformed input is ignored rather than contaminating the stdio stream.
            continue


if __name__ == "__main__":
    main()
