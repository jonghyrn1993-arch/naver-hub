@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
"C:\Users\10075\AppData\Local\Programs\Python\Python313\python.exe" publish.py >> "%~dp0publish.log" 2>&1
