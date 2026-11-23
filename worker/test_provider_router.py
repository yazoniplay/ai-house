import unittest
from provider_router import rotate, model_pool, filter_model_pool, is_model_specific_error, is_unavailable_model_error, cooldown_seconds, should_try_next_model, openrouter_free_model_ids, is_openrouter_credit_model_error, is_provider_wide_error, gemini_chat_model_pool, provider_chat_model_pool

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

    def test_live_catalog_filters_retired_and_unsupported_models(self):
        candidates=["gemini-3.5-flash-lite","old-model","google/gemma-4-31b-it"]
        available={"gemini-3.5-flash-lite","google/gemma-4-31b-it"}
        self.assertEqual(filter_model_pool(candidates,available),["gemini-3.5-flash-lite","google/gemma-4-31b-it"])
        self.assertEqual(filter_model_pool(candidates,None,{"old-model"}),["gemini-3.5-flash-lite","google/gemma-4-31b-it"])

    def test_openrouter_router_aliases_survive_live_model_catalog_filter(self):
        candidates=["openrouter/free","openrouter/auto","google/gemini-3.5-flash-lite","retired/model"]
        available={"google/gemini-3.5-flash-lite"}
        self.assertEqual(
            filter_model_pool(candidates,available,allow_unlisted={"openrouter/free","openrouter/auto"}),
            ["openrouter/free","openrouter/auto","google/gemini-3.5-flash-lite"],
        )

    def test_retired_model_errors_are_marked_unavailable(self):
        self.assertTrue(is_unavailable_model_error("NVIDIA 410 Gone: model reached end of life"))
        self.assertTrue(is_unavailable_model_error("HTTP 404 page not found"))
        self.assertFalse(is_unavailable_model_error("503 temporarily unavailable"))

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

    def test_gemini_pool_uses_full_catalog_and_filters_specialized_models(self):
        catalog={"gemini-3.5-flash-lite","gemini-3.1-flash-lite","gemini-3.8-flash","gemini-3.6-flash","gemini-2.5-pro","gemma-3-27b-it","gemini-embedding-001","gemini-3.5-transcribe","gemini-3.1-flash-live-preview","gemini-3-pro-image"}
        pool=gemini_chat_model_pool(catalog,["gemini-3.5-flash-lite","gemini-3.1-flash-lite"])
        self.assertEqual(pool[:2],["gemini-3.5-flash-lite","gemini-3.1-flash-lite"])
        self.assertIn("gemini-3.8-flash",pool)
        self.assertIn("gemma-3-27b-it",pool)
        self.assertIn("gemini-2.5-pro",pool)
        self.assertFalse(any(any(token in model for token in ("embedding","transcribe","live","image")) for model in pool))
        self.assertEqual(len(pool),6)

    def test_provider_chat_catalog_expands_and_prioritizes_free_and_fast_models(self):
        catalog=["meta/llama-70b","meta/llama-8b","meta/llama-embedding","nvidia/nemotron-fast","nvidia/nemotron-120b","nvidia/whisper-large"]
        groq=provider_chat_model_pool("groq",catalog,["meta/llama-70b"])
        self.assertEqual(groq[0],"meta/llama-70b")
        self.assertIn("meta/llama-8b",groq)
        self.assertIn("nvidia/nemotron-fast",groq)
        self.assertNotIn("meta/llama-embedding",groq)
        self.assertNotIn("nvidia/whisper-large",groq)

    def test_openrouter_free_models_are_first_then_paid_catalog_fallbacks(self):
        catalog=["paid/model-large","free/llama:free","paid/model-mini","free/gemma:free"]
        pool=provider_chat_model_pool("openrouter",catalog,["paid/model-mini"],["free/llama:free","free/gemma:free"])
        self.assertEqual(pool[:2],["free/llama:free","free/gemma:free"])
        self.assertIn("paid/model-mini",pool)
        self.assertIn("paid/model-large",pool)

    def test_openrouter_catalog_finds_free_and_zero_priced_models(self):
        rows=[
            {"id":"meta-llama/llama-3.3-70b-instruct:free","pricing":{"prompt":"0","completion":"0"}},
            {"id":"google/gemma-3-27b-it","pricing":{"prompt":"0.000001","completion":"0.000002"}},
            {"id":"qwen/qwen3-32b","pricing":{"prompt":0,"completion":0}},
            {"id":"bad/model","pricing":{"prompt":"unknown","completion":"unknown"}},
        ]
        self.assertEqual(openrouter_free_model_ids(rows),["meta-llama/llama-3.3-70b-instruct:free","qwen/qwen3-32b"])

    def test_openrouter_account_credit_failure_is_provider_wide(self):
        error="openrouter 402: can only afford 83 tokens due to credits"
        self.assertTrue(is_openrouter_credit_model_error("openrouter",error))
        self.assertTrue(is_provider_wide_error("openrouter",error))
        self.assertTrue(is_provider_wide_error("gemini","402 insufficient credits"))
        self.assertTrue(is_provider_wide_error("openrouter","openrouter 401 invalid API key"))

    def test_openrouter_free_daily_quota_skips_model_pool(self):
        error="429: free-models-per-day quota exhausted"
        self.assertTrue(is_provider_wide_error("openrouter",error))
        self.assertFalse(should_try_next_model(error))
        self.assertFalse(is_provider_wide_error("groq","429 rate limit for this model"))

    def test_unknown_error_does_not_disable_provider(self):
        self.assertEqual(cooldown_seconds("bad response shape"),0)

if __name__=="__main__":
    unittest.main()
