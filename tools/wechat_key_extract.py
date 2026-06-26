#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
微信密钥提取器 - 支持 WeChat 4.0 (Weixin.exe) 和旧版 (WeChatAppEx)

参考: https://github.com/ylytdeng/wechat-decrypt
"""
import ctypes
import ctypes.wintypes as wt
import os, sys, re, struct, hashlib, hmac as hmac_mod, logging

logger = logging.getLogger(__name__)

PAGE_SZ = 4096
KEY_SZ = 32
SALT_SZ = 16
MEM_COMMIT = 0x1000
READABLE = {0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80}

kernel32 = ctypes.windll.kernel32


class MBI(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_uint64),
        ("AllocationBase", ctypes.c_uint64),
        ("AllocationProtect", wt.DWORD),
        ("_pad1", wt.DWORD),
        ("RegionSize", ctypes.c_uint64),
        ("State", wt.DWORD),
        ("Protect", wt.DWORD),
        ("Type", wt.DWORD),
        ("_pad2", wt.DWORD),
    ]


def _get_pids(proc_name):
    """获取指定进程名的所有 PID"""
    import subprocess
    try:
        r = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {proc_name}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=10
        )
        pids = []
        for line in r.stdout.strip().split('\n'):
            if not line.strip():
                continue
            p = line.strip('"').split('","')
            if len(p) >= 5:
                try:
                    pid = int(p[1])
                    mem = int(p[4].replace(',', '').replace(' K', '').strip() or '0')
                    pids.append((pid, mem))
                except ValueError:
                    continue
        pids.sort(key=lambda x: x[1], reverse=True)
        return pids
    except Exception as e:
        logger.warning(f"tasklist 失败: {e}")
        return []


def _read_mem(h, addr, sz):
    """读取进程内存"""
    buf = ctypes.create_string_buffer(sz)
    n = ctypes.c_size_t(0)
    if kernel32.ReadProcessMemory(h, ctypes.c_uint64(addr), buf, sz, ctypes.byref(n)):
        return buf.raw[:n.value]
    return None


def _enum_regions(h):
    """枚举进程的所有可读内存区域"""
    regs = []
    addr = 0
    mbi = MBI()
    while addr < 0x7FFFFFFFFFFF:
        if kernel32.VirtualQueryEx(h, ctypes.c_uint64(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)) == 0:
            break
        if mbi.State == MEM_COMMIT and mbi.Protect in READABLE and 0 < mbi.RegionSize < 500 * 1024 * 1024:
            regs.append((mbi.BaseAddress, mbi.RegionSize))
        nxt = mbi.BaseAddress + mbi.RegionSize
        if nxt <= addr:
            break
        addr = nxt
    return regs


def _verify_key_against_db(enc_key_bytes, db_path):
    """通过 HMAC-SHA512 验证密钥是否正确"""
    try:
        with open(db_path, 'rb') as f:
            page1 = f.read(PAGE_SZ)
        if len(page1) < PAGE_SZ:
            return False

        salt = page1[:SALT_SZ]
        mac_salt = bytes(b ^ 0x3A for b in salt)
        mac_key = hashlib.pbkdf2_hmac("sha512", enc_key_bytes, mac_salt, 2, dklen=KEY_SZ)
        hmac_data = page1[SALT_SZ: PAGE_SZ - 80 + 16]
        stored_hmac = page1[PAGE_SZ - 64: PAGE_SZ]
        hm = hmac_mod.new(mac_key, hmac_data, hashlib.sha512)
        hm.update(struct.pack("<I", 1))
        return hm.digest() == stored_hmac
    except Exception:
        return False


def extract_keys_from_process(proc_name="Weixin.exe", db_dir=None):
    """
    从进程内存提取所有数据库密钥

    Args:
        proc_name: 进程名 (Weixin.exe 或 WeChatAppEx)
        db_dir: 数据库目录，用于验证密钥

    Returns:
        dict: {db_path: {"key": hex_key, "salt": hex_salt}}
    """
    pids = _get_pids(proc_name)
    if not pids:
        logger.warning(f"进程 {proc_name} 未运行")
        return {}

    logger.info(f"找到 {len(pids)} 个 {proc_name} 进程")

    # 收集数据库文件的 salt
    db_files = {}  # salt_hex -> [db_path, ...]
    if db_dir and os.path.isdir(db_dir):
        for root, dirs, files in os.walk(db_dir):
            for name in files:
                if name.endswith('.db') and not name.endswith('-wal') and not name.endswith('-shm'):
                    path = os.path.join(root, name)
                    try:
                        with open(path, 'rb') as f:
                            page1 = f.read(PAGE_SZ)
                        if len(page1) >= PAGE_SZ:
                            salt_hex = page1[:SALT_SZ].hex()
                            db_files.setdefault(salt_hex, []).append(path)
                    except Exception:
                        pass

    logger.info(f"找到 {len(db_files)} 个不同的 salt")

    # 搜索模式: x'<64-192位hex>'
    hex_re = re.compile(rb"x'([0-9a-fA-F]{64,192})'")

    # 结果
    found_keys = {}  # salt_hex -> key_hex
    result = {}

    for pid, mem_kb in pids:
        logger.info(f"扫描 PID={pid} ({mem_kb // 1024}MB)")

        h = kernel32.OpenProcess(0x0010 | 0x0400, False, pid)
        if not h:
            logger.warning(f"无法打开进程 PID={pid}")
            continue

        try:
            regions = _enum_regions(h)
            logger.info(f"  {len(regions)} 个内存区域")

            for base, size in regions:
                data = _read_mem(h, base, size)
                if not data:
                    continue

                for m in hex_re.finditer(data):
                    hex_str = m.group(1).decode('ascii')
                    hex_len = len(hex_str)

                    if hex_len == 96:
                        # x'<64hex_key><32hex_salt>'
                        enc_key_hex = hex_str[:64]
                        salt_hex = hex_str[64:]
                    elif hex_len == 64:
                        # x'<64hex_key>' (需要和数据库 salt 匹配)
                        enc_key_hex = hex_str
                        salt_hex = None
                    elif hex_len > 96 and hex_len % 2 == 0:
                        # 长格式，取前64位为key，后32位为salt
                        enc_key_hex = hex_str[:64]
                        salt_hex = hex_str[-32:]
                    else:
                        continue

                    enc_key_bytes = bytes.fromhex(enc_key_hex)

                    # 如果有 salt，直接匹配
                    if salt_hex and salt_hex in db_files:
                        if salt_hex not in found_keys:
                            # 验证密钥
                            for db_path in db_files[salt_hex]:
                                if _verify_key_against_db(enc_key_bytes, db_path):
                                    found_keys[salt_hex] = enc_key_hex
                                    logger.info(f"  [FOUND] salt={salt_hex} key={enc_key_hex[:16]}...")
                                    break

                    # 如果没有 salt 或 salt 不匹配，尝试所有数据库
                    elif not salt_hex and db_files:
                        for s, paths in db_files.items():
                            if s in found_keys:
                                continue
                            for db_path in paths:
                                if _verify_key_against_db(enc_key_bytes, db_path):
                                    found_keys[s] = enc_key_hex
                                    logger.info(f"  [FOUND] salt={s} key={enc_key_hex[:16]}...")
                                    break

                    # 如果没有数据库来验证，直接记录所有找到的 hex
                    elif not db_files:
                        if hex_len == 96:
                            salt_hex = hex_str[64:]
                            if salt_hex not in found_keys:
                                found_keys[salt_hex] = enc_key_hex
                                logger.info(f"  [FOUND] salt={salt_hex} key={enc_key_hex[:16]}... (未验证)")

        finally:
            kernel32.CloseHandle(h)

        # 如果已经找到所有密钥，停止
        if db_files and len(found_keys) >= len(db_files):
            logger.info("所有密钥已找到")
            break

    # 构建结果
    for salt_hex, key_hex in found_keys.items():
        if salt_hex in db_files:
            for db_path in db_files[salt_hex]:
                result[db_path] = {"key": key_hex, "salt": salt_hex}
        else:
            result[f"unknown_{salt_hex}"] = {"key": key_hex, "salt": salt_hex}

    logger.info(f"共找到 {len(result)} 个数据库密钥")
    return result


def extract_keys_simple(proc_name="Weixin.exe"):
    """
    简化版密钥提取 - 不验证数据库，直接从内存找 hex 模式

    Returns:
        list: [{"key": hex_key, "salt": hex_salt, "hex": full_hex}, ...]
    """
    pids = _get_pids(proc_name)
    if not pids:
        # 尝试其他进程名
        for alt_name in ["WeChatAppEx", "WeChat.exe"]:
            pids = _get_pids(alt_name)
            if pids:
                proc_name = alt_name
                break
    if not pids:
        return []

    hex_re = re.compile(rb"x'([0-9a-fA-F]{96})'")
    results = []
    seen = set()

    for pid, mem_kb in pids:
        h = kernel32.OpenProcess(0x0010 | 0x0400, False, pid)
        if not h:
            continue

        try:
            regions = _enum_regions(h)
            for base, size in regions:
                data = _read_mem(h, base, size)
                if not data:
                    continue

                for m in hex_re.finditer(data):
                    hex_str = m.group(1).decode('ascii')
                    if hex_str not in seen:
                        seen.add(hex_str)
                        results.append({
                            "key": hex_str[:64],
                            "salt": hex_str[64:],
                            "hex": hex_str,
                            "pid": pid,
                            "process": proc_name,
                        })
        finally:
            kernel32.CloseHandle(h)

    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("=" * 60)
    print("  微信密钥提取器")
    print("=" * 60)

    # 尝试所有可能的进程名
    for proc in ["Weixin.exe", "WeChatAppEx", "WeChat.exe"]:
        print(f"\n尝试 {proc}...")
        keys = extract_keys_simple(proc)
        if keys:
            print(f"\n找到 {len(keys)} 个密钥:")
            for k in keys:
                print(f"  Key: {k['key']}")
                print(f"  Salt: {k['salt']}")
                print(f"  Process: {k['process']} (PID={k['pid']})")
                print()
            break
    else:
        print("\n未找到微信进程或密钥")
