import os
import json
import tempfile
import unittest
from unittest.mock import patch

from channel_connectors import connection_status, ConnectorError, _gumroad_token, _youtube_token, _reserve_publish_slot, GUMROAD_DAILY_PRODUCT_CAP, YOUTUBE_DAILY_UPLOAD_CAP


class ConnectorConfigTests(unittest.TestCase):
    def test_status_never_requires_or_returns_secret_values(self):
        with patch.dict(os.environ, {"GUMROAD_ACCESS_TOKEN": "secret-a", "YOUTUBE_ACCESS_TOKEN": "secret-b"}):
            status = connection_status()
        self.assertTrue(status["gumroad"]["connected"])
        self.assertTrue(status["youtube"]["connected"])
        self.assertNotIn("secret-a", repr(status))
        self.assertNotIn("secret-b", repr(status))

    def test_missing_gumroad_token_is_clear(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ConnectorError, "GUMROAD_ACCESS_TOKEN"):
                _gumroad_token()

    def test_missing_youtube_token_is_clear(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ConnectorError, "YOUTUBE_ACCESS_TOKEN"):
                _youtube_token()


    def test_gumroad_daily_cap_is_three_and_persistent(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "limits.json")
            for _ in range(GUMROAD_DAILY_PRODUCT_CAP):
                _reserve_publish_slot("gumroad_products", GUMROAD_DAILY_PRODUCT_CAP, path)
            with self.assertRaisesRegex(ConnectorError, "Daily gumroad_products limit reached"):
                _reserve_publish_slot("gumroad_products", GUMROAD_DAILY_PRODUCT_CAP, path)
            with open(path, encoding="utf-8") as handle:
                stored = json.load(handle)
            from datetime import datetime, timezone
            today = datetime.now(timezone.utc).date().isoformat()
            self.assertEqual(stored[today]["gumroad_products"], 3)

    def test_youtube_daily_cap_is_one_and_persistent(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "limits.json")
            _reserve_publish_slot("youtube_uploads", YOUTUBE_DAILY_UPLOAD_CAP, path)
            with self.assertRaisesRegex(ConnectorError, "Daily youtube_uploads limit reached"):
                _reserve_publish_slot("youtube_uploads", YOUTUBE_DAILY_UPLOAD_CAP, path)
            with open(path, encoding="utf-8") as handle:
                stored = json.load(handle)
            from datetime import datetime, timezone
            today = datetime.now(timezone.utc).date().isoformat()
            self.assertEqual(stored[today]["youtube_uploads"], 1)

if __name__ == "__main__":
    unittest.main()
