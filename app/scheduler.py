import os
import sys
import subprocess

TASK_NAME = "AI Daily Publisher"
CHECK_TASK_NAME = "AI Daily Publisher - Check"
PYTHON_PATH = getattr(sys, "_base_executable", sys.executable) or "python"


def _add_minutes(time_str, minutes):
    h, m = int(time_str.split(":")[0]), int(time_str.split(":")[1])
    m += minutes
    h += m // 60
    m %= 60
    return f"{h:02d}:{m:02d}"


def create_or_update_tasks(schedule_time):
    subprocess.run(
        ["schtasks", "/change", "/tn", TASK_NAME, "/st", schedule_time],
        capture_output=True, text=True, timeout=10
    )
    _fix_task_settings(TASK_NAME)
    _create_check_task(schedule_time)


def _create_check_task(schedule_time):
    check_time = _add_minutes(schedule_time, 5)
    check_script = os.path.join(os.path.dirname(__file__), "check_daily.py")
    subprocess.run(
        ["schtasks", "/delete", "/tn", CHECK_TASK_NAME, "/f"],
        capture_output=True, text=True, timeout=10
    )
    ps_cmd = (
        f"$a = New-ScheduledTaskAction -Execute '{PYTHON_PATH}' -Argument '{check_script}'; "
        f"$t = New-ScheduledTaskTrigger -Daily -At '{check_time}'; "
        f"$p = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited; "
        f"Register-ScheduledTask -TaskName '{CHECK_TASK_NAME}' -Action $a -Trigger $t -Principal $p -Force"
    )
    subprocess.run(["powershell", "-Command", ps_cmd], capture_output=True, text=True, timeout=15)
    _fix_task_settings(CHECK_TASK_NAME)


def _fix_task_settings(task_name):
    """Fix battery/sleep defaults so task runs even when unplugged or asleep"""
    import tempfile
    xml_path = os.path.join(tempfile.gettempdir(), f"ai_{task_name.replace(' ', '_')}.xml")
    try:
        result = subprocess.run(
            ["schtasks", "/query", "/tn", task_name, "/xml"],
            capture_output=True, timeout=10
        )
        if result.returncode != 0:
            return
        with open(xml_path, "wb") as f:
            f.write(result.stdout)
    except Exception:
        return
    ps = (
        f"[xml]$doc = Get-Content '{xml_path}'; "
        f"$t = $doc.Task; "
        f"$t.Settings.DisallowStartIfOnBatteries = 'false'; "
        f"$t.Settings.StopIfGoingOnBatteries = 'false'; "
        f"$w = $doc.CreateElement('WakeToRun', $t.Settings.NamespaceURI); "
        f"$w.InnerText = 'true'; "
        f"$t.Settings.AppendChild($w); "
        f"$doc.Save('{xml_path}'); "
        f"schtasks /create /tn '{task_name}' /xml '{xml_path}' /f"
    )
    subprocess.run(["powershell", "-Command", ps], capture_output=True, timeout=15)


def get_trigger_time(task_name):
    try:
        xml = subprocess.run(
            ["schtasks", "/query", "/tn", task_name, "/xml"],
            capture_output=True, text=True, timeout=10
        )
        for line in xml.stdout.splitlines():
            if "<StartBoundary>" in line:
                t = line.split(">")[1].split("T")[1].split(":")[:2]
                return f"{t[0]}:{t[1]}"
    except Exception:
        pass
    return None


def get_task_info(task_name):
    import csv
    import io
    result = subprocess.run(
        ["schtasks", "/query", "/tn", task_name, "/v", "/fo", "csv"],
        capture_output=True, text=True, timeout=10
    )
    reader = csv.reader(io.StringIO(result.stdout.strip()))
    rows = [row for row in reader]
    if len(rows) < 2:
        return None
    values = rows[1]
    return {
        "last_run": values[5] if len(values) > 5 else "",
        "last_result": values[6] if len(values) > 6 else "",
        "next_run": values[2] if len(values) > 2 else "",
    }
