from pathlib import Path
import requests
import logging

logger = logging.getLogger(__name__)

# 使用 2026年最新且經 cobalt.directory 驗證對 YouTube 支援 Working 且不需 JWT 驗證的社群節點作為備用
COBALT_NODES = [
    "https://fox.kittycat.boo/",
    "https://dog.kittycat.boo/",
    "https://cobaltapi.kittycat.boo/",
    "https://api.cobalt.blackcat.sweeux.org/",
    "https://api.cobalt.liubquanti.click/",
    "https://cobaltapi.cjs.nz/",
]

def download_youtube_mp3(url: str, target_dir: Path) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    output_path = target_dir / "youtube.mp3"

    logger.info(f"開始使用雲端代理服務解析 YouTube URL: {url}")
    
    # 符合 Cobalt v10 最新規格 of API Payload
    payload = {
        "url": url,
        "downloadMode": "audio",   # 取代舊的 isAudioOnly: True
        "audioFormat": "mp3",      # 取代舊的 aFormat: "mp3"
        "filenameStyle": "basic"   # 取代舊的 filenamePattern: "basic"
    }
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

    download_url = None
    node_errors = []

    # 嘗試不同的 Cobalt API 節點進行影片解析
    for node in COBALT_NODES:
        try:
            logger.info(f"嘗試使用雲端代理節點: {node}")
            # 發送 POST 請求到節點的根路徑 (符合 v10 API / 規範)
            resp = requests.post(node, headers=headers, json=payload, timeout=12)
            if resp.status_code == 200:
                data = resp.json()
                # v10 API 回傳狀態可能為 redirect 或 tunnel (由 Cobalt 代理中轉串流)
                if data.get("status") in ["redirect", "tunnel", "stream"] and data.get("url"):
                    download_url = data["url"]
                    logger.info(f"成功透過節點 {node} 解析下載 URL")
                    break
                elif data.get("status") == "error":
                    node_errors.append(f"{node} -> API 錯誤: {data.get('text') or data.get('error')}")
                else:
                    node_errors.append(f"{node} -> 未知回應狀態: {data.get('status')}")
            else:
                node_errors.append(f"{node} -> HTTP {resp.status_code}: {resp.text[:100]}")
        except Exception as e:
            node_errors.append(f"{node} -> 連線失敗: {type(e).__name__} ({str(e)})")
            continue

    if not download_url:
        # 將所有節點的錯誤串接起來，方便排查
        error_details = "\n".join(f" - {err}" for err in node_errors)
        friendly_err = (
            "【YouTube 轉換失敗】\n"
            "無法透過雲端下載代理服務解析該 YouTube 影片網址。\n"
            f"雲端代理詳細錯誤日誌如下：\n{error_details}\n\n"
            "請確認影片網址是否正確，或者改用本機「上傳音訊檔案」功能。"
        )
        raise RuntimeError(friendly_err)

    # 從解析出來的直連 URL 下載 MP3 檔案
    try:
        logger.info(f"開始從代理節點下載音訊流...")
        with requests.get(download_url, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(output_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
        logger.info("音訊下載並轉換成功")
    except Exception as e:
        raise RuntimeError(f"下載音訊流失敗：{str(e)}")

    return output_path
