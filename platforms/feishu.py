#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
维权宝 - 飞书平台模块

三种工作模式（自动选择优先级）：
  1. lark-cli 模式 — 通过官方 CLI 工具拉取（推荐，支持用户身份）
  2. API 模式 — 通过飞书开放平台 API 拉取（需要 app_id/app_secret）
  3. 浏览器模式 — Playwright 抓取网页版（已废弃）

lark-cli 安装: npx @larksuite/cli@latest install
lark-cli 配置: lark-cli config init && lark-cli auth login --recommend
"""
import os, sys, re, time, json, logging, subprocess, shutil
from datetime import datetime
from platforms.base import PlatformBase, Conversation, Message

logger = logging.getLogger(__name__)

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

FEISHU_CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".colleague-skill", "feishu_config.json")
FEISHU_API = "https://open.feishu.cn/open-apis"


def _find_npx():
    """查找 npx 可执行文件路径"""
    # Windows 上 npx 可能是 .cmd 文件
    for name in ["npx.cmd", "npx"]:
        path = shutil.which(name)
        if path:
            return path
    # 常见路径
    common_paths = [
        r"D:\Program Files\nodejs\npx.cmd",
        r"C:\Program Files\nodejs\npx.cmd",
        os.path.expanduser(r"~\AppData\Roaming\npm\npx.cmd"),
    ]
    for p in common_paths:
        if os.path.exists(p):
            return p
    return None


def _has_lark_cli():
    """检测 lark-cli 是否可用（通过 npx）"""
    npx = _find_npx()
    if not npx:
        return False
    try:
        result = subprocess.run([npx, "@larksuite/cli@latest", "--version"],
                                capture_output=True, text=True, timeout=60, shell=True)
        return result.returncode == 0 and "lark-cli" in result.stdout
    except Exception:
        return False


def _run_lark_cli(args, timeout=60):
    """运行 lark-cli 命令（通过 npx）"""
    npx = _find_npx()
    if not npx:
        logger.error("npx 未找到，请安装 Node.js")
        return None
    cmd = [npx, "@larksuite/cli@latest"] + args
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, encoding='utf-8')
        if result.returncode != 0:
            logger.error(f"lark-cli 错误: {result.stderr[:200]}")
            return None
        return json.loads(result.stdout) if result.stdout.strip() else None
    except subprocess.TimeoutExpired:
        logger.error("lark-cli 超时")
        return None
    except json.JSONDecodeError:
        logger.error(f"lark-cli 输出不是 JSON: {result.stdout[:200]}")
        return None
    except Exception as e:
        logger.error(f"lark-cli 执行失败: {e}")
        return None


class FeishuPlatform(PlatformBase):

    @property
    def name(self):
        return "feishu"

    @property
    def display_name(self):
        return "飞书"

    def __init__(self):
        self._ready = False
        self._mode = None  # 'lark-cli', 'api', 'browser'
        self._token = None
        self._token_expires = 0
        self._api_config = None
        self._page = None
        self._playwright = None
        self._context = None
        self._convs_cache = []
        self._msgs_cache = {}

        self._check_available_modes()

    def _check_available_modes(self):
        """检测可用模式（lark-cli > API > browser）"""
        if _has_lark_cli():
            logger.info("飞书: lark-cli 模式可用")
            self._mode = 'lark-cli'
            return
        if self._find_api_config():
            logger.info("飞书: API 模式可用")
            self._mode = 'api'
            return
        try:
            from playwright.sync_api import sync_playwright
            logger.info("飞书: 浏览器模式可用")
            self._mode = 'browser'
        except ImportError:
            pass

    def _find_api_config(self):
        """查找飞书 API 凭证"""
        app_id = os.environ.get("FEISHU_APP_ID", "")
        app_secret = os.environ.get("FEISHU_APP_SECRET", "")
        if app_id and app_secret:
            self._api_config = {"app_id": app_id, "app_secret": app_secret}
            return True
        if os.path.exists(FEISHU_CONFIG_PATH):
            try:
                cfg = json.loads(open(FEISHU_CONFIG_PATH, encoding='utf-8').read())
                if cfg.get('app_id') and cfg.get('app_secret'):
                    self._api_config = cfg
                    return True
            except Exception:
                pass
        return False

    def is_available(self):
        return self._mode is not None

    def discover(self):
        """初始化连接"""
        if self._mode == 'lark-cli':
            return self._discover_lark_cli()
        elif self._mode == 'api':
            return self._init_api()
        elif self._mode == 'browser':
            return self._init_browser()
        return False

    def _discover_lark_cli(self):
        """检测 lark-cli 登录状态"""
        # 检查是否已登录
        data = _run_lark_cli(["auth", "status"], timeout=10)
        if data is None:
            # 尝试直接调用一个简单 API 来检测
            data = _run_lark_cli(["im", "+chat-list", "--page-size", "1"], timeout=15)
            if data is not None:
                self._ready = True
                logger.info("飞书 lark-cli: 已登录")
                return True
            logger.warning("飞书 lark-cli: 未登录，请运行 'lark-cli auth login --recommend'")
            return False
        self._ready = True
        logger.info("飞书 lark-cli: 已登录")
        return True

    def _init_api(self):
        """获取 tenant_access_token"""
        if not self._api_config:
            if not self._find_api_config():
                return False
        if not HAS_REQUESTS:
            logger.error("飞书: requests 未安装")
            return False

        try:
            resp = requests.post(
                f"{FEISHU_API}/auth/v3/tenant_access_token/internal",
                json={"app_id": self._api_config["app_id"], "app_secret": self._api_config["app_secret"]},
                timeout=10,
            )
            data = resp.json()
            if data.get("code") == 0:
                self._token = data["tenant_access_token"]
                self._token_expires = time.time() + data.get("expire", 7200) - 300
                self._ready = True
                logger.info("飞书 API 初始化成功")
                return True
            else:
                logger.error(f"飞书 API token 获取失败: {data.get('msg', data)}")
                return False
        except Exception as e:
            logger.error(f"飞书 API 初始化失败: {e}")
            return False

    def _init_browser(self):
        """初始化 Playwright 浏览器（已废弃）"""
        logger.warning("飞书浏览器模式已废弃，请使用 lark-cli 模式")
        return False

    def _api_headers(self):
        if time.time() > self._token_expires:
            self._init_api()
        return {"Authorization": f"Bearer {self._token}"}

    # ─── 获取会话列表 ──────────────────────────────────────────────────

    def get_conversations(self, keyword=None):
        if self._convs_cache:
            if keyword:
                return [c for c in self._convs_cache if keyword.lower() in c.title.lower()]
            return self._convs_cache

        if not self._ready and not self.discover():
            return []

        if self._mode == 'lark-cli':
            convs = self._get_convs_lark_cli(keyword)
        elif self._mode == 'api':
            convs = self._get_convs_api(keyword)
        else:
            convs = []

        self._convs_cache = convs
        return convs

    def _get_convs_lark_cli(self, keyword=None):
        """通过 lark-cli 获取会话列表"""
        convs = []
        page_token = ""

        while True:
            args = ["im", "+chat-list", "--page-size", "100", "--types", "group,p2p"]
            if page_token:
                args.extend(["--page-token", page_token])
            if keyword:
                args.extend(["--query", keyword])

            data = _run_lark_cli(args, timeout=30)
            if data is None:
                break

            items = data.get("data", {}).get("items", [])
            for chat in items:
                name = chat.get("name", "")
                chat_id = chat.get("chat_id", "")
                chat_type = "group" if chat.get("chat_type") == "group" else "single"
                convs.append(Conversation(
                    cid=chat_id, title=name, type=chat_type,
                    platform="feishu", member_count=chat.get("user_count", 0),
                ))

            if not data.get("data", {}).get("has_more", False):
                break
            page_token = data.get("data", {}).get("page_token", "")

        logger.info(f"飞书 lark-cli: 获取 {len(convs)} 个会话")
        return convs

    def _get_convs_api(self, keyword=None):
        """通过 API 获取会话列表"""
        convs = []
        page_token = ""
        try:
            while True:
                params = {"page_size": 100}
                if page_token:
                    params["page_token"] = page_token
                resp = requests.get(f"{FEISHU_API}/im/v1/chats", headers=self._api_headers(), params=params, timeout=15)
                data = resp.json()
                if data.get("code") != 0:
                    break
                for chat in data.get("data", {}).get("items", []):
                    name = chat.get("name", "")
                    if keyword and keyword.lower() not in name.lower():
                        continue
                    convs.append(Conversation(
                        cid=chat.get("chat_id", ""), title=name, type="group",
                        platform="feishu", member_count=chat.get("user_count", 0),
                    ))
                if not data.get("data", {}).get("has_more", False):
                    break
                page_token = data.get("data", {}).get("page_token", "")
        except Exception as e:
            logger.error(f"飞书 API 获取会话失败: {e}")
        return convs

    # ─── 获取消息 ──────────────────────────────────────────────────────

    def get_messages(self, cid, limit=50, offset=0):
        if cid in self._msgs_cache:
            msgs = self._msgs_cache[cid]
            return msgs[offset:offset + limit]

        if not self._ready and not self.discover():
            return []

        if self._mode == 'lark-cli':
            msgs = self._get_msgs_lark_cli(cid, limit, offset)
        elif self._mode == 'api':
            msgs = self._get_msgs_api(cid, limit, offset)
        else:
            msgs = []

        return msgs

    def _get_msgs_lark_cli(self, cid, limit=50, offset=0):
        """通过 lark-cli 获取消息"""
        messages = []
        page_token = ""

        while len(messages) < limit + offset:
            args = ["im", "+chat-messages-list", "--chat-id", cid, "--page-size", "50", "--sort", "asc"]
            if page_token:
                args.extend(["--page-token", page_token])

            data = _run_lark_cli(args, timeout=30)
            if data is None:
                break

            items = data.get("data", {}).get("messages", [])
            if not items:
                break

            for item in items:
                msg = self._parse_lark_message(item, cid)
                if msg:
                    messages.append(msg)

            if not data.get("data", {}).get("has_more", False):
                break
            page_token = data.get("data", {}).get("page_token", "")

        return messages[offset:offset + limit]

    def _parse_lark_message(self, item, cid):
        """解析 lark-cli 返回的消息"""
        try:
            msg_type = item.get("msg_type", "")
            body = item.get("body", {})
            content_str = body.get("content", "")

            text = self._extract_text(content_str, msg_type)

            ts = item.get("create_time", "")
            if ts:
                try:
                    ts = int(ts) // 1000 if len(ts) > 10 else int(ts)
                except Exception:
                    ts = None

            sender = item.get("sender", {})
            sender_id = sender.get("sender_id", {}).get("open_id", "")

            return Message(
                mid=item.get("message_id", ""), cid=cid, platform="feishu",
                sender_name=sender_id, sender_id=sender_id, content=text, timestamp=ts,
            )
        except Exception as e:
            logger.warning(f"飞书消息解析失败: {e}")
            return None

    def _extract_text(self, content_str, msg_type):
        """提取消息文本"""
        if not content_str:
            return f"[{msg_type}]"
        try:
            content = json.loads(content_str)
        except Exception:
            return content_str if isinstance(content_str, str) else f"[{msg_type}]"

        if msg_type == "text":
            return content.get("text", "")
        if msg_type == "post":
            lines = []
            for v in content.values():
                if isinstance(v, dict):
                    for para in v.get("content", []):
                        if isinstance(para, list):
                            parts = [e.get("text", "") for e in para if isinstance(e, dict) and e.get("tag") == "text"]
                            if parts:
                                lines.append("".join(parts))
            return "\n".join(lines) or f"[{msg_type}]"
        if msg_type == "image": return "[图片]"
        if msg_type == "audio": return "[语音]"
        if msg_type == "video": return "[视频]"
        if msg_type == "file": return "[文件]"
        if msg_type == "sticker": return "[表情]"
        if msg_type == "interactive": return "[卡片消息]"
        if msg_type == "share_chat": return "[分享群聊]"
        if msg_type == "share_user": return "[分享用户]"
        return f"[{msg_type}]"

    def _get_msgs_api(self, cid, limit=50, offset=0):
        """通过 API 获取消息"""
        messages = []
        page_token = ""
        try:
            while len(messages) < limit + offset:
                params = {"container_id_type": "chat", "container_id": cid, "page_size": 50, "sort_type": "ByCreateTimeDesc"}
                if page_token:
                    params["page_token"] = page_token
                resp = requests.get(f"{FEISHU_API}/im/v1/messages", headers=self._api_headers(), params=params, timeout=15)
                data = resp.json()
                if data.get("code") != 0:
                    break
                for item in data.get("data", {}).get("items", []):
                    msg = self._parse_lark_message(item, cid)
                    if msg:
                        messages.append(msg)
                if not data.get("data", {}).get("has_more", False):
                    break
                page_token = data.get("data", {}).get("page_token", "")
        except Exception as e:
            logger.error(f"飞书 API 获取消息失败: {e}")
        messages.reverse()
        return messages[offset:offset + limit]

    def search_messages(self, keyword, limit=50, offset=0):
        """搜索消息（仅 lark-cli 模式支持）"""
        if not self._ready and not self.discover():
            return []
        if self._mode != 'lark-cli':
            return []

        messages = []
        page_token = ""

        while len(messages) < limit + offset:
            args = ["im", "+messages-search", "--query", keyword, "--page-size", "50"]
            if page_token:
                args.extend(["--page-token", page_token])

            data = _run_lark_cli(args, timeout=30)
            if data is None:
                break

            items = data.get("data", {}).get("items", [])
            if not items:
                break

            for item in items:
                msg = self._parse_lark_message(item, item.get("chat_id", ""))
                if msg:
                    messages.append(msg)

            if not data.get("data", {}).get("has_more", False):
                break
            page_token = data.get("data", {}).get("page_token", "")

        return messages[offset:offset + limit]

    def get_stats(self):
        return {"mode": self._mode, "ready": self._ready, "conversations": len(self._convs_cache)}


def get_platform():
    return FeishuPlatform()
