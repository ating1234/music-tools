from pathlib import Path
import ipaddress
import os
import shutil
import socket
import urllib.parse
import logging

import requests

logger = logging.getLogger(__name__)

# 社群 Cobalt 節點（依 cobalt.directory 評分排序，2026-06 更新）
# 注意：YouTube 支援需節點配置 OAuth token，無法由外部控制；節點可能隨時下線
COBALT_NODES = [
    "https://nuko-c.meowing.de/",       # 100% score, 23/23 services
    "https://cobalt.meowing.de/",        # confirmed YouTube working (HN)
    "https://apicobalt.mgytr.top/",      # 96% score, 22/23 services
    "https://cobaltapi.squair.xyz/",     # 91% score, 21/23 services
    "https://lime.clxxped.lol/",         # 87% score
    "https://grapefruit.clxxped.lol/",   # 87% score
    "https://api.qwkuns.me/",            # 87% score
    "https://cobaltapi.kittycat.boo/",   # 87% score (舊清單保留)
    "https://fox.kittycat.boo/",         # 87% score (舊清單保留)
    "https://dog.kittycat.boo/",         # 87% score (舊清單保留)
]

# yt-dlp 依序嘗試的 player client（ios/mweb 通常可繞過 bot 偵測）
_YTDLP_CLIENTS = [
    ["ios"],
    ["mweb"],
    ["android_creator"],
    ["web_creator"],
]

# Cobalt 依序嘗試的 payload（涵蓋不同版本格式）
_COBALT_PAYLOADS = [
    {"downloadMode": "audio"},                                                      # v10 最精簡
    {"downloadMode": "audio", "audioFormat": "mp3", "filenameStyle": "basic"},     # v10 完整
    {},                                                                              # 裸最小值
]


def _assert_public_url(url: str) -> None:
    """拒絕指向私有/保留 IP 的 URL，防止 SSRF。"""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"不允許的 URL scheme: {parsed.scheme!r}")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("URL 缺少 hostname")

    try:
        addr = ipaddress.ip_address(socket.gethostbyname(hostname))
    except socket.gaierror as exc:
        raise ValueError(f"無法解析 hostname {hostname!r}: {exc}") from exc

    if not addr.is_global or addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved or addr.is_multicast:
        raise ValueError(f"拒絕連線至非公開 IP: {addr}")


def _try_ytdlp(url: str, target_dir: Path) -> Path:
    """使用 yt-dlp 下載，依序嘗試不同 player client。"""
    import yt_dlp  # 延遲 import，避免未安裝時炸掉整個模組

    output_path = target_dir / "youtube.mp3"
    cookies_file = os.getenv("YTDLP_COOKIES_FILE", "")
    errors: list[str] = []

    for client in _YTDLP_CLIENTS:
        outtmpl = str(target_dir / "%(id)s.%(ext)s")
        opts: dict = {
            "format": "bestaudio[ext=m4a]/bestaudio/best",
            "outtmpl": outtmpl,
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "320",
            }],
            "extractor_args": {"youtube": {"player_client": client}},
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
        }
        if cookies_file and Path(cookies_file).exists():
            opts["cookiefile"] = cookies_file

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True) or {}

            video_id = info.get("id", "")
            candidate = target_dir / f"{video_id}.mp3"
            if candidate.exists():
                shutil.move(str(candidate), str(output_path))
            else:
                mp3_files = [f for f in target_dir.glob("*.mp3") if f != output_path]
                if not mp3_files:
                    raise FileNotFoundError("找不到 yt-dlp 輸出的 mp3")
                shutil.move(str(mp3_files[0]), str(output_path))

            logger.info(f"yt-dlp player_client={client} 成功")
            return output_path

        except Exception as exc:
            errors.append(f"client={client}: {exc}")
            logger.warning(f"yt-dlp player_client={client} 失敗: {exc}")

    raise RuntimeError("yt-dlp 所有 player client 均失敗:\n" + "\n".join(errors))


def _try_cobalt(url: str, target_dir: Path) -> Path:
    """透過 Cobalt 社群節點下載（備援）。"""
    output_path = target_dir / "youtube.mp3"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        # 部分節點會封鎖 Python requests 預設 UA
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    }
    node_errors: list[str] = []

    for node in COBALT_NODES:
        for extra in _COBALT_PAYLOADS:
            payload = {"url": url, **extra}
            try:
                resp = requests.post(node, headers=headers, json=payload, timeout=12)
                if resp.status_code != 200:
                    node_errors.append(f"{node} -> HTTP {resp.status_code}: {resp.text[:120]}")
                    break  # 換下一個節點

                data = resp.json()
                if data.get("status") in ("redirect", "tunnel", "stream") and data.get("url"):
                    download_url = data["url"]
                    _assert_public_url(download_url)
                    with requests.get(download_url, stream=True, timeout=60) as r:
                        r.raise_for_status()
                        with open(output_path, "wb") as f:
                            for chunk in r.iter_content(chunk_size=8192):
                                if chunk:
                                    f.write(chunk)
                    logger.info(f"Cobalt 節點 {node} (payload={list(extra)}) 成功")
                    return output_path

                # error 或未知 status：記錄後嘗試下一個 payload
                error_code = (data.get("error") or {}).get("code") or data.get("text") or data.get("status")
                node_errors.append(f"{node} payload={list(extra)} -> {error_code}")

            except ValueError as exc:
                raise RuntimeError(f"Cobalt 下載 URL 安全驗證失敗: {exc}") from exc
            except Exception as exc:
                node_errors.append(f"{node} -> {type(exc).__name__}: {exc}")
                break  # 連線失敗，直接換節點

    raise RuntimeError(
        "Cobalt 所有節點均失敗:\n" + "\n".join(f" - {e}" for e in node_errors)
    )


def download_youtube_mp3(url: str, target_dir: Path) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"開始下載 YouTube: {url}")

    # 主力：Cobalt（第三方 IP 代理，繞過雲端主機 IP 封鎖）
    try:
        return _try_cobalt(url, target_dir)
    except Exception as cobalt_err:
        logger.warning(f"Cobalt 全部失敗，切換至 yt-dlp 備援: {cobalt_err}")

    # 備援：yt-dlp（本機環境或 IP 未被封鎖時可用）
    try:
        return _try_ytdlp(url, target_dir)
    except Exception as ytdlp_err:
        raise RuntimeError(
            "【YouTube 轉換失敗】\n"
            f"Cobalt 錯誤:\n{cobalt_err}\n\n"
            f"yt-dlp 備援錯誤:\n{ytdlp_err}\n\n"
            "請確認影片網址是否正確，或改用「上傳音訊檔案」功能。"
        ) from ytdlp_err
