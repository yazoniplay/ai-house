import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import house_mcp


class HouseMCPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name)
        self.state_dir = self.workspace / ".ai-house"
        self.state_dir.mkdir()
        (self.state_dir / "state.json").write_text(json.dumps({
            "cycle": 7,
            "business": {"name": "Demo business", "api_key": "should-not-leak"},
            "roadmap": {"strategy": "build", "tasks": [
                {"id": "t1", "title": "Research", "status": "running", "agent_role": "researcher"}
            ]},
            "activity": {"message": "Working on research"}
        }), encoding="utf-8")
        (self.state_dir / "events.jsonl").write_text(
            json.dumps({"event": "agent_started", "api_token": "hidden", "detail": "Research started"}) + "\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_status_and_work_are_live_workspace_data(self):
        status = house_mcp.house_status(self.workspace)
        self.assertEqual(status["cycle"], 7)
        self.assertEqual(status["business"], "Demo business")
        self.assertNotIn("api_key", json.dumps(status))
        work = house_mcp.list_work(self.workspace)
        self.assertEqual(work["tasks"][0]["title"], "Research")

    def test_recent_activity_filters_secret_fields(self):
        result = house_mcp.recent_activity(self.workspace)
        self.assertEqual(result["events"][0]["event"], "agent_started")
        self.assertNotIn("hidden", json.dumps(result))

    def test_tool_catalog_and_dispatch(self):
        names = {tool["name"] for tool in house_mcp.TOOLS}
        self.assertIn("ask_house_leader", names)
        result = house_mcp.call_tool("house_status", {}, self.workspace)
        self.assertFalse(result["isError"])
        self.assertIn("Demo business", result["content"][0]["text"])

    def test_unknown_tool_rejected(self):
        with self.assertRaises(KeyError):
            house_mcp.call_tool("not_a_tool", {}, self.workspace)


if __name__ == "__main__":
    unittest.main()
