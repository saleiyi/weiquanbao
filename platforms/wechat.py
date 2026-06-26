#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
维权宝 - 微信平台模块

支持两种版本：
  - WeChat 4.0 (Weixin.exe): SQLCipher 4, 数据在 xwechat_files/wxid/db_storage
  - 旧版 WeChat (WeChatAppEx): SQLCipher 3, 数据在 Documents/WeChat Files/wxid/Msg
"""
import os, sys, re, time, json, logging, glob, hashlib, hmac as hmac_mod, struct
from datetime import datetime
from platforms.base import PlatformBase, Conversation, Message

logger = logging.getLogger(__name__)

PAGE_SZ = 4096
KEY_SZ = 32
SALT_SZ = 16
RESERVE_SZ = 80  # IV(16) + HMAC(64)
SQLITE_HDR = b'SQLite format 3\x00'

# 尝试导入密钥提取器
try:
    from tools.wechat_key_extract import extract_keys_from_process
    HAS_KEY_EXTRACTOR = True
except ImportError:
    HAS_KEY_EXTRACTOR = False

# 尝试导入 pymem (后备)
try:
    import pymem
    HAS_PYMEM = True
except ImportError:
    HAS_PYMEM = False


class WeChatPlatform(PlatformBase):

    @property
    def name(self):
        return "wechat"

    @property
    def display_name(self):
        return "微信"

    def __init__(self):
        self._ready = False
        self._version = None  # 'new' (4.0) or 'old'
        self._keys = {}  # db_rel_path -> {"key": hex, "salt": hex}
        self._db_dir = None  # 数据库目录
        self._decrypted_dir = None
        self._wxid = None
        self._convs_cache = []
        self._msgs_cache = {}

    # ─── 检测可用性 ──────────────────────────────────────────────────

    def is_available(self):
        """检测微信是否安装并有本地数据"""
        # WeChat 4.0 路径
        new_dir = self._find_wechat4_data_dir()
        if new_dir:
            return True
        # 旧版路径
        old_dir = self._find_old_wechat_data_dir()
        if old_dir:
            return True
        return False

    def _find_wechat4_data_dir(self):
        """查找 WeChat 4.0 数据目录 (xwechat_files/wxid/db_storage)"""
        appdata = os.environ.get("APPDATA", "")
        config_dir = os.path.join(appdata, "Tencent", "xwechat", "config")
        if not os.path.isdir(config_dir):
            return None

        # 从 INI 文件读取数据根目录
        for ini_file in glob.glob(os.path.join(config_dir, "*.ini")):
            try:
                content = None
                for enc in ("utf-8", "gbk"):
                    try:
                        with open(ini_file, "r", encoding=enc) as f:
                            content = f.read(1024).strip()
                        break
                    except UnicodeDecodeError:
                        continue
                if not content or any(c in content for c in "\n\r\x00"):
                    continue
                if os.path.isdir(content):
                    # 搜索 xwechat_files/*/db_storage
                    pattern = os.path.join(content, "xwechat_files", "*", "db_storage")
                    matches = glob.glob(pattern)
                    if matches:
                        # 选择最新的
                        matches.sort(key=lambda p: os.path.getmtime(p), reverse=True)
                        return matches[0]
            except OSError:
                continue
        return None

    def _find_old_wechat_data_dir(self):
        """查找旧版微信数据目录 (Documents/WeChat Files/wxid/Msg)"""
        wechat_base = os.path.expanduser("~/Documents/WeChat Files")
        if not os.path.isdir(wechat_base):
            return None
        for f in os.listdir(wechat_base):
            full = os.path.join(wechat_base, f)
            if not os.path.isdir(full):
                continue
            msg_dir = os.path.join(full, "Msg")
            if os.path.isdir(msg_dir):
                if os.path.exists(os.path.join(msg_dir, "MSG.db")) or \
                   os.path.exists(os.path.join(msg_dir, "ChatMsg.db")):
                    return full
        return None

    def discover(self):
        """获取密钥 + 解密数据库"""
        import config as cfg
        # 使用持久化目录（兼容 PyInstaller 打包）
        self._decrypted_dir = os.path.join(cfg.DATA_DIR, "wechat_decrypted")
        os.makedirs(self._decrypted_dir, exist_ok=True)

        # 优先尝试 WeChat 4.0
        new_dir = self._find_wechat4_data_dir()
        if new_dir:
            logger.info(f"微信 4.0 数据目录: {new_dir}")
            self._db_dir = new_dir
            self._version = "new"

            if self._extract_and_decrypt_new():
                self._ready = True
                return True

        # 降级到旧版
        old_dir = self._find_old_wechat_data_dir()
        if old_dir:
            logger.info(f"旧版微信数据目录: {old_dir}")
            self._db_dir = old_dir
            self._version = "old"

            if self._extract_and_decrypt_old():
                self._ready = True
                return True

        logger.error("微信: 未找到数据目录")
        return False

    def _extract_and_decrypt_new(self):
        """WeChat 4.0: 提取密钥并解密"""
        if not HAS_KEY_EXTRACTOR:
            logger.error("微信: 密钥提取器不可用")
            return False

        logger.info("微信: 提取密钥...")
        keys = extract_keys_from_process(db_dir=self._db_dir)
        if not keys:
            logger.error("微信: 未找到匹配的密钥，请确保微信正在运行")
            return False

        # 转换 key 路径为相对路径
        normalized_keys = {}
        for db_path, info in keys.items():
            # db_path 可能是完整路径或相对路径
            if os.path.isabs(db_path):
                db_rel = os.path.relpath(db_path, self._db_dir).replace("\\", "/")
            else:
                db_rel = db_path.replace("\\", "/")
            normalized_keys[db_rel] = info

        self._keys = normalized_keys
        logger.info(f"微信: 找到 {len(normalized_keys)} 个数据库密钥")

        # 解密所有有密钥的数据库
        for db_rel, info in normalized_keys.items():
            db_path = os.path.join(self._db_dir, db_rel.replace("/", os.sep))
            if os.path.exists(db_path):
                self._decrypt_single_db_new(db_path, info["key"])
            else:
                logger.warning(f"微信: 数据库不存在: {db_path}")

        return True

    def _decrypt_single_db_new(self, db_path, key_hex):
        """解密单个 WeChat 4.0 数据库 (SQLCipher 4)"""
        import sqlite3

        db_rel = os.path.relpath(db_path, self._db_dir).replace("\\", "/")
        out_path = os.path.join(self._decrypted_dir, db_rel.replace("/", "_"))
        os.makedirs(os.path.dirname(out_path), exist_ok=True)

        # 如果已解密且更新时间相同，跳过
        if os.path.exists(out_path):
            src_mtime = os.path.getmtime(db_path)
            out_mtime = os.path.getmtime(out_path)
            if src_mtime <= out_mtime:
                self._keys[db_rel]["decrypted_path"] = out_path
                return True

        try:
            enc_key = bytes.fromhex(key_hex)

            with open(db_path, 'rb') as f:
                page1 = f.read(PAGE_SZ)

            if len(page1) < PAGE_SZ:
                return False

            # 验证密钥
            salt = page1[:SALT_SZ]
            mac_salt = bytes(b ^ 0x3A for b in salt)
            mac_key = hashlib.pbkdf2_hmac("sha512", enc_key, mac_salt, 2, dklen=KEY_SZ)
            hmac_data = page1[SALT_SZ: PAGE_SZ - RESERVE_SZ + 16]
            stored_hmac = page1[PAGE_SZ - 64: PAGE_SZ]
            hm = hmac_mod.new(mac_key, hmac_data, hashlib.sha512)
            hm.update(struct.pack("<I", 1))
            if hm.digest() != stored_hmac:
                return False

            # 解密
            from Crypto.Cipher import AES
            file_size = os.path.getsize(db_path)
            total_pages = file_size // PAGE_SZ

            with open(db_path, 'rb') as fin, open(out_path, 'wb') as fout:
                for pgno in range(1, total_pages + 1):
                    page = fin.read(PAGE_SZ)
                    if len(page) < PAGE_SZ:
                        page = page + b'\x00' * (PAGE_SZ - len(page))

                    iv = page[PAGE_SZ - RESERVE_SZ: PAGE_SZ - RESERVE_SZ + 16]
                    if pgno == 1:
                        encrypted = page[SALT_SZ: PAGE_SZ - RESERVE_SZ]
                    else:
                        encrypted = page[:PAGE_SZ - RESERVE_SZ]

                    cipher = AES.new(enc_key, AES.MODE_CBC, iv)
                    decrypted = cipher.decrypt(encrypted)

                    if pgno == 1:
                        out_page = SQLITE_HDR + decrypted + b'\x00' * RESERVE_SZ
                    else:
                        out_page = decrypted + b'\x00' * RESERVE_SZ

                    fout.write(out_page)

            # 验证解密结果
            try:
                conn = sqlite3.connect(out_path)
                conn.execute("SELECT 1")
                conn.close()
                self._keys[db_rel]["decrypted_path"] = out_path
                logger.info(f"微信: 解密成功 {db_rel}")
                return True
            except sqlite3.DatabaseError:
                os.remove(out_path)
                return False

        except Exception as e:
            logger.warning(f"微信: 解密 {db_rel} 失败: {e}")
            if os.path.exists(out_path):
                os.remove(out_path)
            return False

    def _extract_and_decrypt_old(self):
        """旧版微信: 提取密钥并解密"""
        # 旧版使用 pymem
        if not HAS_PYMEM:
            logger.error("微信: pymem 未安装")
            return False

        # 获取密钥
        pm = None
        for proc_name in ["WeChatAppEx", "WeChat.exe"]:
            try:
                pm = pymem.Pymem(proc_name)
                break
            except Exception:
                continue

        if not pm:
            logger.error("微信: 未找到微信进程")
            return False

        key_pattern = re.compile(rb"x'([0-9a-fA-F]{96})'")
        for module in pm.list_modules():
            try:
                size = min(module.SizeOfImage, 200 * 1024 * 1024)
                mem = pm.read_bytes(module.lpBaseOfDll, size)
            except Exception:
                continue

            for match in key_pattern.finditer(mem):
                hex_str = match.group(1).decode('ascii')
                if len(hex_str) == 96:
                    self._keys["_old_key"] = {"key": hex_str[:64], "salt": hex_str[64:]}
                    logger.info("微信: 旧版密钥获取成功")
                    return True

        logger.error("微信: 未找到密钥")
        return False

    def _get_decrypted_path(self, db_name):
        """获取解密后的数据库路径"""
        if self._version == "new":
            # WeChat 4.0: 在 keys 中查找
            for db_rel, info in self._keys.items():
                if db_name in db_rel and "decrypted_path" in info:
                    return info["decrypted_path"]
            # 尝试直接解密
            for db_rel, info in self._keys.items():
                if db_name in db_rel:
                    db_path = os.path.join(self._db_dir, db_rel.replace("/", os.sep))
                    if os.path.exists(db_path):
                        if self._decrypt_single_db_new(db_path, info["key"]):
                            return info.get("decrypted_path")
        else:
            # 旧版
            return self._keys.get("_old_key", {}).get("decrypted_path")
        return None

    def _query_decrypted(self, db_path, sql, params=()):
        """查询解密后的数据库"""
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.text_factory = str
        try:
            cursor = conn.execute(sql, params)
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
        except sqlite3.DatabaseError as e:
            logger.error(f"微信 SQL 查询失败: {e}")
            return []
        finally:
            conn.close()

    # ─── 获取会话列表 ──────────────────────────────────────────────

    def get_conversations(self, keyword=None):
        """获取微信会话列表"""
        if self._convs_cache:
            if keyword:
                return [c for c in self._convs_cache if keyword.lower() in c.title.lower()]
            return self._convs_cache

        if not self._ready and not self.discover():
            return []

        convs = []
        if self._version == "new":
            convs = self._get_convs_new(keyword)
        else:
            convs = self._get_convs_old(keyword)

        self._convs_cache = convs
        return convs

    def _get_convs_new(self, keyword=None):
        """WeChat 4.0 会话列表"""
        convs = []

        # 联系人 (WeChat 4.0 表结构: username, nick_name, remark, local_type)
        contact_db = self._get_decrypted_path("contact.db")
        if contact_db:
            try:
                rows = self._query_decrypted(contact_db, """
                    SELECT username, nick_name, remark, local_type FROM contact
                """)
                session_db = self._get_decrypted_path("session.db")
                session_times = {}
                if session_db:
                    try:
                        sessions = self._query_decrypted(session_db, """
                            SELECT strUsrName, iLastMsgTime FROM Session
                        """)
                        session_times = {s['strUsrName']: s['iLastMsgTime'] for s in sessions}
                    except Exception:
                        # WeChat 4.0 session 表可能不同
                        try:
                            sessions = self._query_decrypted(session_db, """
                                SELECT username, last_message_time FROM session
                            """)
                            session_times = {s['username']: s['last_message_time'] for s in sessions}
                        except Exception:
                            pass

                for c in rows:
                    username = c.get('username', '')
                    nick = c.get('remark', '') or c.get('nick_name', '')
                    if not nick or not username:
                        continue
                    if keyword and keyword.lower() not in nick.lower():
                        continue
                    conv_type = 'group' if username.endswith('@chatroom') else 'single'
                    convs.append(Conversation(
                        cid=username, title=nick, type=conv_type,
                        platform="wechat", last_time=session_times.get(username),
                    ))
            except Exception as e:
                logger.warning(f"微信 4.0 Contact 查询失败: {e}")

        # 如果 Contact 查询失败，尝试 Session
        if not convs:
            session_db = self._get_decrypted_path("session.db")
            if session_db:
                try:
                    rows = self._query_decrypted(session_db, """
                        SELECT strUsrName, iLastMsgTime FROM Session
                    """)
                    for r in rows:
                        cid = r.get('strUsrName', '')
                        if not cid:
                            continue
                        if keyword and keyword.lower() not in cid.lower():
                            continue
                        convs.append(Conversation(
                            cid=cid, title=cid, type='single',
                            platform="wechat", last_time=r.get('iLastMsgTime'),
                        ))
                except Exception as e:
                    logger.warning(f"微信 4.0 Session 查询失败: {e}")

        return convs

    def _get_convs_old(self, keyword=None):
        """旧版微信会话列表"""
        # 旧版逻辑类似，省略
        return []

    # ─── 获取消息 ──────────────────────────────────────────────────

    def get_messages(self, cid, limit=50, offset=0):
        """获取消息"""
        if cid in self._msgs_cache:
            msgs = self._msgs_cache[cid]
            return msgs[offset:offset + limit]

        if not self._ready and not self.discover():
            return []

        msgs = self._get_msgs_new(cid, limit, offset)
        return msgs

    def _get_msgs_new(self, cid, limit=50, offset=0):
        """WeChat 4.0: 获取某个会话的消息"""
        import hashlib
        # Msg 表名 = Msg_ + md5(cid)
        md5 = hashlib.md5(cid.encode()).hexdigest()
        table_name = f"Msg_{md5}"

        # 在所有 message 数据库中查找这个表
        messages = []
        for db_rel, info in self._keys.items():
            if "decrypted_path" not in info:
                continue
            if "message" not in db_rel:
                continue

            db_path = info["decrypted_path"]
            if not os.path.exists(db_path):
                continue

            try:
                import sqlite3
                conn = sqlite3.connect(db_path)
                # 检查表是否存在
                exists = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                    (table_name,)
                ).fetchone()
                if not exists:
                    conn.close()
                    continue

                # 获取联系人映射 (sender_id -> nick_name)
                contact_map = self._get_contact_map()

                # 查询消息
                rows = conn.execute(f"""
                    SELECT local_id, real_sender_id, create_time, message_content,
                           WCDB_CT_message_content, local_type
                    FROM "{table_name}"
                    ORDER BY create_time ASC
                    LIMIT ? OFFSET ?
                """, (limit, offset)).fetchall()

                for r in rows:
                    msg = self._parse_message_row(r, cid, contact_map)
                    if msg:
                        messages.append(msg)

                conn.close()
                if messages:
                    break  # 找到了就停止
            except Exception as e:
                logger.warning(f"微信: 查询 {db_rel} 失败: {e}")

        return messages

    def _get_contact_map(self):
        """获取联系人 ID -> 昵称映射"""
        if hasattr(self, '_contact_map') and self._contact_map:
            return self._contact_map

        self._contact_map = {}
        contact_db = self._get_decrypted_path("contact.db")
        if contact_db:
            try:
                import sqlite3
                conn = sqlite3.connect(contact_db)
                rows = conn.execute("SELECT id, username, nick_name, remark FROM contact").fetchall()
                for r in rows:
                    self._contact_map[r[0]] = {
                        "username": r[1],
                        "nick_name": r[2] or "",
                        "remark": r[3] or "",
                    }
                conn.close()
            except Exception as e:
                logger.warning(f"微信: 读取联系人失败: {e}")
        return self._contact_map

    def _parse_message_row(self, row, cid, contact_map):
        """解析消息行"""
        try:
            local_id = row[0]
            sender_id = row[1]
            create_time = row[2]
            content = row[3]
            content_type = row[4]
            local_type = row[5]

            # 解析发送者
            sender_info = contact_map.get(sender_id, {})
            sender_name = sender_info.get("remark") or sender_info.get("nick_name") or str(sender_id)
            is_self = sender_info.get("username") == self._wxid

            # 解析内容
            text = self._decode_message_content(content, content_type, local_type)

            return Message(
                mid=str(local_id),
                cid=cid,
                platform="wechat",
                sender_name="我" if is_self else sender_name,
                sender_id="me" if is_self else str(sender_id),
                content=text,
                msg_type=local_type,
                timestamp=create_time,
            )
        except Exception as e:
            logger.warning(f"微信: 解析消息失败: {e}")
            return None

    def _decode_message_content(self, content, content_type, local_type):
        """解码消息内容"""
        if content is None:
            return ""

        # 纯文本
        if content_type == 0:
            if isinstance(content, bytes):
                try:
                    return content.decode('utf-8', errors='replace')
                except Exception:
                    return f"<binary {len(content)} bytes>"
            return str(content)

        # zstd 压缩
        if content_type == 4 and isinstance(content, bytes):
            try:
                import zstandard
                dctx = zstandard.ZstdDecompressor()
                decompressed = dctx.decompress(content)
                # 解压后是 protobuf，尝试提取文本
                return self._extract_text_from_protobuf(decompressed, local_type)
            except Exception as e:
                return f"<compressed message, decode error: {e}>"

        # 其他类型
        if isinstance(content, bytes):
            try:
                return content.decode('utf-8', errors='replace')
            except Exception:
                return f"<binary {len(content)} bytes>"
        return str(content)

    def _extract_text_from_protobuf(self, data, local_type):
        """从 protobuf 数据中提取文本内容"""
        # 微信消息的 protobuf 格式：
        # field 1 (string): 消息文本内容
        # 其他字段: 图片、文件等元数据

        try:
            # 简单的 protobuf 解析：查找 field 1 的 string 值
            pos = 0
            while pos < len(data):
                if pos >= len(data):
                    break
                # 读取 tag
                tag_byte = data[pos]
                field_number = tag_byte >> 3
                wire_type = tag_byte & 0x07
                pos += 1

                if wire_type == 2:  # length-delimited (string/bytes)
                    # 读取长度
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

                    # field 1 通常是消息文本
                    if field_number == 1:
                        try:
                            text = value.decode('utf-8')
                            if text and len(text) > 0:
                                return text
                        except UnicodeDecodeError:
                            pass
                elif wire_type == 0:  # varint
                    while pos < len(data) and data[pos] & 0x80:
                        pos += 1
                    pos += 1
                elif wire_type == 5:  # 32-bit
                    pos += 4
                elif wire_type == 1:  # 64-bit
                    pos += 8
                else:
                    break

            # 如果没找到 field 1，尝试直接解码为 UTF-8
            try:
                text = data.decode('utf-8', errors='ignore')
                # 过滤掉控制字符
                text = ''.join(c for c in text if c.isprintable() or c in '\n\r\t')
                if text.strip():
                    return text.strip()
            except Exception:
                pass

            return f"<message {len(data)} bytes>"
        except Exception as e:
            return f"<parse error: {e}>"

    def search_messages(self, keyword, limit=50, offset=0):
        """搜索消息"""
        if not self._ready and not self.discover():
            return []

        results = []
        contact_map = self._get_contact_map()

        # 构建 hash -> username 映射
        hash_to_name = {}
        for db_rel, info in self._keys.items():
            if "decrypted_path" not in info or "message" not in db_rel:
                continue
            db_path = info["decrypted_path"]
            if not os.path.exists(db_path):
                continue
            try:
                import sqlite3, hashlib
                conn = sqlite3.connect(db_path)
                names = conn.execute("SELECT user_name FROM Name2Id").fetchall()
                for n in names:
                    h = hashlib.md5(n[0].encode()).hexdigest()
                    hash_to_name[h] = n[0]
                conn.close()
            except Exception:
                pass

        # 在所有 message 数据库中搜索
        for db_rel, info in self._keys.items():
            if "decrypted_path" not in info:
                continue
            if "message" not in db_rel:
                continue

            db_path = info["decrypted_path"]
            if not os.path.exists(db_path):
                continue

            try:
                import sqlite3
                conn = sqlite3.connect(db_path)
                tables = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'Msg_%'"
                ).fetchall()

                for t in tables:
                    table_name = t[0]
                    try:
                        rows = conn.execute(f"""
                            SELECT local_id, real_sender_id, create_time, message_content,
                                   WCDB_CT_message_content, local_type
                            FROM "{table_name}"
                            WHERE WCDB_CT_message_content = 0
                              AND message_content LIKE ?
                            ORDER BY create_time DESC
                            LIMIT ?
                        """, (f"%{keyword}%", limit)).fetchall()

                        for r in rows:
                            # 从表名反推真实 cid
                            hash_val = table_name[4:]
                            cid = hash_to_name.get(hash_val, hash_val)

                            msg = self._parse_message_row(r, cid, contact_map)
                            if msg:
                                results.append(msg)
                                if len(results) >= limit + offset:
                                    conn.close()
                                    return results[offset:offset + limit]
                    except Exception:
                        continue

                conn.close()
            except Exception as e:
                logger.warning(f"微信: 搜索 {db_rel} 失败: {e}")

        return results[offset:offset + limit]

    def get_stats(self):
        """获取统计"""
        return {
            "version": self._version,
            "ready": self._ready,
            "db_dir": self._db_dir,
            "keys_found": len(self._keys),
        }


def get_platform():
    return WeChatPlatform()
