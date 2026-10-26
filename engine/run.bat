@echo off
setlocal
set PYTHONDONTWRITEBYTECODE=1
set PYTHONUTF8=1
if not defined RENOVATION_PYTHON set "RENOVATION_PYTHON=python"
"%RENOVATION_PYTHON%" -c "import sys; assert sys.version_info >= (3,10)" >nul 2>&1
if errorlevel 1 (
  echo Python 3.10+ was not found. Set RENOVATION_PYTHON to an existing Python executable.
  exit /b 1
)
if "%~1"=="" (
  echo Commands: package-check, configure --out PROJECT/machine.json, init, doctor, new-job, voice-check, voice, align, render, qa, finalize
  echo Start with: run.bat configure --out PROJECT/machine.json
  exit /b 0
)
"%RENOVATION_PYTHON%" -B "%~dp0scripts\workflow.py" %*
exit /b %errorlevel%
