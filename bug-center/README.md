# ⚡ 集中式私有 Bug 回報系統 (Centralized Bug Center)

這是一個獨立運行、輕量且安全的**集中式 Bug 回報中心**。您可以將旗下所有網站與應用程式（如 Music Tools）對接到此服務，並在私有後台內查看所有用戶的回報，以及在 UI 介面上直接設定 Telegram Bot 通知！

---

## 🚀 系統功能

1. **統一接收端點**：接收各個不同網站發送過來的錯誤報告，寫入 SQLite 資料庫持久化儲存。
2. **安全認證 (API Key)**：客戶端對接時需帶上 `X-Bug-API-Key` 進行驗證，保障接口安全。
3. **私有管理控制台**：管理員登入後可以查看所有 Bug 詳細資料與環境參數、標記處理狀態或刪除。
4. **介面化 Telegram Bot 設定**：直接在管理後台輸入您的 Telegram Bot Token 與 Chat ID 並存入資料庫，不需手動去後端配置環境變數，新 Bug 送達時會即時通知至 Telegram！

---

## 🛠️ 啟動步驟 (本地運行)

1. 進入 `bug-center` 目錄：
   ```bash
   cd bug-center
   ```
2. 安裝 Python 依賴套件：
   ```bash
   pip install -r requirements.txt
   ```
3. 啟動伺服器：
   ```bash
   python app.py
   ```
   *伺服器將預設運行於：`http://localhost:8088`*

---

## 🔒 登入與預設密碼

* **後台網址**：`http://localhost:8088/login`
* **預設管理員密碼**：`admin1234`
  *(登入後，請第一時間前往「系統設定」修改管理員密碼以策安全。)*

---

## 🛰️ 客戶端對接方式

請將您所有要對接的網頁應用程式（如 Music Tools）的 Bug 送出請求指向此伺服器：

* **API 網址**：`http://localhost:8088/api/reports` (如果是部署在雲端，請改為對應網址，例如 `https://your-bug-center.render.com/api/reports`)
* **Headers**：
  * `Content-Type: application/json`
  * `X-Bug-API-Key: [您的對接金鑰]` *(可於回報中心的「系統設定」頁面查看或修改預設金鑰)*
* **JSON Payload 格式**：
  ```json
  {
    "app_name": "Music Tools",
    "title": "Bug 標題",
    "description": "Bug 詳細描述",
    "email": "user@example.com",
    "meta": {
      "user_agent": "Mozilla/5.0...",
      "timestamp": "2026-06-06T18:25:00"
    }
  }
  ```
