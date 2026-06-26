import os, sys, logging

# PyInstaller 打包后使用 exe 所在目录，否则使用脚本目录
if getattr(sys, 'frozen', False):
    PROJECT_DIR = os.path.dirname(sys.executable)
else:
    PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

DATA_DIR = os.path.join(PROJECT_DIR, "data")
LOGS_DIR = os.path.join(PROJECT_DIR, "logs")

# DingTalk config
USER_UID = ""
DINGTALK_DATA_DIR = ""
ENCRYPTED_DB = ""
DINGWAVE_PATH = os.path.join(PROJECT_DIR, "tools", "dingwave.exe")
ENCRYPTED_DB_DIR = ""
DECRYPTED_DIR = os.path.join(DATA_DIR, "decrypted")
DECRYPTED_DB_PATH = os.path.join(DECRYPTED_DIR, "dingtalk.db")
EXPORT_DIR = os.path.join(DATA_DIR, "exports")
SYNC_STATE_FILE = os.path.join(DATA_DIR, "sync_state.json")
SYNC_INTERVAL_HOURS = 4
COPY_RETRY_COUNT = 3
COPY_RETRY_DELAY = 30

WEB_HOST = "0.0.0.0"
WEB_PORT = 8090

# AI 分析配置
AI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
AI_API_BASE = os.environ.get("OPENAI_API_BASE", "https://api.openai.com/v1")
AI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

ATTACHMENT_DIRS = {
    "image": "ImageFiles",
    "audio": "AudioFiles",
    "video": "VideoFiles",
    "resource_cache": "resource_cache",
}

# 消息内容类型常量
CONTENT_TYPE_TEXT = 1
CONTENT_TYPE_IMAGE = 2
CONTENT_TYPE_VOICE = 300
CONTENT_TYPE_FILE = 501
CONTENT_TYPE_RICH_TEXT = 1200
CONTENT_TYPE_QUOTE = 3100
CONTENT_TYPE_APPROVAL = 1400
CONTENT_TYPE_VIDEO_CALL = 1101

CONTENT_TYPE_NAMES = {
    1: "文本",
    2: "图片",
    300: "语音",
    501: "文件",
    1101: "通话",
    1200: "富文本",
    1201: "互动卡片",
    1202: "系统提示",
    1400: "审批",
    2900: "互动卡片",
    2950: "小程序卡片",
    3100: "引用/回复",
}

for d in [DATA_DIR, DECRYPTED_DIR, EXPORT_DIR, LOGS_DIR]:
    os.makedirs(d, exist_ok=True)


def _detect_dingtalk():
    global USER_UID, DINGTALK_DATA_DIR, ENCRYPTED_DB, ENCRYPTED_DB_DIR
    appdata = os.environ.get("APPDATA", "")
    if not appdata:
        userprofile = os.environ.get("USERPROFILE", "")
        if userprofile:
            appdata = os.path.join(userprofile, "AppData", "Roaming")
    dingtalk_base = os.path.join(appdata, "DingTalk")
    if not os.path.isdir(dingtalk_base):
        return False
    v2_dirs = []
    for entry in os.listdir(dingtalk_base):
        if entry.endswith(("_v2", "_v3")):
            full_path = os.path.join(dingtalk_base, entry)
            if os.path.isdir(full_path):
                db_file = os.path.join(full_path, "DBFiles", "dingtalk.db")
                if os.path.exists(db_file):
                    uid = entry.rsplit("_v", 1)[0]
                    mtime = os.path.getmtime(db_file)
                    v2_dirs.append((uid, full_path, mtime))
    if not v2_dirs:
        return False
    v2_dirs.sort(key=lambda x: x[2], reverse=True)
    uid, path, _ = v2_dirs[0]
    USER_UID = uid
    DINGTALK_DATA_DIR = path
    ENCRYPTED_DB_DIR = os.path.join(path, "DBFiles")
    ENCRYPTED_DB = os.path.join(ENCRYPTED_DB_DIR, "dingtalk.db")
    return True


_detect_dingtalk()
