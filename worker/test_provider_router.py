import unittest
from provider_router import rotate, model_pool, is_model_specific_error, cooldown_seconds, should_try_next_model

class ProviderRouterTests(unittest.TestCase):
    def test_provider_rotation_spreads_calls_across_available_providers(self):
        providers=["gemini","groq","nvidia","openrouter"]
        self.assertEqual(rotate(providers,0),providers)
        self.assertEqual(rotate(providers,1),["groq","nvidia","openrouter","gemini"])
        self.assertEqual(rotate(providers,5),["groq","nvidia","openrouter","gemini"])

    def test_model_pool_deduplicates_primary_and_configured_models(self):
        self.assertEqual(model_pool("main","alt,main,third"),["main","alt","third"])

    def test_model_errors_can_try_another_model(self):
        self.assertTrue(is_model_specific_error("HTTP 404: model_not_found"))
        self.assertTrue(is_model_specific_error("unknown model id"))
        self.assertFalse(is_model_specific_error("HTTP 429: quota exceeded"))

    def test_quota_and_billing_errors_trigger_provider_cooldown(self):
        self.assertEqual(cooldown_seconds("429 resource_exhausted"),900)
        self.assertEqual(cooldown_seconds("402 insufficient credits"),86400)
        self.assertEqual(cooldown_seconds("401 invalid API key"),3600)

    def test_transient_model_failure_keeps_trying_alternates(self):
        self.assertTrue(should_try_next_model("read operation timed out"))
        self.assertTrue(should_try_next_model("429 rate limit for this model"))
        self.assertTrue(should_try_next_model("503 temporarily unavailable"))
        self.assertFalse(should_try_next_model("401 invalid API key"))
        self.assertFalse(should_try_next_model("402 insufficient credits"))

    def test_model_pool_keeps_primary_and_alternates_in_order(self):
        self.assertEqual(model_pool("kimi", "nemotron,glm,kimi"), ["kimi", "nemotron", "glm"])

    def test_unknown_error_does_not_disable_provider(self):
        self.assertEqual(cooldown_seconds("bad response shape"),0)

if __name__=="__main__":
    unittest.main()
