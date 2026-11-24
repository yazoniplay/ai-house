import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from approval_policy import requires_owner_approval


class ApprovalPolicyTests(unittest.TestCase):
    def test_routine_choices_are_autonomous(self):
        for question in (
            "Which product idea should we build first?",
            "Should the team use a checklist or a template?",
            "Which research source should we prioritize?",
        ):
            with self.subTest(question=question):
                self.assertFalse(requires_owner_approval(question))

    def test_external_and_destructive_actions_need_owner(self):
        for question in (
            "Should I publish this video now?",
            "Should I send this email to the customer?",
            "May I purchase this subscription?",
            "Should I delete the live account?",
            "Can I deploy to production?",
        ):
            with self.subTest(question=question):
                self.assertTrue(requires_owner_approval(question))


if __name__ == "__main__":
    unittest.main()
