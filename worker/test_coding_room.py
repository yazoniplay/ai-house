import tempfile
import unittest
from pathlib import Path

from coding_room import CodingRoomError, create_project, claim_next, complete_project, list_projects


class CodingRoomTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def make(self, title):
        return create_project(self.workspace, title, "independent creators", "They waste time on repetitive admin.", "A small app that solves the core workflow.", "5 users finish the flow")

    def test_only_one_app_can_be_active(self):
        first = self.make("App One")
        second = self.make("App Two")
        claimed = claim_next(self.workspace, "room-a")
        self.assertEqual(claimed["id"], first["id"])
        self.assertIsNone(claim_next(self.workspace, "room-b"))
        complete_project(self.workspace, first["id"], "room-a", "Leader-reviewed")
        next_project = claim_next(self.workspace, "room-b")
        self.assertEqual(next_project["id"], second["id"])

    def test_queue_is_small_and_bounded(self):
        self.make("One")
        self.make("Two")
        self.make("Three")
        with self.assertRaisesRegex(CodingRoomError, "at most two queued"):
            self.make("Four")

    def test_wrong_room_cannot_complete_active_project(self):
        project = self.make("Focused")
        claim_next(self.workspace, "room-a")
        with self.assertRaisesRegex(CodingRoomError, "currently owning"):
            complete_project(self.workspace, project["id"], "room-b")


if __name__ == "__main__":
    unittest.main()
