# Music Tools Project Notes

## Current Goal

本機使用的 music tools，目標是在 Mac Apple Silicon 上執行，並能透過同一 Wi-Fi 讓手機瀏覽器使用。

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

## Implemented Mac Release Packaging

- Root scripts: `1-Install.command`, `2-Start.command`, `3-Stop.command`
- Release builder: `scripts/package-release.sh`
- Release output: `dist/music-tools-mac-arm64.zip`
- Package excludes local environments and storage outputs; end users install dependencies with `1-Install.command`

## Operational Notes

- `2-Start.command` now verifies that port 8000 is serving Music Tools `/api/health`; if another app occupies port 8000, it prints the owning process and exits instead of silently connecting the frontend to the wrong backend.

## Removed YouTube to MP3 Feature

- YouTube 下載功能因 Hugging Face 雲端 IP 被 YouTube 封鎖而無法穩定運作，已於 2026-06-08 完整移除
- 根本原因：YouTube 封鎖資料中心 IP（HF、GCP、AWS 等），與 yt-dlp player_client 或 Cobalt 節點格式無關
- 解法需要自架 Cobalt 實例並配置 YouTube OAuth token，成本超過此功能的價值
- `backend/app/youtube.py` 保留 SSRF 防護函數 (`_assert_public_url`) 與 Cobalt/yt-dlp 邏輯，以備未來重新啟用
- 若日後重新加回此功能，建議：自架 Cobalt（Oracle Cloud Always Free + YouTube OAuth 最穩定）
- 頻道重新編號：CH 01 WAV、CH 02 Vocal、CH 03 Stems、CH 04 Pitch（原 CH 02 YT 已移除）

## Implemented PWA & Job History

- PWA service worker (`public/sw.js`) registered on load; caches app shell for offline/installable use
- `GET /api/jobs` — list all jobs from all RQ registries (finished, failed, started, queued)
- `DELETE /api/jobs/{job_id}` — remove job from Redis and delete upload/output files from storage
- Frontend job history panel in LCD area: expandable, shows kind/status/filename, DL and DEL buttons per row
