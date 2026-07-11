@echo off
setlocal
cd /d "%~dp0.."
py -m uv run --project . ai-daily web
pause
