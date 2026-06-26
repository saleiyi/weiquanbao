#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
维权宝 - 微信聊天记录导出器
支持 WeChat 4.0 (SQLCipher 4) 数据库
"""
import json
import os
import hashlib
import sqlite3
import logging
from datetime import datetime

import config

logger = logging.getLogger(__name__)


def _create_export_dir(base_dir, prefix):
    """Create a timestamped export directory."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    export_dir = os.path.join(base_dir, f"wechat_{prefix}_{timestamp}")
    os.makedirs(export_dir, exist_ok=True)
    return export_dir


def _write_export_json(export_data, export_dir):
    """Write the export JSON file."""
    json_path = os.path.join(export_dir, "export.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(export_data, f, ensure_ascii=False, indent=2)
    return json_path


def _format_timestamp(ts):
    """Format a Unix timestamp to ISO string."""
    if not ts:
        return ""
    try:
        dt = datetime.fromtimestamp(ts)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, OSError):
        return str(ts)


def _get_contact_map(decrypted_dir):
    """Load contact ID -> name mapping from decrypted contact.db."""
    contact_map = {}
    contact_db = os.path.join(decrypted_dir, "contact_contact.db")
    if not os.path.exists(contact_db):
        return contact_map

    try:
        conn = sqlite3.connect(contact_db)
        rows = conn.execute("SELECT id, username, nick_name, remark FROM contact").fetchall()
        for r in rows:
            contact_map[r[0]] = {
                "username": r[1],
                "nick_name": r[2] or "",
                "remark": r[3] or "",
            }
        conn.close()
    except Exception as e:
        logger.warning(f"读取联系人失败: {e}")

    return contact_map


def _get_session_map(decrypted_dir):
    """Load session mapping (conversation list)."""
    sessions = {}
    # 尝试多个可能的 session 数据库
    for db_name in ["session_session.db", "session.db"]:
        session_db = os.path.join(decrypted_dir, db_name)
        if not os.path.exists(session_db):
            continue
        try:
            conn = sqlite3.connect(session_db)
            # WeChat 4.0 session 表结构
            try:
                rows = conn.execute("SELECT strUsrName, iLastMsgTime FROM Session").fetchall()
                for r in rows:
                    sessions[r[0]] = {"last_time": r[1]}
            except Exception:
                pass
            conn.close()
            if sessions:
                break
        except Exception:
            continue

    return sessions


def _find_msg_table(conn, cid):
    """Find the Msg table for a conversation."""
    md5 = hashlib.md5(cid.encode()).hexdigest()
    table_name = f"Msg_{md5}"
    exists = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,)
    ).fetchone()
    return table_name if exists else None


def _decode_message_content(content, content_type):
    """Decode message content (plain text or zstd compressed)."""
    if content is None:
        return ""

    if content_type == 0:
        if isinstance(content, bytes):
            try:
                return content.decode('utf-8', errors='replace')
            except Exception:
                return f"<binary {len(content)} bytes>"
        return str(content)

    if content_type == 4 and isinstance(content, bytes):
        try:
            import zstandard
            dctx = zstandard.ZstdDecompressor()
            decompressed = dctx.decompress(content)
            return _extract_text_from_protobuf(decompressed)
        except Exception:
            return f"<compressed {len(content)} bytes>"

    if isinstance(content, bytes):
        try:
            return content.decode('utf-8', errors='replace')
        except Exception:
            return f"<binary {len(content)} bytes>"
    return str(content)


def _extract_text_from_protobuf(data):
    """Extract text from protobuf data."""
    try:
        pos = 0
        while pos < len(data):
            if pos >= len(data):
                break
            tag_byte = data[pos]
            field_number = tag_byte >> 3
            wire_type = tag_byte & 0x07
            pos += 1

            if wire_type == 2:
                length = 0
                shift = 0
                while pos < len(data):
                    b = data[pos]
                    pos += 1
                    length |= (b & 0x7F) << shift
                    shift += 7
                    if not (b & 0x80):
                        break
                if pos + length > len(data):
                    break
                value = data[pos:pos + length]
                pos += length
                if field_number == 1:
                    try:
                        text = value.decode('utf-8')
                        if text and len(text) > 0:
                            return text
                    except UnicodeDecodeError:
                        pass
            elif wire_type == 0:
                while pos < len(data) and data[pos] & 0x80:
                    pos += 1
                pos += 1
            elif wire_type == 5:
                pos += 4
            elif wire_type == 1:
                pos += 8
            else:
                break

        try:
            text = data.decode('utf-8', errors='ignore')
            text = ''.join(c for c in text if c.isprintable() or c in '\n\r\t')
            if text.strip():
                return text.strip()
        except Exception:
            pass
        return f"<message {len(data)} bytes>"
    except Exception:
        return f"<parse error>"


def _parse_message(row, cid, contact_map, wxid):
    """Parse a message row into a dict."""
    local_id = row[0]
    sender_id = row[1]
    create_time = row[2]
    content = row[3]
    content_type = row[4]
    local_type = row[5]

    sender_info = contact_map.get(sender_id, {})
    sender_name = sender_info.get("remark") or sender_info.get("nick_name") or str(sender_id)
    is_self = sender_info.get("username") == wxid

    text = _decode_message_content(content, content_type)

    # 消息类型映射
    type_names = {
        1: "文本", 3: "图片", 34: "语音", 42: "视频",
        43: "文件", 47: "表情", 48: "位置", 50: "通话",
        10000: "系统",
    }
    type_name = type_names.get(local_type, f"类型{local_type}")

    return {
        "message_id": local_id,
        "sender_id": sender_id,
        "sender_name": "我" if is_self else sender_name,
        "content_type": local_type,
        "content_type_name": type_name,
        "text": text,
        "created_at": create_time,
        "created_at_str": _format_timestamp(create_time),
    }


def export_by_cids(cids, base_dir=None, wxid=None, decrypted_dir=None):
    """Export selected WeChat conversations.

    Args:
        cids: List of conversation IDs (wxid or chatroom)
        base_dir: Output directory
        wxid: Current user's wxid
        decrypted_dir: Directory containing decrypted databases
    """
    if base_dir is None:
        base_dir = config.EXPORT_DIR
    if decrypted_dir is None:
        decrypted_dir = os.path.join(os.path.dirname(__file__), "data", "wechat_decrypted")

    os.makedirs(base_dir, exist_ok=True)
    export_dir = _create_export_dir(base_dir, "export")

    logger.info(f"开始导出 {len(cids)} 个微信会话 -> {export_dir}")

    # 加载联系人映射
    contact_map = _get_contact_map(decrypted_dir)
    logger.info(f"加载 {len(contact_map)} 个联系人")

    export_data = {
        "export_time": datetime.now().isoformat(),
        "export_type": "selected",
        "platform": "wechat",
        "total_conversations": len(cids),
        "conversations": [],
    }

    # 找到所有消息数据库
    msg_dbs = []
    for f in sorted(os.listdir(decrypted_dir)):
        if "message" in f and f.endswith(".db"):
            msg_dbs.append(os.path.join(decrypted_dir, f))

    total_messages = 0

    for cid in cids:
        logger.info(f"导出会话: {cid}")

        # 从 contact_map 找到会话名称
        conv_title = cid
        conv_type = "group" if cid.endswith("@chatroom") else "single"
        for info in contact_map.values():
            if info["username"] == cid:
                conv_title = info["remark"] or info["nick_name"] or cid
                break

        conv_data = {
            "conversation_id": cid,
            "title": conv_title,
            "type": conv_type,
            "messages": [],
        }

        # 在所有消息数据库中查找
        for db_path in msg_dbs:
            try:
                conn = sqlite3.connect(db_path)
                table_name = _find_msg_table(conn, cid)
                if not table_name:
                    conn.close()
                    continue

                # 获取所有消息
                rows = conn.execute(f"""
                    SELECT local_id, real_sender_id, create_time, message_content,
                           WCDB_CT_message_content, local_type
                    FROM "{table_name}"
                    ORDER BY create_time ASC
                """).fetchall()

                for r in rows:
                    msg = _parse_message(r, cid, contact_map, wxid)
                    conv_data["messages"].append(msg)

                conn.close()
                if conv_data["messages"]:
                    break
            except Exception as e:
                logger.warning(f"查询 {db_path} 失败: {e}")

        conv_data["message_count"] = len(conv_data["messages"])
        total_messages += conv_data["message_count"]
        export_data["conversations"].append(conv_data)

        logger.info(f"  {cid}: {conv_data['message_count']} 条消息")

    # 写入 JSON
    json_path = _write_export_json(export_data, export_dir)
    logger.info(f"导出完成: {export_dir} ({total_messages} 条消息)")
    return export_dir


def export_all(base_dir=None, wxid=None, decrypted_dir=None, limit=100):
    """Export all conversations (limited by default).

    Args:
        base_dir: Output directory
        wxid: Current user's wxid
        decrypted_dir: Directory containing decrypted databases
        limit: Max conversations to export
    """
    if base_dir is None:
        base_dir = config.EXPORT_DIR
    if decrypted_dir is None:
        decrypted_dir = os.path.join(os.path.dirname(__file__), "data", "wechat_decrypted")

    # 获取会话列表
    sessions = _get_session_map(decrypted_dir)
    cids = list(sessions.keys())[:limit]

    if not cids:
        # 如果没有 session，从 Name2Id 获取
        for f in os.listdir(decrypted_dir):
            if "message" in f and f.endswith(".db"):
                db_path = os.path.join(decrypted_dir, f)
                try:
                    conn = sqlite3.connect(db_path)
                    names = conn.execute("SELECT user_name FROM Name2Id WHERE is_session=1").fetchall()
                    for n in names:
                        if n[0] not in cids:
                            cids.append(n[0])
                    conn.close()
                except Exception:
                    pass
                if len(cids) >= limit:
                    break

    cids = cids[:limit]
    logger.info(f"找到 {len(cids)} 个会话")

    return export_by_cids(cids, base_dir=base_dir, wxid=wxid, decrypted_dir=decrypted_dir)


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    path = export_all(limit=10)
    print(f"Export saved to: {path}")
