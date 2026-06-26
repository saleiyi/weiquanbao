import os, sys, struct, hashlib
os.chdir(r'D:\浏览器下载\weiquanbao')

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

import pymem, logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# 读加密文件
enc_path = r"C:\Users\fan\Documents\WeChat Files\wxid_u33l4i98gkf622\Msg\MicroMsg.db"
with open(enc_path, 'rb') as f:
    data = f.read()
print(f'文件大小: {len(data)}')
print(f'前32字节hex: {data[:32].hex()}')
print(f'非标准SQLite头: {data[:16] != b"SQLite format 3"}')

# 从内存提取密钥
pm = pymem.Pymem("WeChatAppEx")
found_key = None
for m in pm.list_modules():
    try:
        mb = pm.read_bytes(m.lpBaseOfDll, min(m.SizeOfImage, 200*1024*1024))
        sig = b'\x78\x00\x00\x00\x00\x00\x00\x00'
        off = mb.find(sig)
        if off != -1:
            k = mb[off + 0x70:off + 0x70 + 32]
            if len(k) == 32 and k != b'\x00'*32 and k[0] != 0:
                print(f'找到密钥: {k.hex()}')
                found_key = k
                break
    except:
        continue

if not found_key:
    print('密钥未找到')
    sys.exit(1)

# 尝试不同配置解密
configs = [
    ('4096_salt16_kdf64000', 4096, True, 64000, 16, 0),
    ('4096_salt16_kdf4000', 4096, True, 4000, 16, 0),
    ('4096_salt32_kdf64000', 4096, True, 64000, 32, 0),
    ('4096_nosalt_kdf64000', 4096, True, 64000, 0, 0),
    ('4096_rawkey_nokdf', 4096, False, 0, 16, 0),
    ('4096_rawkey_nosalt', 4096, False, 0, 0, 0),
    ('1024_salt16_kdf4000', 1024, True, 4000, 16, 0),
]

SQLITE_HEADER = b'SQLite format 3\0'
out_dir = r'D:\浏览器下载\weiquanbao\data\wechat_decrypted_test'
os.makedirs(out_dir, exist_ok=True)

for name, page_size, use_kdf, kdf_iter, salt_len, skip_start in configs:
    out = os.path.join(out_dir, f'MicroMsg_{name}.db')
    try:
        page_count = (len(data) + page_size - 1) // page_size
        with open(out, 'wb') as f:
            for i in range(page_count):
                off = i * page_size
                pdata = data[off:off + page_size]
                if len(pdata) < page_size:
                    pdata = pdata.ljust(page_size, b'\x00')

                if i == 0:
                    salt = pdata[:salt_len] if salt_len > 0 else bytes(16)
                    if use_kdf:
                        kdf = PBKDF2HMAC(hashes.SHA1(), 32, salt=salt, iterations=kdf_iter)
                        k = kdf.derive(found_key)
                    else:
                        k = found_key
                else:
                    k = found_key

                start = salt_len if i == 0 else skip_start
                ct = pdata[start:]
                iv = struct.pack('>Q', i) + b'\x00'*8

                c = Cipher(algorithms.AES(k), modes.CBC(iv))
                d = c.decryptor()
                dec = d.update(ct) + d.finalize()

                if i == 0:
                    f.write(SQLITE_HEADER + dec[16:])
                else:
                    f.write(dec)

        # 验证
        import sqlite3
        c = sqlite3.connect(out)
        try:
            tables = c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            if tables:
                print(f'✅ {name}: {[t[0] for t in tables[:10]]}')
            else:
                print(f'❌ {name}: 无表')
        except Exception as e:
            print(f'❌ {name}: {str(e)[:50]}')
        c.close()
    except Exception as e:
        print(f'💥 {name}: {str(e)[:60]}')
