@echo off
setlocal
set PYTHONUTF8=1
set PYTHONDONTWRITEBYTECODE=1
if not defined RENOVATION_PYTHON set "RENOVATION_PYTHON=python"
"%RENOVATION_PYTHON%" -B "%~dp0scripts\cli.py" %*
exit /b %errorlevel%
