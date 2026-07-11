import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from ai_daily.logging import configure_logging


class LoggingTests(unittest.TestCase):
    def test_configure_logging_writes_a_rotating_local_log(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ai_daily.log"
            logger = configure_logging(path)
            logger.info("run=run-1 stage=ready")

            self.assertIn("stage=ready", path.read_text(encoding="utf-8"))
            for handler in logger.handlers[:]:
                logger.removeHandler(handler)
                handler.close()
