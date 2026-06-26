@echo off
chcp 65001 >nul 2>&1
title Weiquanbao - Chat Record Export Tool

echo.
echo  ========================================
echo    Weiquanbao - Chat Record Export Tool
echo  ========================================
echo.
echo  Starting...
echo.

:: Check Python
where python >nul 2>&1
if %errorlevel% neq 0 (
    where py >nul 2>&1
    if %errorlevel% neq 0 (
        echo  [ERROR] Python not found
        echo.
        echo  Please install Python 3.8+:
        echo  https://www.python.org/downloads/
        echo.
        echo  IMPORTANT: Check "Add Python to PATH" during install
        echo.
        pause
        exit /b 1
    )
    set PYTHON=py
) else (
    set PYTHON=python
)

:: Install dependencies (first run)
if not exist ".venv" (
    echo  First run, installing dependencies...
    echo  This may take 2-3 minutes...
    echo.
    %PYTHON% -m venv .venv
    call .venv\Scripts\activate.bat
    pip install fastapi uvicorn apscheduler pymem cryptography zstandard -q
    echo.
    echo  Dependencies installed!
    echo.
) else (
    call .venv\Scripts\activate.bat
)

:: Start server
echo  ========================================
echo    Open browser: http://localhost:8090
echo  ========================================
echo.
echo  Press Ctrl+C to stop
echo.

%PYTHON% main.py

pause
