@echo off
title BuildScope Consultation Portal
cd /d "%~dp0"

echo.
echo Starting BuildScope Consultation Portal...
echo.
echo If the browser does not open automatically, open:
echo http://127.0.0.1:8000
echo.

where py >nul 2>nul
if %errorlevel%==0 (
    py main.py
    goto end
)

where python >nul 2>nul
if %errorlevel%==0 (
    python main.py
    goto end
)

echo Python was not found.
echo Install Python or select a Python interpreter in Visual Studio Code.

:end
echo.
echo App stopped. Press any key to close this window.
pause >nul
