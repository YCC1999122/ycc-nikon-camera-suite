@echo off
REM Launch the control-center GUI. / 启动「启动工具」界面（主入口）
set PY="%~dp0.venv\Scripts\python.exe"
if not exist %PY% set PY=python
%PY% "%~dp0launcher.py"
if errorlevel 1 pause
