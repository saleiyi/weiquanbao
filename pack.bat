@echo off
chcp 65001 >nul 2>&1
setlocal

echo.
echo  ========================================
echo    Weiquanbao - Pack for Sharing
echo  ========================================
echo.

set DIST=weiquanbao_share

if exist "%DIST%" rmdir /s /q "%DIST%"
mkdir "%DIST%"

echo [1/4] Copying files...

copy /y "main.py" "%DIST%\" >nul 2>&1
copy /y "config.py" "%DIST%\" >nul 2>&1
copy /y "scheduler.py" "%DIST%\" >nul 2>&1
copy /y "dt_parser.py" "%DIST%\" >nul 2>&1
copy /y "dt_exporter.py" "%DIST%\" >nul 2>&1
copy /y "wechat_exporter.py" "%DIST%\" >nul 2>&1
copy /y "decrypt.py" "%DIST%\" >nul 2>&1
copy /y "attachment.py" "%DIST%\" >nul 2>&1
copy /y "ai_analyzer.py" "%DIST%\" >nul 2>&1
copy /y "start.bat" "%DIST%\" >nul 2>&1
copy /y "README.md" "%DIST%\" >nul 2>&1

echo [2/4] Copying directories...

xcopy "web" "%DIST%\web\" /e /i /q /y >nul 2>&1
xcopy "platforms" "%DIST%\platforms\" /e /i /q /y >nul 2>&1
xcopy "tools" "%DIST%\tools\" /e /i /q /y >nul 2>&1

echo [3/4] Creating directories...

mkdir "%DIST%\data" >nul 2>&1
mkdir "%DIST%\data\exports" >nul 2>&1
mkdir "%DIST%\data\decrypted" >nul 2>&1
mkdir "%DIST%\logs" >nul 2>&1

echo [4/4] Done!
echo.
echo  ========================================
echo    Share folder created: %DIST%
echo  ========================================
echo.
echo  How to share:
echo    1. Zip the "%DIST%" folder
echo    2. Send the zip to your friend
echo    3. Friend unzips and runs start.bat
echo.
echo  Requirements for your friend:
echo    - Python 3.8+ (add to PATH during install)
echo    - Download: https://www.python.org/downloads/
echo.

pause
