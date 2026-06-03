# Music Tools

本機使用的音訊工具。第一版支援：

- 上傳 WAV 轉成 320kbps MP3
- 從 YouTube 連結提取 MP3
- 上傳音訊做人聲與伴奏分離，輸出 MP3 zip
- 上傳音訊做樂器分離，可選擇要單獨輸出的聲部，其餘混成 `other.mp3`
- 上傳音訊偵測調性/BPM，並用目標調性與目標 BPM 產生 MP3
- Job status 顯示完成百分比
- 手機與 Mac 在同一個 Wi-Fi 下可透過瀏覽器使用

## 架構

```text
frontend/  React + Vite
backend/   FastAPI + RQ worker
storage/   本機上傳與輸出檔案
Redis      任務佇列
ffmpeg     音訊轉檔
yt-dlp     YouTube 音訊下載
Demucs     人聲/伴奏與樂器分離
librosa    調性與 BPM 偵測
rubberband 高品質移調與速度調整
```

## 系統需求

Mac Apple Silicon 建議使用 Homebrew：

```bash
brew install ffmpeg redis
```

YouTube 功能還需要：

```bash
brew install yt-dlp
```

移調與速度調整還需要：

```bash
brew install rubberband
```

分離功能會透過 Python 安裝 Demucs 與 PyTorch。第一次執行時會下載 `htdemucs_ft` 或 `htdemucs_6s` 模型，時間會比較久。

## Backend 安裝

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Frontend 安裝

```bash
cd frontend
npm install
```

## 啟動

如果是拿到 `music-tools-mac-arm64.zip`，建議使用雙擊流程：

```text
1. 解壓縮 music-tools-mac-arm64.zip
2. 右鍵打開 1-Install.command
3. 右鍵打開 2-Start.command
4. 手機打開 terminal 顯示的 Wi-Fi 網址
5. 要停止時打開 3-Stop.command，或在 2-Start.command 視窗按 Ctrl+C
```

第一次執行 `.command` 時，macOS 可能會阻擋未簽章腳本。請用右鍵選 `Open`，不要直接雙擊。

建議使用一鍵啟動腳本：

```bash
./scripts/start-dev.sh
```

它會啟動 Redis、Backend API、Worker、Frontend，並印出電腦與手機連線網址。保持這個 terminal 開著，按 `Ctrl+C` 可停止服務。

也可以手動開 4 個 terminal。

1. Redis

```bash
redis-server
```

2. Backend API

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

3. Worker

```bash
cd backend
source .venv/bin/activate
python -m app.worker
```

4. Frontend

```bash
cd frontend
npm run dev
```

電腦打開：

```text
http://localhost:5180
```

手機與 Mac 連同一個 Wi-Fi 後，打開：

```text
http://你的Mac區網IP:5180
```

查 Mac 區網 IP：

```bash
ipconfig getifaddr en0
```

## 手機安裝

目前前端已包含基本 PWA manifest。手機同 Wi-Fi 打開網址後，可以加入主畫面使用。

iPhone Safari：

```text
分享 -> 加入主畫面
```

Android Chrome：

```text
選單 -> Add to Home screen / Install app
```

注意：音訊處理仍然在 Mac 上執行，手機只是操作介面。請保持 `./scripts/start-dev.sh` 的 terminal 開著。

## 製作發佈包

在開發機上產生可交給其他 Mac Apple Silicon 使用者的 zip：

```bash
./scripts/package-release.sh
```

輸出：

```text
dist/music-tools-mac-arm64.zip
```

發佈包不包含 `.venv`、`node_modules`、前端 build、上傳檔、輸出檔、暫存檔。使用者第一次執行 `1-Install.command` 時會自動安裝依賴。

## API

```text
GET  /api/health
POST /api/jobs/upload
POST /api/jobs/youtube
POST /api/jobs/separate-vocals
POST /api/jobs/separate-instruments
POST /api/audio/analyze
POST /api/jobs/transform
GET  /api/jobs/{job_id}
GET  /api/jobs/{job_id}/download
```

`GET /api/jobs/{job_id}` 會回傳 `progress`，範圍是 `0` 到 `100`。

## 分離功能輸出

`POST /api/jobs/separate-vocals` 支援：

```text
wav, mp3, flac, m4a, aac
```

完成後下載 zip，內容包含：

```text
vocals.mp3
accompaniment.mp3
```

人聲/伴奏分離固定使用較高品質的 Demucs `htdemucs_ft` 模型。

`POST /api/jobs/separate-instruments` 使用 form-data：

```text
file: audio file
stems: drums
stems: bass
stems: guitar
quality: standard
```

可選擇的 `stems`：

```text
vocals, drums, bass, guitar, piano, other
```

前端預設不勾選任何聲部，避免誤把預設聲部一起輸出。

樂器分離品質模式：

```text
standard: 標準，最快，不使用 shifts
high: 高品質，使用 --shifts 2
highest: 最高品質，使用 --shifts 4，最慢
```

完成後下載 zip。勾選的聲部會各自輸出 MP3，未勾選的聲部會混成：

```text
other.mp3
```

如果勾選了 `other`，模型的其他樂器會輸出為 `other.mp3`；剩下未勾選的聲部會混成：

```text
remaining.mp3
```

例如選擇 `drums`, `bass`, `guitar`，zip 內容會是：

```text
drums.mp3
bass.mp3
guitar.mp3
other.mp3
```

預設使用 CPU：

```text
DEMUCS_DEVICE=cpu
```

若要測 Apple Silicon MPS，可自行用環境變數啟動 worker：

```bash
DEMUCS_DEVICE=mps python -m app.worker
```

## 移調與速度調整

流程：

```text
POST /api/audio/analyze
  -> 回傳 file_id、目前調性、目前 BPM

POST /api/jobs/transform
  -> 使用 file_id、semitones、target_bpm 建立處理 job
```

移調使用半音：

```text
-12 到 +12
```

速度調整使用目標 BPM，不使用倍數。

輸出固定為 320kbps MP3。

## 後續計劃

- PWA 安裝體驗
- 任務清理與歷史紀錄

## 注意

YouTube 下載功能只應用於你有權使用的內容。
