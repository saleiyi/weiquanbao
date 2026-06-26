#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
维权宝 - QQ 平台模块

两种数据源：
  1. qq-chat-exporter 导出文件（推荐）
     扫描 ~/.qq-chat-exporter/exports/ 下的 JSON 导出文件

  2. QQ 本地数据库（需解密，暂未实现）
     Tencent Files\[QQ号]\Msg\QQ.db
"""
import os, sys, re, json, logging
from datetime import datetime
from platforms.base import PlatformBase, Conversation, Message

logger = logging.getLogger(__name__)

# QQ 数据根目录
QQ_BASE = os.path.expanduser("~/Documents/Tencent Files")

# qq-chat-exporter 导出目录
QCE_BASE = os.path.expanduser("~/.qq-chat-exporter")
QCE_EXPORTS = os.path.join(QCE_BASE, "exports")
QCE_SCHEDULED = os.path.join(QCE_BASE, "scheduled-exports")

CHAT_TYPE_MAP = {
    "group": "group",
    "friend": "single",
    "single": "single",
}


class QQPlatform(PlatformBase):

    @property
    def name(self):
        return "qq"

    @property
    def display_name(self):
        return "QQ"

    def __init__(self):
        self._ready = False
        self._data_dir = None
        self._exports = []
        self._convs_cache = []
        self._msgs_cache = {}

    def is_available(self):
        """检测是否有 QQ 数据"""
        if os.path.isdir(QCE_EXPORTS):
            exports = self._scan_exports()
            if exports:
                return True
        if os.path.isdir(QQ_BASE):
            for f in os.listdir(QQ_BASE):
                if f.isdigit() and len(f) >= 5:
                    msg_dir = os.path.join(QQ_BASE, f, "Msg")
                    if os.path.exists(os.path.join(msg_dir, "QQ.db")):
                        return True
        return False

    def discover(self):
        """发现 QQ 数据源"""
        # 优先用 qq-chat-exporter 导出
        if os.path.isdir(QCE_EXPORTS):
            self._exports = self._scan_exports()
            if self._exports:
                logger.info(f"发现 {len(self._exports)} 个 qq-chat-exporter 导出文件")
                self._load_all_exports()
                self._ready = True
                return True

        # 降级到本地 QQ 数据
        self._find_data_dir()
        if self._data_dir:
            logger.info(f"发现本地 QQ 数据: {self._data_dir}")
            self._ready = True
            return True

        logger.warning("QQ: 未找到数据")
        return False

    def _scan_exports(self):
        """扫描 qq-chat-exporter 的导出目录"""
        exports = []
        if not os.path.isdir(QCE_EXPORTS):
            return exports

        for entry in os.listdir(QCE_EXPORTS):
            entry_path = os.path.join(QCE_EXPORTS, entry)
            if os.path.isdir(entry_path):
                manifest = os.path.join(entry_path, "manifest.json")
                export_json = os.path.join(entry_path, "export.json")
                if os.path.exists(manifest):
                    exports.append({
                        "type": "chunked",
                        "path": entry_path,
                        "name": entry,
                        "mtime": os.path.getmtime(entry_path),
                    })
                elif os.path.exists(export_json):
                    exports.append({
                        "type": "single",
                        "path": export_json,
                        "name": entry,
                        "mtime": os.path.getmtime(export_json),
                    })
            elif entry.endswith(".json") and os.path.isfile(entry_path):
                exports.append({
                    "type": "single",
                    "path": entry_path,
                    "name": entry,
                    "mtime": os.path.getmtime(entry_path),
                })

        exports.sort(key=lambda x: x["mtime"], reverse=True)
        return exports

    def _read_export_json(self, export_path):
        """读取导出文件的 JSON 数据"""
        try:
            with open(export_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"读取导出文件失败: {export_path}: {e}")
            return None

    def _load_all_exports(self):
        """加载所有导出文件的会话和消息"""
        for export in self._exports:
            try:
                data = None
                if export["type"] == "single":
                    data = self._read_export_json(export["path"])
                elif export["type"] == "chunked":
                    data = self._read_export_json(
                        os.path.join(export["path"], "export.json")
                    )

                if data:
                    convs, msgs = self._parse_export_data(data)
                    for c in convs:
                        # 去重：同 cid 不重复添加
                        if not any(existing.cid == c.cid for existing in self._convs_cache):
                            self._convs_cache.append(c)
                    self._msgs_cache.update(msgs)
            except Exception as e:
                logger.warning(f"加载导出文件失败 {export['name']}: {e}")

        logger.info(f"QQ: 共加载 {len(self._convs_cache)} 个会话, {len(self._msgs_cache)} 个消息缓存")

    def _parse_export_data(self, data):
        """解析 qq-chat-exporter 的导出数据为统一格式"""
        convs = []
        msgs_map = {}

        chat_info = data.get("chatInfo", {})
        cid = chat_info.get("id", "unknown")
        chat_type = CHAT_TYPE_MAP.get(chat_info.get("type"), "group")
        title = chat_info.get("name", chat_info.get("title", "未知会话"))

        conv = Conversation(
            cid=cid,
            title=title,
            type=chat_type,
            platform="qq",
            member_count=chat_info.get("memberCount", 0),
        )
        convs.append(conv)

        messages = data.get("messages", [])
        parsed = []
        for m in messages:
            msg = self._parse_message(m, cid)
            if msg:
                parsed.append(msg)

        msgs_map[cid] = parsed
        return convs, msgs_map

    def _parse_message(self, raw, cid):
        """解析单条 CleanMessage 格式消息"""
        try:
            content = raw.get("content", {})
            if isinstance(content, dict):
                text = content.get("text", "")
            else:
                text = str(content)

            sender = raw.get("sender", {})
            sender_name = sender.get("name", "") or sender.get("nickname", "") or "未知"
            sender_id = sender.get("uid", "") or sender.get("uin", "")

            timestamp = raw.get("timestamp", 0)
            if isinstance(timestamp, str):
                try:
                    timestamp = int(float(timestamp))
                except Exception:
                    timestamp = 0

            return Message(
                mid=str(raw.get("id", raw.get("seq", ""))),
                cid=cid,
                platform="qq",
                sender_name=sender_name,
                sender_id=sender_id,
                content=text,
                msg_type=1,
                timestamp=timestamp,
            )
        except Exception as e:
            logger.warning(f"解析消息失败: {e}")
            return None

    # ─── 外部文件导入 ────────────────────────────────────────────

    def import_exported_file(self, file_path):
        """导入文件（自动检测格式：JSON/TXT）"""
        path = file_path if isinstance(file_path, str) else str(file_path)
        if not os.path.exists(path):
            logger.error(f"文件不存在: {path}")
            return False

        # 根据扩展名选择解析方式
        if path.lower().endswith('.json'):
            return self._import_json(path)
        elif path.lower().endswith('.txt'):
            return self._import_txt(path)
        else:
            logger.error(f"不支持的文件格式: {path}")
            return False

    def _import_json(self, path):
        """导入 qq-chat-exporter 导出的 JSON 文件"""
        try:
            data = self._read_export_json(path)
            if not data:
                return False

            convs, msgs = self._parse_export_data(data)
            for c in convs:
                if not any(existing.cid == c.cid for existing in self._convs_cache):
                    self._convs_cache.append(c)
            self._msgs_cache.update(msgs)
            self._ready = True
            logger.info(f"QQ: 已导入 JSON {path}")
            return True
        except Exception as e:
            logger.error(f"QQ JSON 导入失败: {e}")
            return False

    def _import_txt(self, path):
        """导入 QQ 自带导出的 TXT 文件

        QQ 导出格式：
        ==========消息记录==========
        消息分组:我的好友
        消息对象:张三
        ============================

        2024-01-15 10:30:45 张三(12345678)
        你好啊

        2024-01-15 10:31:02 我
        你好！
        """
        try:
            import re
            with open(path, 'r', encoding='utf-8-sig') as f:
                content = f.read()

            # 解析消息对象名称
            title_match = re.search(r'消息对象[:：](.+)', content)
            title = title_match.group(1).strip() if title_match else os.path.basename(path).rsplit('.', 1)[0]

            # 解析消息
            # 格式: 2024-01-15 10:30:45 张三(12345678) 或 2024-01-15 10:30:45 我
            msg_pattern = re.compile(
                r'^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+(.+?)(?:\((\d+)\))?\s*$',
                re.MULTILINE
            )

            messages = []
            matches = list(msg_pattern.finditer(content))

            for i, m in enumerate(matches):
                time_str = m.group(1)
                sender = m.group(2).strip()
                qq_num = m.group(3) or ""

                # 获取消息内容（到下一条消息或文件末尾）
                start = m.end()
                end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
                text = content[start:end].strip()

                if not text:
                    continue

                # 解析时间戳
                try:
                    from datetime import datetime as dt
                    ts = int(dt.strptime(time_str, "%Y-%m-%d %H:%M:%S").timestamp())
                except ValueError:
                    ts = None

                is_self = sender == '我'
                messages.append(Message(
                    mid=f"txt_{len(messages)}",
                    cid=f"txt_{title}",
                    platform="qq",
                    sender_name=sender,
                    sender_id="me" if is_self else (qq_num or sender),
                    content=text,
                    msg_type=1,
                    timestamp=ts,
                ))

            if not messages:
                logger.warning(f"QQ TXT: 未解析到消息 {path}")
                return False

            cid = f"txt_{title}"
            self._msgs_cache[cid] = messages
            self._convs_cache.append(Conversation(
                cid=cid, title=f"导入:{title}", type="single", platform="qq",
            ))
            self._ready = True
            logger.info(f"QQ: 已导入 TXT {len(messages)} 条消息: {title}")
            return True
        except Exception as e:
            logger.error(f"QQ TXT 导入失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _find_data_dir(self):
        """查找 QQ 本地数据目录"""
        if not os.path.isdir(QQ_BASE):
            return
        for f in os.listdir(QQ_BASE):
            if f.isdigit() and len(f) >= 5:
                msg_dir = os.path.join(QQ_BASE, f, "Msg")
                if os.path.exists(os.path.join(msg_dir, "QQ.db")):
                    self._data_dir = os.path.join(QQ_BASE, f)
                    self._qq_num = f
                    return

    # ─── 接口实现 ────────────────────────────────────────

    def get_conversations(self, keyword=None):
        """获取会话列表"""
        if not self._ready and not self.discover():
            return []

        if self._convs_cache:
            return self._filter_convs(self._convs_cache, keyword)

        return []

    def _filter_convs(self, convs, keyword):
        if not keyword:
            return convs
        return [c for c in convs if keyword.lower() in c.title.lower()]

    def get_messages(self, cid, limit=50, offset=0):
        """获取消息"""
        if cid in self._msgs_cache:
            msgs = self._msgs_cache[cid]
            end = offset + limit
            return msgs[offset:end]

        # 还没缓存，重新加载
        if not self._ready:
            self.get_conversations()
        if cid in self._msgs_cache:
            msgs = self._msgs_cache[cid]
            end = offset + limit
            return msgs[offset:end]

        return []

    def search_messages(self, keyword, limit=50, offset=0):
        """搜索消息"""
        if not self._ready and not self.discover():
            return []

        results = []
        for cid, msgs in self._msgs_cache.items():
            for m in msgs:
                if keyword.lower() in m.content.lower():
                    results.append(m)
                    if len(results) >= limit + offset:
                        return results[offset:offset + limit]
        return results[offset:offset + limit] if offset < len(results) else results

    def get_stats(self):
        """获取统计"""
        stats = {
            "exports": len(self._exports),
            "conversations": len(self._convs_cache),
            "cached_messages": sum(len(v) for v in self._msgs_cache.values()),
        }
        if self._exports:
            stats["latest_export"] = self._exports[0]["name"]
        return stats


def get_platform():
    return QQPlatform()
