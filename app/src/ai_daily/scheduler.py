import subprocess
from datetime import datetime, timedelta
from pathlib import Path


TASK_NAME = "AI Daily Publisher"
LEGACY_CHECK_TASK = "AI Daily Publisher - Check"


def add_minutes(time_text: str, minutes: int) -> str:
    moment = datetime.strptime(time_text, "%H:%M") + timedelta(minutes=minutes)
    return moment.strftime("%H:%M")


def task_arguments(script: Path) -> str:
    return f'"{script}"'


def install(schedule_time: str, script: Path, runner=subprocess.run) -> None:
    command = ["schtasks", "/create", "/tn", TASK_NAME, "/tr", task_arguments(script),
               "/sc", "daily", "/st", schedule_time, "/f"]
    result = runner(command, capture_output=True, text=True, timeout=20)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout or "计划任务创建失败").strip())
    runner(["schtasks", "/delete", "/tn", LEGACY_CHECK_TASK, "/f"], capture_output=True, text=True, timeout=20)
