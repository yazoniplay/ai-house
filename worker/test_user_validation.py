import unittest
from datetime import datetime, timezone
from user_validation import verify_usage_events

class ProductUsageValidationTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,11,23,12,0,tzinfo=timezone.utc)

    def event(self,uid,event="core_action",**extra):
        return {"user_id":uid,"event_name":event,"environment":"production","timestamp":self.now.isoformat(),**extra}

    def test_requires_ten_distinct_real_users(self):
        events=[self.event("user-"+str(i).zfill(8)) for i in range(9)]
        self.assertEqual(verify_usage_events(events,now=self.now)["status"],"pending")
        events.append(self.event("user-00000010"))
        report=verify_usage_events(events,now=self.now)
        self.assertEqual(report["status"],"verified")
        self.assertEqual(report["distinct_production_users"],10)

    def test_repeated_events_from_one_user_do_not_inflate_user_count(self):
        report=verify_usage_events([self.event("same-user-123") for _ in range(20)],now=self.now)
        self.assertEqual(report["distinct_production_users"],1)

    def test_owner_test_bot_and_nonproduction_are_excluded(self):
        events=[
            self.event("owner-12345678"),
            self.event("test-user-123456",is_test=True),
            self.event("bot-user-123456",is_bot=True),
            self.event("dev-user-123456",environment="development"),
        ]
        report=verify_usage_events(events,owner_user_ids=["owner-12345678"],now=self.now)
        self.assertEqual(report["distinct_production_users"],0)
        self.assertEqual(report["status"],"pending")

    def test_page_views_and_marketing_clicks_are_not_usage(self):
        events=[self.event("visitor-1234567","page_view"),self.event("visitor-2234567","marketing_click")]
        self.assertEqual(verify_usage_events(events,now=self.now)["distinct_production_users"],0)

    def test_old_events_are_not_counted(self):
        events=[self.event("old-user-123456",timestamp="2026-09-01T00:00:00Z")]
        report=verify_usage_events(events,now=self.now)
        self.assertEqual(report["distinct_production_users"],0)
        self.assertEqual(report["rejected_events"]["invalid_or_old_timestamp"],1)

    def test_report_uses_fingerprints_not_raw_user_ids(self):
        report=verify_usage_events([self.event("person@example.com")],now=self.now)
        self.assertNotIn("person@example.com",str(report))
        self.assertEqual(len(report["privacy_safe_user_fingerprints"]),1)

if __name__=="__main__":
    unittest.main()
