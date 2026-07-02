import ctypes
import subprocess
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from datetime import date, datetime
from app.scheduler import get_task_info, TASK_NAME


def main():
    info = get_task_info(TASK_NAME)
    if not info:
        ctypes.windll.user32.MessageBoxW(0, f"找不到计划任务: {TASK_NAME}", "AI Daily · 检查", 0x10 | 0x1000)
        return

    last_run_raw = info["last_run"]
    last_result = info["last_result"]
    next_run_raw = info["next_run"]

    today_str = date.today().strftime("%Y/%m/%d")
    msg = ""
    icon = 0x40

    if last_run_raw.startswith(today_str):
        if last_result == "0":
            msg = f"✅ 今日已成功执行\n\n上次运行: {last_run_raw}\n结果码: {last_result}\n下次运行: {next_run_raw}"
            icon = 0x40
        else:
            msg = f"❌ 执行失败 (代码: {last_result})\n\n上次运行: {last_run_raw}\n下次运行: {next_run_raw}"
            icon = 0x10
    else:
        subprocess.run(["schtasks", "/run", "/tn", TASK_NAME], capture_output=True, timeout=15)
        msg = (f"⚠️ 今日尚未触发，已自动重新触发\n\n"
               f"上次运行: {last_run_raw}\n下次运行: {next_run_raw}")
        icon = 0x30

    ctypes.windll.user32.MessageBoxW(0, msg, "AI Daily · 定时任务状态", icon | 0x1000)


if __name__ == "__main__":
    main()
