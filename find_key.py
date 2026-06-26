import os, re, logging, sys
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
import pymem

pm = pymem.Pymem("WeChatAppEx")
print(f"Attached to PID {pm.process_id}")

# 搜索各种格式的密钥
found = []

for module in pm.list_modules():
    if module.SizeOfImage > 200 * 1024 * 1024:
        continue
    try:
        mem = pm.read_bytes(module.lpBaseOfDll, module.SizeOfImage)
    except:
        continue

    name = module.name

    # 模式1: UTF-8 x'<96hex>'
    for m in re.finditer(rb"x'([0-9a-fA-F]{96})'", mem):
        hex_str = m.group(1).decode('ascii')
        found.append(('x_utf8', name, hex_str[:40] + '...'))

    # 模式2: UTF-16 x'<96hex>'
    for m in re.finditer(rb"x\x00'\x00([0-9a-fA-F\x00]{192})'\x00", mem):
        raw = m.group(1).replace(b'\x00', b'').decode('ascii')
        if len(raw) == 96:
            found.append(('x_utf16', name, raw[:40] + '...'))

    # 模式3: 裸96hex (UTF-8)
    for m in re.finditer(rb'(?<![0-9a-fA-F])([0-9a-fA-F]{96})(?![0-9a-fA-F])', mem):
        hex_str = m.group(1).decode('ascii')
        found.append(('raw_utf8', name, hex_str[:40] + '...'))

    # 模式4: 裸96hex (UTF-16)
    for m in re.finditer(rb'(?<![0-9a-fA-F\x00])((?:[0-9a-fA-F]\x00){96})(?![0-9a-fA-F\x00])', mem):
        raw = m.group(1).replace(b'\x00', b'')
        if len(raw) == 96:
            found.append(('raw_utf16', name, raw[:40].decode('ascii', errors='replace') + '...'))

        # 模式5: 搜索 "salties" 字符串附近
    for m in re.finditer(rb'saltiest', mem):
        try:
            ctx = mem[max(0, m.start()-64):m.end()+128]
            found.append(('salties_ctx', name, str(ctx[:80].hex())))
        except:
            pass

# 去重输出
seen = set()
for fmt, mod, val in found[:50]:
    key = f"{fmt}:{val[:30]}"
    if key not in seen:
        seen.add(key)
        print(f"[{fmt}] {mod}: {val}")
