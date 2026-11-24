@echo off
setlocal
cd /d "%~dp0"
if not exist "venv\Scripts\python.exe" (
  echo Run run.bat once first to set everything up.
  pause
  exit /b 1
)
set "VPY=%~dp0venv\Scripts\python.exe"
echo Checking that models and migrations match ...
"%VPY%" manage.py makemigrations --check --dry-run
echo.
echo Running automated tests ...
"%VPY%" manage.py test core -v 2
echo.
pause
endlocal
