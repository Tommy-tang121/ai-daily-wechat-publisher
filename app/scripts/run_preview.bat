@echo off
setlocal
cd /d "%~dp0.."
set "PYTHONPATH=%CD%\src"
py -m ai_daily.cli web --preview
pause
