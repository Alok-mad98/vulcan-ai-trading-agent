@echo off
cd /d "C:\Users\alokp\OneDrive\Desktop\vulcan"
set PYTHONIOENCODING=utf-8
"venv\Scripts\python.exe" -m vulcan.remote --once >> logs\poller.log 2>&1
