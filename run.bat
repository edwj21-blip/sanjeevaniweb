@echo off
title Sanjeevani – Blood Donor Platform
color 0C

echo.
echo  ==============================================
echo   SANJEEVANI (സഞ്ജീവനി) Blood Donor Platform
echo   Donate Blood. Save Lives.
echo  ==============================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python 3.10+ from https://www.python.org
    pause
    exit /b 1
)

echo [1/4] Installing requirements...
pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo [ERROR] Failed to install requirements.
    pause
    exit /b 1
)

echo [2/4] Running database migrations...
python manage.py migrate
if errorlevel 1 (
    echo [ERROR] Migration failed.
    pause
    exit /b 1
)

echo [3/4] Collecting static files...
python manage.py collectstatic --noinput --clear >nul 2>&1

echo [4/4] Starting Sanjeevani server...
echo.
echo  ============================================
echo   Server started at: http://127.0.0.1:8000
echo   Press Ctrl+C to stop the server
echo  ============================================
echo.
echo  ADMIN PANEL:  http://127.0.0.1:8000/admin/
echo  To create admin:  python manage.py createsuperuser
echo.
start http://127.0.0.1:8000
python manage.py runserver

pause
