@echo off
chcp 65001 >nul
title 维权宝 - 聊天记录取证工具
echo.
echo  ██████████████████████████████████████
echo  █                                    █
echo  █    🛡️  维权宝 - 聊天记录取证工具   █
echo  █                                    █
echo  ██████████████████████████████████████
echo.
echo  正在启动...
echo.

:: 检查 Python
where python >nul 2>&1
if %errorlevel% neq 0 (
    where py >nul 2>&1
    if %errorlevel% neq 0 (
        echo  [错误] 未找到 Python
        echo.
        echo  请先安装 Python:
        echo  https://www.python.org/downloads/
        echo.
        echo  安装时请勾选 "Add Python to PATH"
        echo.
        pause
        exit /b 1
    )
    set PYTHON=py
) else (
    set PYTHON=python
)

:: 安装依赖（首次运行）
if not exist ".venv" (
    echo  首次运行，正在安装依赖...
    %PYTHON% -m venv .venv
    call .venv\Scripts\activate.bat
    pip install fastapi uvicorn apscheduler pymem cryptography zstandard -q
    echo  依赖安装完成！
    echo.
) else (
    call .venv\Scripts\activate.bat
)

:: 启动
echo  启动成功！请在浏览器中打开:
echo.
echo  ═══════════════════════════════════════
echo    http://localhost:8090
echo  ═══════════════════════════════════════
echo.
echo  按 Ctrl+C 停止服务
echo.

%PYTHON% main.py

pause
