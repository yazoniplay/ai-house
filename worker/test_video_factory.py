import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from video_factory import VideoFactoryError, _inside, search_pexels


class VideoFactoryTests(unittest.TestCase):
    def test_asset_path_cannot_escape_project(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as outside:
            with self.assertRaises(VideoFactoryError):
                _inside(root, Path(outside) / "secret.txt")

    def test_pexels_search_requires_local_api_key(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(VideoFactoryError, "PEXELS_API_KEY"):
                search_pexels("cinematic city")

    def test_empty_query_rejected(self):
        with patch.dict(os.environ, {"PEXELS_API_KEY": "test-key"}):
            with self.assertRaisesRegex(VideoFactoryError, "query"):
                search_pexels("")


if __name__ == "__main__":
    unittest.main()
