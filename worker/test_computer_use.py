import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from approvals import answer
from computer_use import ComputerUseError, execute, status


class FakePyAutoGUI(types.ModuleType):
    def __init__(self):
        super().__init__("pyautogui")
        self.calls = []
        self.FAILSAFE = False
        self.PAUSE = 0
    def click(self, *args, **kwargs): self.calls.append(("click", args, kwargs))
    def moveTo(self, *args, **kwargs): self.calls.append(("move", args, kwargs))
    def write(self, *args, **kwargs): self.calls.append(("write", args, kwargs))
    def hotkey(self, *args, **kwargs): self.calls.append(("hotkey", args, kwargs))
    def scroll(self, *args, **kwargs): self.calls.append(("scroll", args, kwargs))


class ComputerUseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name)
        self.fake = FakePyAutoGUI()

    def tearDown(self):
        self.temp.cleanup()

    def test_risky_action_requires_owner_approval(self):
        action = {"kind": "click", "x": 200, "y": 300, "intent": "publish", "target": "YouTube publish button"}
        result = execute(self.workspace, action)
        self.assertEqual(result["status"], "approval_required")
        self.assertTrue(result["approval_id"])

    def test_approval_is_bound_to_exact_action(self):
        action = {"kind": "click", "x": 200, "y": 300, "intent": "publish", "target": "YouTube publish button"}
        request = execute(self.workspace, action)
        answer(self.workspace, request["approval_id"], "yes")
        changed = dict(action, x=201)
        with patch.dict(sys.modules, {"pyautogui": self.fake}):
            with self.assertRaisesRegex(ComputerUseError, "does not match"):
                execute(self.workspace, changed, approval_id=request["approval_id"])

    def test_approved_risky_action_executes(self):
        action = {"kind": "click", "x": 200, "y": 300, "intent": "publish", "target": "YouTube publish button"}
        request = execute(self.workspace, action)
        answer(self.workspace, request["approval_id"], "yes")
        with patch.dict(sys.modules, {"pyautogui": self.fake}):
            result = execute(self.workspace, action, approval_id=request["approval_id"])
        self.assertEqual(result["status"], "ok")
        self.assertEqual(self.fake.calls[0][0], "click")

    def test_status_is_local_desktop_bridge(self):
        self.assertEqual(status(self.workspace)["backend"], "PyAutoGUI (local desktop)")


if __name__ == "__main__":
    unittest.main()
