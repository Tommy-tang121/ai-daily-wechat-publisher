@echo off
cd /d "E:\App Development\AI Daily"
"C:\Users\tsy79\AppData\Local\Python\pythoncore-3.14-64\python.exe" app/run_daily.py > app\logs\scheduled.log 2>&1
