import sqlite3, os

db_path = os.path.join(os.path.dirname(__file__), 'data/wechat_decrypted/MicroMsg.db')
if not os.path.exists(db_path):
    print(f"DB not found: {db_path}")
    exit()

conn = sqlite3.connect(db_path)
conn.text_factory = str

tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
print('Tables:', [t[0] for t in tables[:30]])

try:
    contacts = conn.execute('SELECT UserName, NickName, Remark, Type FROM Contact LIMIT 10').fetchall()
    print('\nContacts (first 10):')
    for c in contacts:
        print(f'  [{c[3]}] {c[0][:25]} | {c[1][:20]} | {c[2][:20]}')
except Exception as e:
    print(f'Contact error: {e}')

try:
    sessions = conn.execute('SELECT strUsrName, iLastMsgTime FROM Session LIMIT 10').fetchall()
    print(f'\nSessions: {len(sessions)} (first 10)')
    for s in sessions:
        print(f'  {s[0][:25]} | time={s[1]}')
except Exception as e:
    print(f'Session error: {e}')
    # Try to find session-like tables
    for t in tables:
        if 'session' in t[0].lower() or 'contact' in t[0].lower():
            try:
                cols = conn.execute(f'PRAGMA table_info("{t[0]}")').fetchall()
                print(f'  Table {t[0]} columns: {[(c[1], c[2]) for c in cols]}')
            except:
                pass

conn.close()
