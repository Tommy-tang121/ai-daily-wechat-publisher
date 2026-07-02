"""Check today's task status"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app.scheduler import get_task_info, get_trigger_time, TASK_NAME, CHECK_TASK_NAME
from datetime import date

today = date.today().strftime("%Y/%m/%d")
print(f"今天日期: {today}")

for name, label in [(TASK_NAME, "Publisher"), (CHECK_TASK_NAME, "Check")]:
    info = get_task_info(name)
    if info:
        print(f"\n{label}:")
        print(f"  last_run:  {info['last_run']}")
        print(f"  result:    {info['last_result']}")
        print(f"  next_run:  {info['next_run']}")
        if info['last_run'].startswith(today):
            print(f"  今天已运行: {'✅ 成功' if info['last_result'] == '0' else '❌ 失败'}")
        else:
            print(f"  今天未运行")
    else:
        print(f"\n{label}: NOT FOUND")
