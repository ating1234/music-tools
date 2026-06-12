import sqlite3
import json
import hashlib
import uuid
import secrets
from pathlib import Path

DB_FILE = Path(__file__).parent / "bug_center.db"

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    # 建立 Bug 報告資料表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS bug_reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        app_name TEXT NOT NULL,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        email TEXT,
        meta TEXT,
        status TEXT DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    
    # 建立設定資料表 (Key-Value)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    );
    """)
    
    # 建立 Sessions 資料表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
        session_id TEXT PRIMARY KEY,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    
    conn.commit()
    
    # 初始化預設值
    # 1. 預設 API 金鑰 (用於客戶端對接驗證)
    if not get_setting("api_key"):
        set_setting("api_key", str(uuid.uuid4())[:18])
        
    # 2. 預設管理員密碼雜湊 (預設密碼為: admin1234)
    if not get_setting("password_hash"):
        default_pw = "admin1234"
        pw_hash = hash_password(default_pw)
        set_setting("password_hash", pw_hash)
        
    # 3. 預設 Telegram 欄位
    if get_setting("telegram_token") is None:
        set_setting("telegram_token", "")
    if get_setting("telegram_chat_id") is None:
        set_setting("telegram_chat_id", "")
        
    conn.close()

def get_setting(key):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row["value"] if row else None

def set_setting(key, value):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()
    conn.close()

def add_bug_report(app_name, title, description, email, meta_dict):
    conn = get_db()
    cursor = conn.cursor()
    meta_json = json.dumps(meta_dict) if meta_dict else "{}"
    cursor.execute(
        "INSERT INTO bug_reports (app_name, title, description, email, meta) VALUES (?, ?, ?, ?, ?)",
        (app_name, title, description, email, meta_json)
    )
    conn.commit()
    report_id = cursor.lastrowid
    conn.close()
    return report_id

def get_all_reports(status=None):
    conn = get_db()
    cursor = conn.cursor()
    if status:
        cursor.execute("SELECT * FROM bug_reports WHERE status = ? ORDER BY created_at DESC", (status,))
    else:
        cursor.execute("SELECT * FROM bug_reports ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    
    # 轉換成 dict 列表
    reports = []
    for r in rows:
        meta_dict = {}
        try:
            meta_dict = json.loads(r["meta"]) if r["meta"] else {}
        except Exception:
            pass
            
        reports.append({
            "id": r["id"],
            "app_name": r["app_name"],
            "title": r["title"],
            "description": r["description"],
            "email": r["email"],
            "meta": meta_dict,
            "status": r["status"],
            "created_at": r["created_at"]
        })
    return reports

def update_report_status(report_id, status):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE bug_reports SET status = ? WHERE id = ?", (status, report_id))
    conn.commit()
    conn.close()

def delete_report(report_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM bug_reports WHERE id = ?", (report_id,))
    conn.commit()
    conn.close()

def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    iterations = 100000
    hash_bytes = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        iterations
    )
    return f"pbkdf2_sha256${iterations}${salt}${hash_bytes.hex()}"

def verify_password(password):
    if not password:
        return False
    stored_val = get_setting("password_hash")
    if not stored_val:
        return False
    
    if not stored_val.startswith("pbkdf2_sha256$"):
        # 兼容舊的 sha256 雜湊
        pw_hash = hashlib.sha256(password.encode('utf-8')).hexdigest()
        return pw_hash == stored_val
        
    try:
        algo, iterations_str, salt, stored_hash = stored_val.split("$")
        iterations = int(iterations_str)
        hash_bytes = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            iterations
        )
        return hash_bytes.hex() == stored_hash
    except Exception:
        return False

def update_password(new_password):
    pw_hash = hash_password(new_password)
    set_setting("password_hash", pw_hash)

def add_session(session_id: str) -> None:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO sessions (session_id) VALUES (?)", (session_id,))
    conn.commit()
    conn.close()

def verify_session(session_id: str) -> bool:
    if not session_id:
        return False
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT session_id FROM sessions WHERE session_id = ?", (session_id,))
    row = cursor.fetchone()
    conn.close()
    return row is not None

def delete_session(session_id: str) -> None:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
    conn.commit()
    conn.close()

# 初始化
init_db()
