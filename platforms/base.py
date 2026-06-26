#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
维权宝 - 平台基类
每个平台（钉钉/微信/QQ/飞书）继承此基类
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import Optional
import json
from datetime import datetime


@dataclass
class Conversation:
    """统一会话格式"""
    cid: str                       # 会话ID
    title: str                     # 会话名称
    type: str = "single"           # single / group
    platform: str = ""             # dingtalk / wechat / qq / feishu
    member_count: int = 0
    unread_count: int = 0
    is_top: bool = False
    last_message: str = ""
    last_time: Optional[float] = None
    avatar: str = ""


@dataclass
class Message:
    """统一消息格式"""
    mid: str                       # 消息ID
    cid: str                       # 会话ID
    platform: str = ""
    sender_name: str = ""
    sender_id: str = ""
    content: str = ""              # 文本内容
    msg_type: int = 1              # 1=文本 2=图片 3=文件 4=系统
    timestamp: Optional[float] = None
    attachments: list = field(default_factory=list)


class PlatformBase(ABC):
    """各平台需实现的接口"""

    @property
    @abstractmethod
    def name(self) -> str:
        """平台名称: dingtalk / wechat / qq / feishu"""
        pass

    @property
    @abstractmethod
    def display_name(self) -> str:
        """显示名称: 钉钉 / 微信 / QQ / 飞书"""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """检测本机是否安装了此平台并存在数据"""
        pass

    @abstractmethod
    def discover(self) -> bool:
        """发现并解密本地数据库，返回是否成功"""
        pass

    @abstractmethod
    def get_conversations(self, keyword=None) -> list:
        """获取会话列表"""
        pass

    @abstractmethod
    def get_messages(self, cid, limit=50, offset=0) -> list:
        """获取某个会话的消息"""
        pass

    def search_messages(self, keyword, limit=50, offset=0) -> list:
        """搜索消息（默认走 get_messages 过滤，可重写）"""
        return []

    @abstractmethod
    def get_stats(self) -> dict:
        """获取统计数据"""
        pass

    def export(self, cids, output_dir, time_range="all"):
        """导出选中会话"""
        pass
