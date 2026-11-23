import tempfile,unittest
from pathlib import Path
from datetime import datetime,timezone
from search_fallback import classify_search_failure,mark_failure,provider_ready,next_retry
class SearchFallbackTests(unittest.TestCase):
 def test_credit_failure_waits_until_next_month(self):
  now=datetime(2026,11,23,12,tzinfo=timezone.utc);reason,until=classify_search_failure("402 insufficient credits",now)
  self.assertEqual(reason,"credits_exhausted");self.assertEqual(until,datetime(2026,12,1,tzinfo=timezone.utc))
 def test_monthly_usage_limit_waits_until_next_month(self):
  now=datetime(2026,11,23,12,tzinfo=timezone.utc);reason,until=classify_search_failure("monthly usage limit reached",now)
  self.assertEqual(reason,"monthly_exhausted");self.assertEqual(until,datetime(2026,12,1,tzinfo=timezone.utc))
 def test_quota_failure_waits_until_next_day(self):
  now=datetime(2026,11,23,12,tzinfo=timezone.utc);reason,until=classify_search_failure("429 quota exceeded",now)
  self.assertEqual(reason,"quota_limited");self.assertEqual(until,datetime(2026,11,24,tzinfo=timezone.utc))
 def test_provider_state_is_persistent_and_independent(self):
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/"providers.json";now=datetime(2026,11,23,12,tzinfo=timezone.utc);mark_failure(path,"tavily","402 out of credits",now)
   self.assertFalse(provider_ready(path,"tavily",now));self.assertTrue(provider_ready(path,"exa",now));self.assertEqual(next_retry(path,["tavily"],now),datetime(2026,12,1,tzinfo=timezone.utc))
if __name__=="__main__":unittest.main()
