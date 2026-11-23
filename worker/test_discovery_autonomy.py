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

if __name__=="__main__":
    unittest.main()
