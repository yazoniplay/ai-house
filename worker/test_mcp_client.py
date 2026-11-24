import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mcp_client


FAKE_SERVER = """import json,sys
for line in sys.stdin:
 try: m=json.loads(line)
 except Exception: continue
 if m.get('method')=='notifications/initialized': continue
 method=m.get('method'); rid=m.get('id')
 if method=='initialize': result={'protocolVersion':'2024-11-05','capabilities':{'tools':{}},'serverInfo':{'name':'fake','version':'1'}}
 elif method=='tools/list': result={'tools':[{'name':'echo','description':'Echo arguments','inputSchema':{'type':'object'}}]}
 elif method=='tools/call': result={'content':[{'type':'text','text':json.dumps(m.get('params',{}).get('arguments',{}))}]}
 else: result={}
 print(json.dumps({'jsonrpc':'2.0','id':rid,'result':result}),flush=True)
"""


class MCPClientTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = self.temp.name

    def tearDown(self):
        self.temp.cleanup()

    def test_save_and_list_servers(self):
        servers = mcp_client.save_servers(self.workspace, [{
            "name": "Fake MCP", "command": sys.executable,
            "args": ["-u", "-c", FAKE_SERVER], "enabled": True
        }])
        self.assertEqual(servers[0]["name"], "Fake MCP")
        self.assertEqual(mcp_client.list_servers(self.workspace), servers)

    def test_reject_duplicate_names(self):
        with self.assertRaises(mcp_client.MCPError):
            mcp_client.save_servers(self.workspace, [
                {"name": "Same", "command": "python", "args": []},
                {"name": "same", "command": "python", "args": []}
            ])

    def test_list_tools_and_call_tool(self):
        mcp_client.save_servers(self.workspace, [{
            "name": "Fake MCP", "command": sys.executable,
            "args": ["-u", "-c", FAKE_SERVER], "enabled": True
        }])
        tools = mcp_client.list_tools(self.workspace, "Fake MCP")
        self.assertEqual(tools[0]["name"], "echo")
        result = mcp_client.call_tool(self.workspace, "Fake MCP", "echo", {"hello": "world"})
        self.assertIn("world", json.dumps(result))

    def test_disabled_server_is_not_started(self):
        mcp_client.save_servers(self.workspace, [{
            "name": "Fake MCP", "command": sys.executable,
            "args": ["-u", "-c", FAKE_SERVER], "enabled": False
        }])
        with self.assertRaises(mcp_client.MCPError):
            mcp_client.list_tools(self.workspace, "Fake MCP")


if __name__ == "__main__":
    unittest.main()
