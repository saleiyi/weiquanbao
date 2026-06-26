@echo off
chcp 65001 >nul 2>&1

echo.
echo  ========================================
echo    Weiquanbao - Build EXE
echo  ========================================
echo.

:: Check Python
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo  [ERROR] Python not found
    echo  Please install Python 3.8+
    pause
    exit /b 1
)

:: Install dependencies
echo  [1/3] Installing dependencies...
pip install fastapi uvicorn apscheduler pymem cryptography zstandard pyinstaller --quiet

:: Build
echo  [2/3] Building EXE (this takes 3-5 minutes)...
echo.

pyinstaller --onefile --name weiquanbao --noconsole ^
    --add-data "web;web" ^
    --add-data "platforms;platforms" ^
    --add-data "tools;tools" ^
    --add-data "config.py;." ^
    --add-data "scheduler.py;." ^
    --add-data "dt_parser.py;." ^
    --add-data "dt_exporter.py;." ^
    --add-data "wechat_exporter.py;." ^
    --add-data "decrypt.py;." ^
    --add-data "attachment.py;." ^
    --add-data "ai_analyzer.py;." ^
    --hidden-import=uvicorn.logging ^
    --hidden-import=uvicorn.loops ^
    --hidden-import=uvicorn.loops.auto ^
    --hidden-import=uvicorn.protocols ^
    --hidden-import=uvicorn.protocols.http ^
    --hidden-import=uvicorn.protocols.http.auto ^
    --hidden-import=uvicorn.protocols.websockets ^
    --hidden-import=uvicorn.protocols.websockets.auto ^
    --hidden-import=uvicorn.lifespan ^
    --hidden-import=uvicorn.lifespan.on ^
    main.py

if %errorlevel% neq 0 (
    echo.
    echo  [ERROR] Build failed
    pause
    exit /b 1
)

:: Done
echo.
echo  [3/3] Build complete!
echo.
echo  ========================================
echo    EXE location: dist\weiquanbao.exe
echo  ========================================
echo.
echo  How to use:
echo    1. Double-click weiquanbao.exe
echo    2. Open browser: http://localhost:8090
echo.
echo  How to share:
echo    1. Send dist\weiquanbao.exe to your friend
echo    2. Friend double-clicks to run
echo    3. No Python installation needed!
echo.

pause
