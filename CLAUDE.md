# Music Tools Project Notes

## Current Goal

## 本機使用的 music tools，目標是在 Mac Apple Silicon 上執行，並能透過同一 Wi-Fi 讓手機瀏覽器使用。

## Architecture Decisions

- Frontend: React + Vite + TypeScript
- Backend: FastAPI
- Background jobs: RQ + Redis
- Audio conversion: ffmpeg
- Key/BPM analysis: librosa
- Pitch shift/time stretch: rubberband CLI
- Storage: local filesystem under `storage/`
- Quality preference: prioritize quality over speed

## Implemented v1 Skeleton

- WAV upload to 320kbps MP3 job
- Job status polling API
- Output download endpoint
- Responsive frontend UI

## Implemented v2 Vocal Separation

- Upload audio to Demucs `htdemucs_ft` two-stem vocal separation job
- Supported uploads: wav, mp3, flac, m4a, aac
- Output zip includes `vocals.mp3` and `accompaniment.mp3`
- Default Demucs device is `cpu`; can be overridden with `DEMUCS_DEVICE`

## Implemented v3 Instrument Separation

- Upload audio to Demucs `htdemucs_6s` six-stem separation job
- Supported uploads: wav, mp3, flac, m4a, aac
- User can choose separate stems from `vocals`, `drums`, `bass`, `guitar`, `piano`, and `other`
- Selected stems are exported as MP3; unselected stems are mixed into `other.mp3`, or `remaining.mp3` when `other` is selected separately
- Quality mode supports `standard` (`--shifts 0`), `high` (`--shifts 2`), and `highest` (`--shifts 4`)
- Uses same `DEMUCS_DEVICE` setting as vocal separation

## Implemented Job Progress

- Job API returns `progress` from 0 to 100
- Conversion and download jobs use coarse phase progress
- Demucs jobs parse CLI percentage output when available and also update phase progress

## Implemented v4 Pitch And Tempo

- Upload audio for key and BPM analysis using librosa
- Transform job uses rubberband CLI with semitone pitch shift and target BPM tempo change
- UI displays detected key/BPM and adjusted key/BPM before creating the MP3 job
- Output is 320kbps MP3## Option B Optimization & AdSense Integration

- Removed transcription feature (and its huge dependencies basic-pitch, onnxruntime, pretty_midi, music21) to reduce environment size by 500MB+ and speed up install.
- Redesigned UI to a dual-column layout: Left Main Rack (CH 01-04), Right Sidebar Console (LCD display + History + 300x250 Simulated VU-Meter Google Ad slot).
- Added Base Power Strip Ad module (728x90 Banner Ad) at the bottom.
- Added Graceful AdBlocker fallback (Blind Metal Panel) and CLS prevention for Ads.

## Removed YouTube to MP3 Feature

- YouTube 下載功能因 Hugging Face 雲端 IP 被 YouTube 封鎖而無法穩定運作，已於 2026-06-08 完整移除。
- 根本原因：YouTube 封鎖資料中心 IP（HF、GCP、AWS 等），與 yt-dlp player_client 或 Cobalt 節點格式無關。
- 已於 2026-06-12 徹底移除 `backend/app/youtube.py` 主程式與 `backend/requirements.txt` 中的 `yt-dlp` 套件依賴，防範潛在安全隱憂並清理死程式碼。
- 頻道重新編號：CH 01 WAV、CH 02 Vocal、CH 03 Stems、CH 04 Pitch（原 CH 02 YT 已移除）。

## Implemented PWA & Job History

- PWA service worker (`public/sw.js`) registered on load; caches app shell for offline/installable use
- `GET /api/jobs` — list all jobs from all RQ registries (finished, failed, started, queued)
- `DELETE /api/jobs/{job_id}` — remove job from Redis and delete upload/output files from storage
- Frontend job history panel in LCD area: expandable, shows kind/status/filename, DL and DEL buttons per row

## Security Reinforcement (公網部署安全性加固)

為了確保在公網 (`music-tools.ating123.com`) 運行的安全性，已進行以下安全性升級：
1. **移除本機執行環境**：
   - 已刪除所有 Mac 本機專用的安裝、啟動與打包腳本 (`1-Install.command`, `2-Start.command`, `3-Stop.command` 與整個 `scripts/` 目錄)。
2. **API 金鑰安全認證**：
   - 限制了所有 API 端點（FastAPI 與 Gradio）。除了 `/api/health` 之外，所有敏感請求均需經過 Bearer Token 驗證。
   - 後端環境變數：**`MTS_ENGINE_SECRET`** (支援 Header 與 URL Query 驗證)。
   - 前端環境變數：**`VITE_MTS_ENGINE_SECRET`** (在 Gradio Client 連線時自動注入 Header)。
3. **Bug Center 安全升級**：
   - 密碼演算法加固：使用加鹽且迭代 100,000 次的 `PBKDF2`（向下相容舊的 `sha256` 密碼）。
   - 資料庫 Session 儲存：在 SQLite 新增了 `sessions` 資料表進行持久化會話管理，避免伺服器重啟強登出。
   - Cookie 安全限制：加入 `secure=True`（強制 HTTPS 協定）與 `samesite="strict"`。
