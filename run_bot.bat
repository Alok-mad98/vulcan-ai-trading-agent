@echo off
cd /d "C:\Users\alokp\OneDrive\Desktop\vulcan"
set PYTHONIOENCODING=utf-8
"venv\Scripts\python.exe" -m vulcan.main >> logs\bot.log 2>&1
