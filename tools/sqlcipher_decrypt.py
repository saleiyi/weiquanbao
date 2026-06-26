#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
维权宝 - SQLCipher 纯 Python 解密引擎 v3
微信 SQLCipher 参数：
  page_size=4096, kdf_iter=64000, cipher=AES-256-CBC
  HMAC 不启用
"""
import os, hashlib, struct, logging
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

logger = logging.getLogger(__name__)

PAGE_SIZE = 4096
KDF_ITER = 64000
KEY_LEN = 32
SALT_LEN = 16


def _make_iv(page_no):
    """页码 → 16字节 IV (big-endian)"""
    return struct.pack(">Q", page_no) + b'\x00' * 8


def derive_keys(raw_key, salt):
    """PBKDF2-HMAC-SHA1 派生 AES-256 密钥"""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA1(),
        length=KEY_LEN,
        salt=salt,
        iterations=KDF_ITER,
    )
    return kdf.derive(raw_key)


def decrypt_db(encrypted_path, raw_key, output_path):
    """
    解密 SQLCipher 数据库（无 HMAC 模式）

    微信 SQLCipher 页面布局（HMAC 禁用）：
      第 0 页: [salt=16B] [AES-256-CBC 加密数据=4080B]
      第 N 页: [AES-256-CBC 加密数据=4096B]
      IV = 页码（16字节 big-endian）
    """
    with open(encrypted_path, 'rb') as f:
        data = f.read()

    # 第 0 页前 16 字节 = salt
    salt = data[:SALT_LEN]
    key = derive_keys(raw_key, salt)

    page_count = (len(data) + PAGE_SIZE - 1) // PAGE_SIZE
    sqlite_header = b'SQLite format 3\0'

    with open(output_path, 'wb') as out:
        for i in range(page_count):
            offset = i * PAGE_SIZE
            page_data = data[offset:offset + PAGE_SIZE]

            # 补齐到整页
            if len(page_data) < PAGE_SIZE:
                page_data = page_data.ljust(PAGE_SIZE, b'\x00')

            if i == 0:
                # 跳过 salt
                ciphertext = page_data[SALT_LEN:]
            else:
                ciphertext = page_data

            # IV = 页码（16字节）
            iv = _make_iv(i)

            # AES-256-CBC 解密
            try:
                cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
                decryptor = cipher.decryptor()
                decrypted = decryptor.update(ciphertext) + decryptor.finalize()
            except Exception as e:
                logger.warning(f"第 {i} 页解密失败: {e}")
                decrypted = b'\x00' * (PAGE_SIZE - (SALT_LEN if i == 0 else 0))

            # 第 0 页替换文件头
            if i == 0:
                out.write(sqlite_header + decrypted[16:])  # 保留后 16 字节（内含有用信息）
            else:
                out.write(decrypted)

    logger.info(f"解密完成: {output_path}")
    return output_path


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) >= 3:
        key = bytes.fromhex(sys.argv[2]) if len(sys.argv[2]) == 64 else sys.argv[2].encode()
        out = sys.argv[3] if len(sys.argv) > 3 else "decrypted.db"
        decrypt_db(sys.argv[1], key, out)
    else:
        print(f"用法: {sys.argv[0]} <加密.db> <32字节hex密钥> [输出路径]")
