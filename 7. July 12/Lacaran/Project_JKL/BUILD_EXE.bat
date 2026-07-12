@echo off
title Build BuildScope EXE
cd /d "%~dp0"

echo.
echo Building BuildScopeApp.exe...
echo.

where py >nul 2>nul
if %errorlevel%==0 (
    py -m pip install pyinstaller
    py -m PyInstaller --onefile --name BuildScopeApp main.py
    goto done
)

where python >nul 2>nul
if %errorlevel%==0 (
    python -m pip install pyinstaller
    python -m PyInstaller --onefile --name BuildScopeApp main.py
    goto done
)

echo Python was not found. Install Python or select a Python interpreter in Visual Studio Code.
goto end

:done
echo.
echo Finished. Look for:
echo dist\BuildScopeApp.exe

:end
echo.
pause
