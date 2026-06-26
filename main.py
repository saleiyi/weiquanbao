#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
维权宝 - 统一入口
支持两种模式：桌面窗口（默认）和浏览器模式（--browser）
"""
import os, sys, threading, time, logging

# --noconsole 模式下 stdout/stderr 为 None
if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w', encoding='utf-8')
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w', encoding='utf-8')

# PyInstaller 打包后资源目录修正
if getattr(sys, 'frozen', False):
    project_root = os.path.dirname(sys.executable)
else:
    project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

import config

# 日志
log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
handlers = [logging.FileHandler(os.path.join(config.LOGS_DIR, "weiquanbao.log"), encoding="utf-8")]
if sys.stdout and hasattr(sys.stdout, 'isatty') and sys.stdout.isatty():
    handlers.append(logging.StreamHandler(sys.stdout))
logging.basicConfig(level=logging.INFO, format=log_format, handlers=handlers)
logger = logging.getLogger(__name__)


def start_server():
    """在后台线程启动 FastAPI 服务器"""
    from web.api import app
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=config.WEB_PORT, log_level="warning")


def wait_for_server(timeout=15):
    """等待服务器启动"""
    import urllib.request
    url = f"http://127.0.0.1:{config.WEB_PORT}/api/platforms"
    for _ in range(timeout * 10):
        try:
            urllib.request.urlopen(url, timeout=1)
            return True
        except Exception:
            time.sleep(0.1)
    return False


def main():
    logger.info("=" * 50)
    logger.info("维权宝 - 聊天记录导出工具")
    logger.info("=" * 50)

    # 判断启动模式
    browser_mode = "--browser" in sys.argv

    # 启动服务器
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()
    logger.info(f"服务器启动中... http://127.0.0.1:{config.WEB_PORT}")

    # 等待服务器就绪
    if not wait_for_server():
        logger.error("服务器启动超时")
        return

    logger.info("服务器已就绪")

    if browser_mode:
        # 浏览器模式：打开系统浏览器
        import webbrowser
        webbrowser.open(f"http://127.0.0.1:{config.WEB_PORT}")
        print(f"已在浏览器中打开 http://127.0.0.1:{config.WEB_PORT}")
        print("按 Ctrl+C 退出")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
    else:
        # 桌面窗口模式
        try:
            import webview
            webview.create_window(
                "维权宝 - 聊天记录取证与AI分析",
                f"http://127.0.0.1:{config.WEB_PORT}",
                width=1280,
                height=800,
                min_size=(900, 600),
                text_select=True,
            )
            webview.start(debug=False)
        except Exception as e:
            logger.warning(f"桌面窗口启动失败: {e}，回退到浏览器模式")
            import webbrowser
            webbrowser.open(f"http://127.0.0.1:{config.WEB_PORT}")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass


if __name__ == "__main__":
    main()
