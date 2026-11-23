import tempfile
import unittest
from pathlib import Path

from studio import (
    StudioError,
    create_project,
    decide_approval,
    list_approvals,
    list_projects,
    move_stage,
)


class StudioWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_youtube_pipeline_requires_leader_approval_before_publish(self):
        project = create_project(self.workspace, "youtube", "A test video")
        for stage in ("research", "script", "storyboard", "assets", "editing", "review", "approval_pending"):
            project = move_stage(self.workspace, project["id"], stage)
        approval = list_approvals(self.workspace)[0]
        with self.assertRaises(StudioError):
            move_stage(self.workspace, project["id"], "published")
        decided = decide_approval(self.workspace, approval["id"], "approve", "Looks good")
        self.assertEqual(decided["status"], "approved")
        self.assertEqual(decided["decision_actor"], "leader")
        project = move_stage(self.workspace, project["id"], "published")
        self.assertEqual(project["stage"], "published")

    def test_rejection_returns_project_to_review(self):
        project = create_project(self.workspace, "marketing", "Launch campaign")
        for stage in ("research", "strategy", "content_drafts", "campaign_review", "approval_pending"):
            project = move_stage(self.workspace, project["id"], stage)
        approval = list_approvals(self.workspace)[0]
        decide_approval(self.workspace, approval["id"], "reject", "Fix claims")
        current = list_projects(self.workspace)[0]
        self.assertEqual(current["stage"], "campaign_review")
        self.assertEqual(list_approvals(self.workspace), [])

    def test_invalid_stage_jump_is_rejected(self):
        project = create_project(self.workspace, "youtube", "Video")
        with self.assertRaises(StudioError):
            move_stage(self.workspace, project["id"], "editing")


if __name__ == "__main__":
    unittest.main()
