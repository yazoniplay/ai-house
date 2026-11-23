import unittest
from specialist_prompts import PLAYBOOKS, UNIVERSAL, PROMPT_VERSION, DELIVERY_CONTRACT, CONSULTATION_PROTOCOL, specialist_system_prompt
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

    def test_prompts_are_versioned_and_include_delivery_contract(self):
        self.assertEqual(PROMPT_VERSION, "2.0.0")
        for role in PLAYBOOKS:
            prompt=specialist_system_prompt(role)
            self.assertIn(DELIVERY_CONTRACT,prompt)
            self.assertIn("evidence ledger",prompt.lower())
        self.assertIn(CONSULTATION_PROTOCOL,specialist_system_prompt("orchestrator"))
        self.assertNotIn(CONSULTATION_PROTOCOL,specialist_system_prompt("builder"))

    def test_roadmap_consultation_uses_independent_specialists(self):
        calls=[]
        original_ask=engine.ask
        original_log=engine.log
        try:
            engine.ask=lambda role,prompt: calls.append((role,prompt)) or ("advice from "+role)
            engine.log=lambda *args,**kwargs: None
            result=engine.consult_specialists(
                {"business":{"name":"Example","problem":"slow invoicing"},"history":[]},
                "initial",
                None,
            )
        finally:
            engine.ask=original_ask
            engine.log=original_log
        self.assertEqual([role for role,_ in calls],["strategist","product_manager"])
        self.assertEqual([item["role"] for item in result],["strategist","product_manager"])
        self.assertTrue(all("Do not invent evidence" in prompt or "Do not assume demand" in prompt for _,prompt in calls))

    def test_playbooks_preserve_truthfulness_and_external_action_boundaries(self):
        prompt=specialist_system_prompt("sales_drafter").lower()
        self.assertIn("do not contact",prompt)
        self.assertIn("anyone",prompt)
        self.assertIn("never imply",UNIVERSAL.lower())
        self.assertIn("never invent",UNIVERSAL.lower())

if __name__=="__main__":
    unittest.main()
