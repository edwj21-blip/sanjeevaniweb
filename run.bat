@echo off
setlocal
cd /d "%~dp0"
title SANJEEVANI - Blood Donor Platform
echo.
echo  ==============================================
echo    SANJEEVANI  -  Donate Blood. Save Lives.
echo  ==============================================
echo.

rem ---- 1. find Python ----
set "PY="
where py >nul 2>&1
if not errorlevel 1 set "PY=py -3"
if not defined PY (
  where python >nul 2>&1
  if not errorlevel 1 set "PY=python"
)
if not defined PY (
  echo [ERROR] Python 3.10 or newer was not found.
  echo Install it from https://www.python.org/downloads/ and tick "Add Python to PATH".
  pause
  exit /b 1
)

rem ---- 2. virtual environment ----
if not exist "venv\Scripts\python.exe" (
  echo [1/6] Creating virtual environment ...
  %PY% -m venv venv
  if errorlevel 1 goto :fail
) else (
  echo [1/6] Virtual environment found.
)
set "VPY=%~dp0venv\Scripts\python.exe"

rem ---- 3. packages ----
echo [2/6] Installing packages (first time takes a few minutes) ...
"%VPY%" -m pip install --upgrade pip --quiet
"%VPY%" -m pip install -r requirements.txt --quiet
if errorlevel 1 goto :fail

rem ---- 4. .env (secret key + push keys) ----
echo [3/6] Preparing settings (.env) ...
"%VPY%" setup_env.py
if errorlevel 1 goto :fail

rem ---- 5. database ----
echo [4/6] Checking project and updating database ...
"%VPY%" manage.py check
if errorlevel 1 goto :fail
"%VPY%" manage.py migrate --noinput
if errorlevel 1 goto :fail

rem ---- 6. first-run questions (no parentheses, so %ANS% is read after you answer) ----
if exist ".setup_done" goto :skipfirst
echo.
set "ANS="
set /p ANS=Create 15 demo donors for testing? [y/N]: 
if /i "%ANS%"=="y" "%VPY%" manage.py create_sample_data
set "ANS="
set /p ANS=Create an admin login now? [y/N]: 
if /i "%ANS%"=="y" "%VPY%" manage.py createsuperuser
echo done> .setup_done
:skipfirst

echo.
echo [5/6] Starting the background scheduler (reminders + automatic availability) ...
start "SANJEEVANI scheduler" /min "%VPY%" manage.py run_scheduled_jobs --loop 600

echo [6/6] Starting website ...
echo.
echo   Website : http://127.0.0.1:8000
echo   Admin   : http://127.0.0.1:8000/admin/
echo   Staff dashboard : http://127.0.0.1:8000/staff/dashboard/
echo   Google Maps key : put GOOGLE_MAPS_API_KEY in the .env file, then restart.
echo   Stop    : press Ctrl+C in this window (and close the scheduler window).
echo.
start "" http://127.0.0.1:8000
"%VPY%" manage.py runserver 127.0.0.1:8000
goto :end

:fail
echo.
echo [ERROR] Something failed - read the message above, then send it to your developer or to Claude.
pause
exit /b 1

:end
endlocal
