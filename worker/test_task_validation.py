import unittest

from task_validation import is_usage_verification_task


class UsageTaskClassificationTests(unittest.TestCase):
    def test_ordinary_analytics_framework_does_not_trigger_adoption_gate(self):
        task = {
            "title": "Create analytics framework",
            "objective": "Define events and metrics to measure activation across the first 10 users.",
            "agent_role": "analyst",
            "acceptance": ["Document the event schema and dashboard metrics."],
        }
        self.assertFalse(is_usage_verification_task(task))

    def test_ordinary_research_about_users_does_not_trigger_adoption_gate(self):
        task = {
            "title": "Research target customers",
            "objective": "Interview or research ten potential users and summarize their pain points.",
            "agent_role": "customer_researcher",
        }
        self.assertFalse(is_usage_verification_task(task))

    def test_dedicated_ten_user_verification_task_triggers_gate(self):
        task = {
            "title": "Verify 10 real product users",
            "objective": "Check a genuine production analytics export.",
            "agent_role": "customer_success",
        }
        self.assertTrue(is_usage_verification_task(task))

    def test_explicit_adoption_verification_task_triggers_gate(self):
        task = {
            "title": "Product adoption verification",
            "objective": "Report actual qualifying production usage.",
            "agent_role": "customer_success",
        }
        self.assertTrue(is_usage_verification_task(task))

    def test_analyst_usage_framework_never_receives_adoption_gate(self):
        task = {
            "title": "Product usage verification analytics framework",
            "objective": "Design an event schema and reporting framework.",
            "agent_role": "analyst",
        }
        self.assertFalse(is_usage_verification_task(task))

    def test_non_dict_task_is_safe(self):
        self.assertFalse(is_usage_verification_task(None))


if __name__ == "__main__":
    unittest.main()
