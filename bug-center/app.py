import os
import uuid
import urllib.request
import json
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, Request, Form, HTTPException, Header, Depends, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import database as db

app = FastAPI(title="Centralized Bug Center")

# 設定模板目錄
TEMPLATES_DIR = Path(__file__).parent / "templates"
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# 單次運行隨機 Session Key，重啟即失效，防止偽造
SESSION_KEY = str(uuid.uuid4())

# 輔助：驗證 Telegram 並發送
def trigger_telegram_bot(title, description, email, app_name):
    token = db.get_setting("telegram_token")
    chat_id = db.get_setting("telegram_chat_id")
    
    if not token or not chat_id:
        return False
        
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    message = (
        f"🚨 *【新 Bug 回報通知】*\n\n"
        f"📱 *來源應用*: {app_name}\n"
        f"📝 *主旨*: {title}\n\n"
        f"🔍 *詳細描述*:\n{description}\n\n"
    )
    if email:
        message += f"📧 *聯絡信箱*: {email}\n"
        
    message += f"\n📅 *回報時間*: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    
    data = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    }
    
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            res = json.loads(response.read().decode("utf-8"))
            return res.get("ok", False)
    except Exception as e:
        print(f"Telegram Bot 發送失敗: {e}")
        return False

# 認證中介：確認是否已登入
def get_current_user(request: Request):
    session_cookie = request.cookies.get("admin_session")
    if session_cookie != SESSION_KEY:
        return False
    return True

# 1. 對接 API：接收外部 Bug 回報
@app.post("/api/reports")
async def receive_report(request: Request, x_bug_api_key: str = Header(None, alias="X-Bug-API-Key")):
    stored_key = db.get_setting("api_key")
    if not x_bug_api_key or x_bug_api_key != stored_key:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"success": False, "message": "無效或未提供 API Key"}
        )
        
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"success": False, "message": "無效的 JSON 格式"}
        )
        
    app_name = payload.get("app_name", "Unknown App")
    title = payload.get("title")
    description = payload.get("description")
    email = payload.get("email", "")
    meta = payload.get("meta", {})
    
    if not title or not description:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"success": False, "message": "title 與 description 皆為必填項"}
        )
        
    # 存入 SQLite
    report_id = db.add_bug_report(app_name, title, description, email, meta)
    
    # 觸發 Telegram 通知 (背景執行)
    tg_success = trigger_telegram_bot(title, description, email, app_name)
    
    return {
        "success": True, 
        "message": "Bug 回報成功", 
        "report_id": report_id,
        "telegram_sent": tg_success
    }

# 2. 登入頁面
@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if request.cookies.get("admin_session") == SESSION_KEY:
        return RedirectResponse(url="/admin")
    return templates.TemplateResponse("login.html", {"request": request, "error": None})

# 3. 處理登入
@app.post("/login")
def login(request: Request, password: str = Form(...)):
    if db.verify_password(password):
        response = RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)
        response.set_cookie(key="admin_session", value=SESSION_KEY, httponly=True, samesite="lax")
        return response
    return templates.TemplateResponse("login.html", {"request": request, "error": "密碼錯誤！"})

# 4. 登出
@app.get("/logout")
def logout():
    response = RedirectResponse(url="/login")
    response.delete_cookie("admin_session")
    return response

# 5. 管理控制台 (主頁)
@app.get("/", response_class=HTMLResponse)
@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request, status_filter: str = "pending"):
    if not get_current_user(request):
        return RedirectResponse(url="/login")
        
    reports = db.get_all_reports(status=None if status_filter == "all" else status_filter)
    api_key = db.get_setting("api_key")
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "reports": reports,
        "status_filter": status_filter,
        "api_key": api_key
    })

# 6. 更新狀態 (Resolved / Ignored)
@app.post("/admin/status/{report_id}")
def change_status(request: Request, report_id: int, new_status: str = Form(...)):
    if not get_current_user(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    db.update_report_status(report_id, new_status)
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)

# 7. 刪除回報
@app.post("/admin/delete/{report_id}")
def delete_report(request: Request, report_id: int):
    if not get_current_user(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    db.delete_report(report_id)
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)

# 8. 設定頁面 (查看/更新 Telegram 等配置)
@app.get("/admin/settings", response_class=HTMLResponse)
def settings_page(request: Request):
    if not get_current_user(request):
        return RedirectResponse(url="/login")
        
    tg_token = db.get_setting("telegram_token")
    tg_chat_id = db.get_setting("telegram_chat_id")
    api_key = db.get_setting("api_key")
    
    return templates.TemplateResponse("settings.html", {
        "request": request,
        "telegram_token": tg_token,
        "telegram_chat_id": tg_chat_id,
        "api_key": api_key,
        "error": None,
        "success": None
    })

# 9. 保存設定
@app.post("/admin/settings")
def update_settings(
    request: Request,
    telegram_token: str = Form(""),
    telegram_chat_id: str = Form(""),
    api_key: str = Form(...),
    new_password: str = Form(""),
    confirm_password: str = Form("")
):
    if not get_current_user(request):
        return RedirectResponse(url="/login")
        
    error = None
    success = None
    
    # 修改密碼驗證
    if new_password:
        if new_password != confirm_password:
            error = "新密碼與確認密碼不一致！"
        else:
            db.update_password(new_password)
            success = "密碼修改成功！"
            
    if not error:
        db.set_setting("telegram_token", telegram_token.strip())
        db.set_setting("telegram_chat_id", telegram_chat_id.strip())
        db.set_setting("api_key", api_key.strip())
        success = "設定更新成功！"
        
    return templates.TemplateResponse("settings.html", {
        "request": request,
        "telegram_token": telegram_token,
        "telegram_chat_id": telegram_chat_id,
        "api_key": api_key,
        "error": error,
        "success": success
    })

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8088)
