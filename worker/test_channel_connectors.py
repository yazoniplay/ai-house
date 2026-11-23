import os
import unittest
from unittest.mock import patch

from channel_connectors import connection_status, ConnectorError, _gumroad_token, _youtube_token


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


if __name__ == "__main__":
    unittest.main()
