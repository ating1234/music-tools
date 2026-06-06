import sqlite3
import json
import hashlib
import uuid
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
    
    conn.commit()
    
    # 初始化預設值
    # 1. 預設 API 金鑰 (用於客戶端對接驗證)
    if not get_setting("api_key"):
        set_setting("api_key", str(uuid.uuid4())[:18])
        
    # 2. 預設管理員密碼雜湊 (預設密碼為: admin1234)
    if not get_setting("password_hash"):
        default_pw = "admin1234"
        pw_hash = hashlib.sha256(default_pw.encode('utf-8')).hexdigest()
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

def verify_password(password):
    if not password:
        return False
    pw_hash = hashlib.sha256(password.encode('utf-8')).hexdigest()
    stored_hash = get_setting("password_hash")
    return pw_hash == stored_hash

def update_password(new_password):
    pw_hash = hashlib.sha256(new_password.encode('utf-8')).hexdigest()
    set_setting("password_hash", pw_hash)

# 初始化
init_db()
