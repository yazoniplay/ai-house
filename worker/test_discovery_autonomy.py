import unittest
from unittest.mock import patch
import autonomous_engine as engine

class DiscoverySearchTests(unittest.TestCase):
    def test_search_fans_out_to_tavily_exa_and_duckduckgo(self):
        tavily=[{"url":"https://tavily.example/a","content":"A"}]
        exa=[{"url":"https://exa.example/b","content":"B"}]
        ddg=[{"url":"https://ddg.example/c","content":"C"}]
        with patch.object(engine,"T","tavily-key"), patch.object(engine,"EX","exa-key"), \
             patch.object(engine,"search_provider_ready",return_value=True), \
             patch.object(engine,"search_allowed",return_value=True), \
             patch.object(engine,"exa_allowed",return_value=True), \
             patch.object(engine,"tavily_search",return_value=tavily) as t, \
             patch.object(engine,"exa_search",return_value=exa) as x, \
             patch.object(engine,"duckduckgo_search",return_value=ddg) as d, \
             patch.object(engine,"log"):
            results=engine.search("test customer problem")
        self.assertEqual({item["url"] for item in results},
                         {"https://tavily.example/a","https://exa.example/b","https://ddg.example/c"})
        t.assert_called_once()
        x.assert_called_once()
        d.assert_called_once()

    def test_new_gateway_providers_are_added_to_fallback_rotation(self):
        with patch.object(engine,"M","gemini"), patch.object(engine,"ORK","orca-key"), \
             patch.object(engine,"BLK","bazaar-key"), patch.object(engine,"PROVIDER_ROTATION",{"orchestrator":0}), \
             patch.object(engine,"log"):
            providers=engine.provider_order("orchestrator")
        self.assertIn("orcarouter",providers)
        self.assertIn("bazaarlink",providers)

    def test_gateway_catalogs_keep_router_aliases_and_filter_non_chat_models(self):
        with patch.object(engine,"provider_model_catalog",side_effect=[
            {"openai/gpt-6.1-sol","anthropic/claude-sonnet-4.6"},
            {"openai/gpt-4o-mini","google/gemini-2.5-flash","openai/text-embedding-3-large","openai/whisper-large"},
        ]), patch.object(engine,"log"):
            orca=engine.model_candidates("orcarouter","orchestrator")
            bazaar=engine.model_candidates("bazaarlink","orchestrator")
        self.assertEqual(orca[0],"orcarouter/auto")
        self.assertIn("openai/gpt-6.1-sol",orca)
        self.assertEqual(bazaar[0],"auto:free")
        self.assertIn("openai/gpt-4o-mini",bazaar)
        self.assertFalse(any("embedding" in model or "whisper" in model for model in bazaar))

    def test_gateway_chat_requests_use_their_own_keys_and_endpoints(self):
        from unittest.mock import Mock
        response=Mock(status_code=200)
        response.json.return_value={"choices":[{"message":{"content":"{\"ok\":true}"}}],"usage":{"prompt_tokens":10,"completion_tokens":5,"cost_usd":0.002}}
        cases=[
            ("orcarouter","ORCAROUTER_API_KEY","https://api.orcarouter.ai/v1/chat/completions","orca-key"),
            ("bazaarlink","BAZAARLINK_API_KEY","https://api.bazaarlink.ai/v1/chat/completions","bazaar-key"),
        ]
        for provider,env_name,url,key in cases:
            with self.subTest(provider=provider), patch.object(engine,"HTTP") as http, \
                 patch.object(engine,"ORK" if provider=="orcarouter" else "BLK",key), \
                 patch.object(engine,"record_spend") as spend, patch.object(engine,"record_action") as action, patch.object(engine,"log"):
                http.post.return_value=response
                output=engine._raw_once(provider,"system","prompt","orchestrator","provider/model")
                self.assertEqual(output,'{"ok":true}')
                args=http.post.call_args
                self.assertEqual(args.args[0],url)
                self.assertEqual(args.kwargs["headers"]["Authorization"],"Bearer "+key)
                if provider=="orcarouter":
                    self.assertEqual(args.kwargs["headers"]["X-OrcaRouter-Include-Cost"],"true")
                self.assertEqual(args.kwargs["json"]["model"],"provider/model")
                spend.assert_called_once_with(engine.SPENDBF,0.002)
                self.assertEqual(action.call_args.kwargs["cost_usd"],0.002)

    def test_agentrouter_and_routeway_are_enabled_and_use_their_own_endpoints(self):
        from unittest.mock import Mock
        response=Mock(status_code=200)
        response.json.return_value={"choices":[{"message":{"content":"{\"ok\":true}"}}],"usage":{"prompt_tokens":7,"completion_tokens":9}}
        cases=[
            ("agentrouter","ARK","https://agentrouter.org/v1/chat/completions","agent-key"),
            ("routeway","RWK","https://api.routeway.ai/v1/chat/completions","routeway-key"),
        ]
        for provider,key_attr,url,key in cases:
            with self.subTest(provider=provider), patch.object(engine,"HTTP") as http, \
                 patch.object(engine,key_attr,key), patch.object(engine,"record_spend"), \
                 patch.object(engine,"record_action"), patch.object(engine,"log"):
                http.post.return_value=response
                output=engine._raw_once(provider,"system","prompt","orchestrator","provider/model")
                self.assertEqual(output,'{"ok":true}')
                self.assertEqual(http.post.call_args.args[0],url)
                self.assertEqual(http.post.call_args.kwargs["headers"]["Authorization"],"Bearer "+key)
                self.assertEqual(http.post.call_args.kwargs["json"]["model"],"provider/model")

    def test_agentrouter_and_routeway_join_provider_rotation_when_configured(self):
        with patch.object(engine,"ARK","agent-key"), patch.object(engine,"RWK","routeway-key"), \
             patch.object(engine,"PROVIDER_ROTATION",{"orchestrator":0}), patch.object(engine,"log"):
            providers=engine.provider_order("orchestrator")
        self.assertIn("agentrouter",providers)
        self.assertIn("routeway",providers)

    def test_leader_text_unwraps_nested_object_content(self):
        self.assertEqual(engine.leader_text({"reply":{"content":"The house is running."}}),"The house is running.")
        self.assertEqual(engine.leader_text("[object Object]"),"")
        self.assertEqual(engine.leader_text({"message":{"text":"A readable answer"}}),"A readable answer")

    def test_gemini_catalog_attempts_are_capped_even_when_env_requests_40(self):
        models=["model-"+str(index) for index in range(34)]
        with patch.dict(engine.os.environ, {"AI_HOUSE_GEMINI_MAX_MODEL_ATTEMPTS": "40"}), \
             patch.object(engine, "MODEL_ROTATION", {}), \
             patch.object(engine, "model_candidates", return_value=models), \
             patch.object(engine, "_raw_once", side_effect=RuntimeError("429 quota exceeded for model")) as request, \
             patch.object(engine, "log"):
            with self.assertRaisesRegex(RuntimeError, "3 attempts"):
                engine.raw("gemini", "system", "prompt", "orchestrator")
        self.assertEqual(request.call_count, 3)

    def test_duckduckgo_timeout_opens_circuit_and_prevents_repeated_waits(self):
        with patch.dict(engine.os.environ, {"AI_HOUSE_FREE_SEARCH": "1"}), \
             patch.object(engine, "FREE_SEARCH_COOLDOWN_UNTIL", 0), \
             patch.object(engine.time, "monotonic", side_effect=[100, 100, 101]), \
             patch.object(engine.HTTP, "get", side_effect=TimeoutError("connection timed out")) as request, \
             patch.object(engine, "log"):
            self.assertEqual(engine.duckduckgo_search("first query"), [])
            self.assertEqual(engine.duckduckgo_search("second query"), [])
            cooldown=engine.FREE_SEARCH_COOLDOWN_UNTIL
            request.assert_called_once()
            self.assertEqual(request.call_args.kwargs["timeout"], 6)
        self.assertEqual(cooldown, 700)

    def test_search_deduplicates_same_url_from_multiple_providers(self):
        shared={"url":"https://same.example/page","content":"source"}
        with patch.object(engine,"T","key"), patch.object(engine,"EX","key"), \
             patch.object(engine,"search_provider_ready",return_value=True), \
             patch.object(engine,"search_allowed",return_value=True), \
             patch.object(engine,"exa_allowed",return_value=True), \
             patch.object(engine,"tavily_search",return_value=[shared]), \
             patch.object(engine,"exa_search",return_value=[shared]), \
             patch.object(engine,"duckduckgo_search",return_value=[shared]), \
             patch.object(engine,"log"):
            results=engine.search("duplicate test")
        self.assertEqual(len(results),1)


    def test_cloudflare_workers_ai_is_in_provider_rotation_and_uses_account_scoped_endpoint(self):
        from unittest.mock import Mock
        response=Mock(status_code=200)
        response.json.return_value={"choices":[{"message":{"content":"{\"ok\":true}"}}],"usage":{"prompt_tokens":12,"completion_tokens":8}}
        with patch.object(engine,"CFK","cf-token"), patch.object(engine,"CF_ACCOUNT_ID","account-123"), patch.object(engine,"CFB","https://api.cloudflare.com/client/v4/accounts/account-123/ai/v1"), patch.object(engine,"PROVIDER_ROTATION",{"orchestrator":0}), patch.object(engine,"HTTP") as http, patch.object(engine,"record_spend"), patch.object(engine,"record_action"), patch.object(engine,"log"):
            providers=engine.provider_order("orchestrator")
            self.assertIn("cloudflare",providers)
            http.post.return_value=response
            output=engine._raw_once("cloudflare","system","prompt","orchestrator","@cf/meta/llama-3.3-70b-instruct-fp8-fast")
        self.assertEqual(output,"{\"ok\":true}")
        args=http.post.call_args
        self.assertEqual(args.args[0],"https://api.cloudflare.com/client/v4/accounts/account-123/ai/v1/chat/completions")
        self.assertEqual(args.kwargs["headers"]["Authorization"],"Bearer cf-token")
        self.assertEqual(args.kwargs["json"]["model"],"@cf/meta/llama-3.3-70b-instruct-fp8-fast")

    def test_cloudflare_model_pool_uses_workers_ai_model_ids(self):
        with patch.object(engine,"CFM","@cf/meta/llama-3.3-70b-instruct-fp8-fast"), patch.object(engine,"provider_model_catalog",return_value=None), patch.object(engine,"log"):
            models=engine.model_candidates("cloudflare","orchestrator")
        self.assertEqual(models[0],"@cf/meta/llama-3.3-70b-instruct-fp8-fast")
        self.assertTrue(all(model.startswith("@cf/") for model in models))
    def test_json_response_gets_one_repair_attempt(self):
        with patch.object(engine,"ask",side_effect=["not json at all", '{"ok":true}']), patch.object(engine,"log"):
            self.assertEqual(engine.ask_json("researcher","make JSON","ok"),{"ok":True})

    def test_waiting_approval_task_wakes_after_owner_answers(self):
        task={"id":"publish","status":"waiting_approval","approval_id":"abc123","depends_on":["research"]}
        tasks=[{"id":"research","status":"completed"},task]
        with patch.object(engine,"get_answer",return_value="yes"), patch.object(engine,"get_brief_answer",return_value=None):
            self.assertTrue(engine.task_ready(task,tasks))

    def test_waiting_approval_task_stays_asleep_until_answered(self):
        task={"id":"publish","status":"waiting_approval","approval_id":"abc123","depends_on":["research"]}
        tasks=[{"id":"research","status":"completed"},task]
        with patch.object(engine,"get_answer",return_value=None), patch.object(engine,"get_brief_answer",return_value=None):
            self.assertFalse(engine.task_ready(task,tasks))

    def test_nvidia_fast_models_are_tried_before_slow_large_models(self):
        with patch.object(engine,"NVIDIA_MODELS",[]), patch.object(engine,"provider_model_catalog",return_value=None), patch.object(engine,"log"):
            models=engine.model_candidates("nvidia","orchestrator")
        self.assertEqual(models[0],"meta/llama-3.1-8b-instruct")
        self.assertEqual(models[1],"nvidia/nemotron-3.5-bolt-e4b")
if __name__=="__main__":
    unittest.main()
