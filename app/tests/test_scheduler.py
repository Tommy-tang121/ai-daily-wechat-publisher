import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from ai_daily.scheduler import add_minutes, task_arguments


class SchedulerTests(unittest.TestCase):
    def test_add_minutes_wraps_midnight(self):
        self.assertEqual(add_minutes("23:58", 5), "00:03")

    def test_task_arguments_quote_paths_with_spaces(self):
        arguments = task_arguments(Path(r"E:\App Development\AI Daily\app\scripts\run_scheduled.bat"))
        self.assertEqual(arguments, '"E:\\App Development\\AI Daily\\app\\scripts\\run_scheduled.bat"')
