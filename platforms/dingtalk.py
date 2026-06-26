#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
维权宝 - 钉钉平台模块
封装 dingtalk-exporter 的解密 + 解析逻辑
"""
import os, sys, logging, time
from datetime import datetime
from platforms.base import PlatformBase, Conversation, Message

logger = logging.getLogger(__name__)

# 引用 dingtalk-exporter 的模块
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__))))


class DingTalkPlatform(PlatformBase):

    @property
    def name(self):
        return "dingtalk"

    @property
    def display_name(self):
        return "钉钉"

    def __init__(self):
        self._decrypted_db = None
        self._conn = None
        self._user_uid = None
        self._data_dir = None

    def is_available(self):
        """检测钉钉是否有本地数据"""
        import config as cfg
        if not cfg.ENCRYPTED_DB:
            return False
        return os.path.exists(cfg.ENCRYPTED_DB)

    def discover(self):
        """解密钉钉数据库"""
        import config as cfg
        from decrypt import sync_decrypt

        try:
            self._data_dir = cfg.DINGTALK_DATA_DIR
            self._user_uid = cfg.USER_UID
            logger.info(f"钉钉数据目录: {self._data_dir}")
            logger.info(f"钉钉用户UID: {self._user_uid}")

            # 解密
            decrypted = sync_decrypt()
            self._decrypted_db = decrypted

            # 建立连接
            from dt_parser import get_connection
            self._conn = get_connection(decrypted)
            logger.info(f"钉钉数据库解密成功: {decrypted}")
            return True
        except Exception as e:
            logger.error(f"钉钉解密失败: {e}")
            return False

    def get_connection(self):
        """获取数据库连接（懒加载）"""
        if not self._conn:
            self.discover()
        return self._conn

    def get_conversations(self, keyword=None):
        """获取会话列表"""
        conn = self.get_connection()
        if not conn:
            return []

        from dt_parser import get_conversations
        results = get_conversations(conn, limit=99999, keyword=keyword)
        conversations = []
        for c in results.get("conversations", []):
            conv = Conversation(
                cid=str(c['cid']),
                title=c.get('title', ''),
                type='group' if c.get('type') == 'group' else 'single',
                platform='dingtalk',
                member_count=c.get('member_count', 0),
                unread_count=c.get('unread_count', 0),
                is_top=c.get('is_top', False),
                last_time=c.get('last_modify', None) / 1000 if c.get('last_modify') else None,
            )
            conversations.append(conv)
        return conversations

    def get_messages(self, cid, limit=50, offset=0):
        """获取消息"""
        conn = self.get_connection()
        if not conn:
            return []

        from dt_parser import get_messages
        results = get_messages(conn, cid, limit=limit, offset=offset)
        messages = []
        for m in results.get("messages", []):
            msg = Message(
                mid=str(m.get('id', '')),
                cid=cid,
                platform='dingtalk',
                sender_name=m.get('sender_name', ''),
                sender_id=str(m.get('sender_id', '')),
                content=m.get('text', ''),
                msg_type=m.get('content_type', 1),
                timestamp=m.get('created_at', None) / 1000 if m.get('created_at') else None,
            )
            if m.get('image_info', {}).get('images'):
                msg.attachments = m['image_info']['images']
            messages.append(msg)
        return messages

    def search_messages(self, keyword, limit=50, offset=0):
        conn = self.get_connection()
        if not conn:
            return []

        from dt_parser import search_messages
        results = search_messages(conn, keyword, limit=limit, offset=offset)
        messages = []
        for m in results:
            msg = Message(
                mid=str(m.get('id', '')),
                cid=str(m.get('cid', '')),
                platform='dingtalk',
                sender_name=m.get('sender_name', ''),
                sender_id=str(m.get('sender_id', '')),
                content=m.get('text', ''),
                msg_type=m.get('content_type', 1),
                timestamp=m.get('created_at', None) / 1000 if m.get('created_at') else None,
            )
            messages.append(msg)
        return messages

    def get_stats(self):
        conn = self.get_connection()
        if not conn:
            return {"error": "not connected"}

        from dt_parser import get_conversation_stats, get_latest_message_time
        stats = get_conversation_stats(conn) if hasattr(get_conversation_stats, '__call__') else {}
        return stats


def get_platform():
    return DingTalkPlatform()
