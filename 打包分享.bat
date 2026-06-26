@echo off
chcp 65001 >nul
echo ========================================
echo   维权宝 - 打包分享脚本
echo ========================================
echo.

:: 创建分享目录
set DIST_DIR=维权宝_分享版
if exist "%DIST_DIR%" rmdir /s /q "%DIST_DIR%"
mkdir "%DIST_DIR%"

echo [1/4] 复制核心文件...
copy "main.py" "%DIST_DIR%\" >nul
copy "config.py" "%DIST_DIR%\" >nul
copy "scheduler.py" "%DIST_DIR%\" >nul
copy "dt_parser.py" "%DIST_DIR%\" >nul
copy "dt_exporter.py" "%DIST_DIR%\" >nul
copy "wechat_exporter.py" "%DIST_DIR%\" >nul
copy "decrypt.py" "%DIST_DIR%\" >nul
copy "attachment.py" "%DIST_DIR%\" >nul
copy "启动维权宝.bat" "%DIST_DIR%\" >nul
copy "使用说明.txt" "%DIST_DIR%\" >nul

echo [2/4] 复制目录...
xcopy "web" "%DIST_DIR%\web\" /e /i /q >nul
xcopy "platforms" "%DIST_DIR%\platforms\" /e /i /q >nul
xcopy "tools" "%DIST_DIR%\tools\" /e /i /q >nul

echo [3/4] 创建必要目录...
mkdir "%DIST_DIR%\data" >nul
mkdir "%DIST_DIR%\data\exports" >nul
mkdir "%DIST_DIR%\data\decrypted" >nul
mkdir "%DIST_DIR%\logs" >nul

echo [4/4] 打包完成！
echo.
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo   分享包已创建: %DIST_DIR%
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.
echo 分享方式:
echo   1. 将「%DIST_DIR%」文件夹压缩成 zip
echo   2. 发送给对方
echo   3. 对方解压后双击「启动维权宝.bat」即可
echo.
echo 注意: 对方电脑需要安装 Python 3.8+
echo   下载地址: https://www.python.org/downloads/
echo   安装时请勾选 "Add Python to PATH"
echo.
pause
