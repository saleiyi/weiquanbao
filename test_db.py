import sqlite3, os

db_path = r'D:\浏览器下载\weiquanbao\data\wechat_decrypted\MicroMsg.db'
print('Exists:', os.path.exists(db_path))

conn = sqlite3.connect(db_path)
conn.text_factory = str
tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
print('Tables:', [t[0] for t in tables[:30]])
conn.close()
