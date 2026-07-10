@echo off
setlocal
cd /d "%~dp0.."
set "PYTHONPATH=%CD%\src"
py -m ai_daily.cli daily
exit /b %ERRORLEVEL%
