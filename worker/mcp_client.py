"""Small, opt-in MCP stdio client for locally configured MCP servers.

Servers are user-configured and started only for an explicit list/test/call request.
No server is auto-connected at startup. Tool calls are explicit and logged by the caller.
"""
import json
import os
import queue
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_. -]{0,63}$")
MAX_TOOLS = 200


class MCPError(RuntimeError):
    pass


def config_path(workspace):
    return Path(workspace).resolve() / ".ai-house" / "mcp_servers.json"


def list_servers(workspace):
    try:
        data = json.loads(config_path(workspace).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {"servers": []}
    items = data.get("servers", []) if isinstance(data, dict) else []
    return [item for item in items if isinstance(item, dict)]


def save_servers(workspace, servers):
    clean = []
    seen = set()
    for item in servers:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        command = str(item.get("command", "")).strip()
        args = item.get("args", [])
        if not NAME_RE.fullmatch(name) or name.lower() in seen:
            raise MCPError("Each MCP server needs a unique, valid name.")
        if not command or len(command) > 500 or not isinstance(args, list) or len(args) > 40:
            raise MCPError("Server command is required; args must be a list of at most 40 strings.")
        if any(not isinstance(arg, str) or len(arg) > 1000 for arg in args):
            raise MCPError("MCP args must be strings no longer than 1000 characters.")
        seen.add(name.lower())
        clean.append({"name": name, "command": command, "args": args, "enabled": bool(item.get("enabled", True))})
    path = config_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"servers": clean}, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
    return clean


class _Session:
    def __init__(self, server, timeout=12):
        self.server = server
        self.timeout = timeout
        command = str(server["command"])
        args = [str(x) for x in server.get("args", [])]
        executable = shutil.which(command) or command
        launch = [executable, *args]
        # Windows MCP packages commonly expose npx.cmd / package .cmd launchers.
        # Use a safely quoted cmd.exe argument string only for those wrappers.
        if os.name == "nt" and Path(executable).suffix.lower() in (".cmd", ".bat"):
            launch = [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/s", "/c", subprocess.list2cmdline(launch)]
        try:
            self.proc = subprocess.Popen(launch, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
                                        errors="replace", bufsize=1, shell=False)
        except OSError as exc:
            raise MCPError("Could not start MCP server: " + type(exc).__name__) from exc
        self.lines = queue.Queue()
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()
        self.next_id = 1

    def _read(self):
        try:
            for line in self.proc.stdout:
                self.lines.put(line)
        finally:
            self.lines.put(None)

    def send(self, payload):
        try:
            self.proc.stdin.write(json.dumps(payload, ensure_ascii=False) + chr(10))
            self.proc.stdin.flush()
        except (OSError, BrokenPipeError) as exc:
            raise MCPError("MCP server closed its input stream.") from exc

    def request(self, method, params=None):
        request_id = self.next_id
        self.next_id += 1
        self.send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}})
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            try:
                line = self.lines.get(timeout=max(0.05, deadline - time.monotonic()))
            except queue.Empty:
                break
            if line is None:
                raise MCPError("MCP server exited before replying.")
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if msg.get("id") != request_id:
                continue
            if "error" in msg:
                error = msg["error"]
                raise MCPError("MCP " + str(error.get("code", "error")) + ": " + str(error.get("message", "request failed"))[:500])
            return msg.get("result", {})
        raise MCPError("MCP request timed out (" + method + ").")

    def initialize(self):
        self.request("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                                    "clientInfo": {"name": "AI House", "version": "1.0"}})
        self.send({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

    def close(self):
        try:
            self.proc.terminate()
            self.proc.wait(timeout=1)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass


def _enabled_server(workspace, name):
    server = next((x for x in list_servers(workspace) if x.get("name") == name), None)
    if not server:
        raise MCPError("MCP server not found.")
    if not server.get("enabled", True):
        raise MCPError("MCP server is disabled.")
    return server


def list_tools(workspace, name):
    server = _enabled_server(workspace, name)
    session = _Session(server)
    try:
        session.initialize()
        result = session.request("tools/list")
        tools = result.get("tools", [])
        if not isinstance(tools, list):
            raise MCPError("MCP server returned an invalid tools list.")
        return [{"name": str(t.get("name", ""))[:120], "description": str(t.get("description", ""))[:1000],
                 "inputSchema": t.get("inputSchema", {})} for t in tools[:MAX_TOOLS] if isinstance(t, dict)]
    finally:
        session.close()


def call_tool(workspace, server_name, tool_name, arguments=None):
    if not isinstance(tool_name, str) or not tool_name or len(tool_name) > 120:
        raise MCPError("Invalid MCP tool name.")
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        raise MCPError("Tool arguments must be a JSON object.")
    if len(json.dumps(arguments, ensure_ascii=False)) > 12000:
        raise MCPError("Tool arguments are too large.")
    server = _enabled_server(workspace, server_name)
    session = _Session(server, timeout=30)
    try:
        session.initialize()
        available = session.request("tools/list").get("tools", [])
        if not any(isinstance(t, dict) and t.get("name") == tool_name for t in available):
            raise MCPError("Tool is not exposed by this MCP server.")
        return session.request("tools/call", {"name": tool_name, "arguments": arguments})
    finally:
        session.close()
