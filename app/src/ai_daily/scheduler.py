import subprocess
import tempfile
import xml.etree.ElementTree as ET
import os
from datetime import date, datetime, timedelta
from pathlib import Path


TASK_NAME = "AI Daily Publisher"
LEGACY_CHECK_TASK = "AI Daily Publisher - Check"
TASK_NAMESPACE = "http://schemas.microsoft.com/windows/2004/02/mit/task"


def add_minutes(time_text: str, minutes: int) -> str:
    moment = datetime.strptime(time_text, "%H:%M") + timedelta(minutes=minutes)
    return moment.strftime("%H:%M")


def task_arguments(script: Path) -> str:
    return f'"{script}"'


def task_xml(schedule_time: str, script: Path) -> str:
    datetime.strptime(schedule_time, "%H:%M")
    ET.register_namespace("", TASK_NAMESPACE)
    tag = lambda name: f"{{{TASK_NAMESPACE}}}{name}"

    root = ET.Element(tag("Task"), {"version": "1.4"})
    triggers = ET.SubElement(root, tag("Triggers"))
    trigger = ET.SubElement(triggers, tag("CalendarTrigger"))
    ET.SubElement(trigger, tag("StartBoundary")).text = f"{date.today().isoformat()}T{schedule_time}:00"
    ET.SubElement(trigger, tag("Enabled")).text = "true"
    by_day = ET.SubElement(trigger, tag("ScheduleByDay"))
    ET.SubElement(by_day, tag("DaysInterval")).text = "1"

    principals = ET.SubElement(root, tag("Principals"))
    principal = ET.SubElement(principals, tag("Principal"), {"id": "Author"})
    ET.SubElement(principal, tag("UserId")).text = os.environ.get("USERNAME", "")
    ET.SubElement(principal, tag("LogonType")).text = "InteractiveToken"
    ET.SubElement(principal, tag("RunLevel")).text = "LeastPrivilege"

    settings = ET.SubElement(root, tag("Settings"))
    for name, value in (
        ("MultipleInstancesPolicy", "IgnoreNew"),
        ("StartWhenAvailable", "true"),
        ("AllowStartOnDemand", "true"),
        ("Enabled", "true"),
        ("ExecutionTimeLimit", "PT0S"),
    ):
        ET.SubElement(settings, tag(name)).text = value
    actions = ET.SubElement(root, tag("Actions"), {"Context": "Author"})
    action = ET.SubElement(actions, tag("Exec"))
    ET.SubElement(action, tag("Command")).text = "cmd.exe"
    ET.SubElement(action, tag("Arguments")).text = f'/d /c "{task_arguments(script)}"'
    ET.SubElement(action, tag("WorkingDirectory")).text = str(script.parent)
    return ET.tostring(root, encoding="unicode", xml_declaration=True).replace("utf-8", "utf-16", 1)


def install(schedule_time: str, script: Path, runner=subprocess.run) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".xml", encoding="utf-16", delete=False) as file:
        file.write(task_xml(schedule_time, script))
        definition = Path(file.name)
    try:
        command = ["schtasks", "/create", "/tn", TASK_NAME, "/xml", str(definition), "/f"]
        result = runner(command, capture_output=True, text=True, timeout=20)
        if result.returncode:
            raise RuntimeError((result.stderr or result.stdout or "计划任务创建失败").strip())
        runner(
            ["schtasks", "/delete", "/tn", LEGACY_CHECK_TASK, "/f"],
            capture_output=True,
            text=True,
            timeout=20,
        )
    finally:
        definition.unlink(missing_ok=True)


class WindowsTasks:
    """Small boundary around Windows Task Scheduler for the daily entry point."""

    def __init__(self, script: Path, runner=subprocess.run):
        self.script = Path(script)
        self.runner = runner

    def install(self, schedule_time: str) -> dict:
        install(schedule_time, self.script, runner=self.runner)
        return self.status()

    def status(self) -> dict:
        result = self.runner(
            ["schtasks", "/query", "/tn", TASK_NAME, "/xml"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if not result.returncode:
            try:
                task = ET.fromstring(result.stdout)
            except ET.ParseError as exc:
                raise RuntimeError("无法读取计划任务定义") from exc
            arguments = task.findtext(f".//{{{TASK_NAMESPACE}}}Exec/{{{TASK_NAMESPACE}}}Arguments", default="")
            expected_script = str(self.script.resolve()).replace("/", "\\").casefold()
            configured = expected_script in arguments.replace("/", "\\").casefold()
            if configured:
                return {"installed": True, "configured": True, "task_name": TASK_NAME}
            return {
                "installed": True,
                "configured": False,
                "task_name": TASK_NAME,
                "message": "检测到同名旧任务，需要保存定时时间后更新",
            }
        detail = (result.stderr or result.stdout or "").lower()
        if "cannot find" in detail or "not exist" in detail or "找不到" in detail:
            return {"installed": False, "task_name": TASK_NAME}
        raise RuntimeError((result.stderr or result.stdout or "无法读取计划任务状态").strip())
