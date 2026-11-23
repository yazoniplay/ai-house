import unittest
from specialist_prompts import PLAYBOOKS, UNIVERSAL, specialist_system_prompt
import autonomous_engine as engine

class SpecialistPromptTests(unittest.TestCase):
    def test_every_configured_role_has_a_professional_playbook(self):
        self.assertEqual(set(engine.ROLES)-set(PLAYBOOKS),set())

    def test_each_playbook_is_included_in_the_system_prompt(self):
        for role,playbook in PLAYBOOKS.items():
            with self.subTest(role=role):
                prompt=specialist_system_prompt(role)
                self.assertIn(UNIVERSAL,prompt)
                self.assertIn(playbook,prompt)
                self.assertIn("SPECIALIST OPERATING BRIEF",prompt)

    def test_playbooks_preserve_truthfulness_and_external_action_boundaries(self):
        prompt=specialist_system_prompt("sales_drafter").lower()
        self.assertIn("do not contact",prompt)\n        self.assertIn("anyone",prompt)
        self.assertIn("never imply",UNIVERSAL.lower())
        self.assertIn("never invent",UNIVERSAL.lower())

if __name__=="__main__":
    unittest.main()
