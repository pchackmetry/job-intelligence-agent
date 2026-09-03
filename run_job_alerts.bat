@echo off
cd /d D:\projects\job-intelligence-agent

set PYTHONPATH=D:\projects\job-intelligence-agent
set PYTHONIOENCODING=utf-8

call .\.venv\Scripts\python.exe .\workers\daily_pipeline.py

exit /b %ERRORLEVEL%