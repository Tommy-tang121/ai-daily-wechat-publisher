import sys
import unittest
import xml.etree.ElementTree as ET
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from ai_daily.scheduler import LEGACY_CHECK_TASK, TASK_NAME, WindowsTasks, add_minutes, task_arguments, task_xml


def task_definition(arguments: str) -> str:
    return f'''<?xml version="1.0" encoding="UTF-16"?>
<Task xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <Actions><Exec><Command>cmd.exe</Command><Arguments>{arguments}</Arguments></Exec></Actions>
</Task>'''


class Completed:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class RecordingRunner:
    def __init__(self, *results):
        self.results = list(results)
        self.commands = []

    def __call__(self, command, **kwargs):
        self.commands.append((command, kwargs))
        return self.results.pop(0)


class SchedulerTests(unittest.TestCase):
    def test_add_minutes_wraps_midnight(self):
        self.assertEqual(add_minutes("23:58", 5), "00:03")

    def test_task_arguments_quote_paths_with_spaces(self):
        arguments = task_arguments(Path(r"E:\App Development\AI Daily\app\scripts\run_scheduled.bat"))
        self.assertEqual(arguments, '"E:\\App Development\\AI Daily\\app\\scripts\\run_scheduled.bat"')

    def test_task_xml_retries_failures_and_runs_the_quoted_daily_script(self):
        document = ET.fromstring(task_xml("09:30", Path(r"E:\App Development\AI Daily\app\scripts\run_scheduled.bat")))
        namespace = {"task": "http://schemas.microsoft.com/windows/2004/02/mit/task"}

        self.assertEqual(document.findtext(".//task:RestartOnFailure/task:Interval", namespaces=namespace), "PT15M")
        self.assertEqual(document.findtext(".//task:RestartOnFailure/task:Count", namespaces=namespace), "3")
        self.assertEqual(document.findtext(".//task:Principal/task:UserId", namespaces=namespace), os.environ.get("USERNAME", ""))
        self.assertEqual(document.findtext(".//task:Principal/task:LogonType", namespaces=namespace), "InteractiveToken")
        self.assertIn('"E:\\App Development\\AI Daily\\app\\scripts\\run_scheduled.bat"', document.findtext(".//task:Actions/task:Exec/task:Arguments", namespaces=namespace))

    def test_windows_tasks_installs_new_task_before_removing_legacy_check_task(self):
        runner = RecordingRunner(
            Completed(),
            Completed(returncode=1, stderr="legacy task is absent"),
            Completed(stdout=task_definition('"E:\\App Development\\AI Daily\\app\\scripts\\run_scheduled.bat"')),
        )
        tasks = WindowsTasks(Path(r"E:\App Development\AI Daily\app\scripts\run_scheduled.bat"), runner=runner)

        status = tasks.install("09:30")

        self.assertTrue(status["installed"])
        self.assertEqual(runner.commands[0][0][0:4], ["schtasks", "/create", "/tn", TASK_NAME])
        self.assertIn("/xml", runner.commands[0][0])
        self.assertEqual(runner.commands[1][0], ["schtasks", "/delete", "/tn", LEGACY_CHECK_TASK, "/f"])
        self.assertEqual(runner.commands[2][0], ["schtasks", "/query", "/tn", TASK_NAME, "/xml"])

    def test_windows_tasks_does_not_delete_legacy_task_when_new_task_creation_fails(self):
        runner = RecordingRunner(Completed(returncode=1, stderr="access denied"))
        tasks = WindowsTasks(Path("run_scheduled.bat"), runner=runner)

        with self.assertRaisesRegex(RuntimeError, "access denied"):
            tasks.install("09:30")

        self.assertEqual(len(runner.commands), 1)

    def test_windows_tasks_status_reports_missing_task_without_throwing(self):
        runner = RecordingRunner(Completed(returncode=1, stderr="ERROR: The system cannot find the file specified."))

        status = WindowsTasks(Path("run_scheduled.bat"), runner=runner).status()

        self.assertEqual(status, {"installed": False, "task_name": TASK_NAME})

    def test_windows_tasks_status_accepts_the_current_app_script_only(self):
        script = Path(r"E:\App Development\AI Daily\app\scripts\run_scheduled.bat")
        runner = RecordingRunner(Completed(stdout=task_definition(f'/d /c "{script}"')))

        status = WindowsTasks(script, runner=runner).status()

        self.assertEqual(status, {"installed": True, "configured": True, "task_name": TASK_NAME})

    def test_windows_tasks_status_flags_a_same_named_task_pointing_to_an_old_script(self):
        script = Path(r"E:\App Development\AI Daily\app\scripts\run_scheduled.bat")
        runner = RecordingRunner(Completed(stdout=task_definition(r'/c "E:\App Development\AI Daily\run_scheduled.bat"')))

        status = WindowsTasks(script, runner=runner).status()

        self.assertEqual(status, {
            "installed": True,
            "configured": False,
            "task_name": TASK_NAME,
            "message": "检测到同名旧任务，需要保存定时时间后更新",
        })

    def test_windows_tasks_status_accepts_localized_missing_task_errors(self):
        runner = RecordingRunner(Completed(returncode=1, stderr="错误: 系统找不到指定的文件。"))

        status = WindowsTasks(Path("run_scheduled.bat"), runner=runner).status()

        self.assertEqual(status, {"installed": False, "task_name": TASK_NAME})
