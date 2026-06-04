import os
import shutil
import sys
import subprocess
import importlib.util
from pathlib import Path

# 動態安裝 demucs 避免與 Hugging Face 內置的 torchaudio 衝突
spec = importlib.util.find_spec("demucs")
if spec is None:
    print("Demucs 找不到，正在透過無依賴模式進行動態安裝...")
    # 必須從 GitHub 安裝以取得最新的 demucs.api
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "--no-deps", "git+https://github.com/facebookresearch/demucs"],
        check=True
    )
    import site
    import importlib
    importlib.reload(site)

import demucs.api
import gradio as gr
import torch

from app.demucs import separate_vocals as local_separate_vocals, separate_instruments as local_separate_instruments
from app.youtube import download_youtube_mp3
from app.analyze import analyze_audio
from app.audio import transform_audio as local_transform_audio

# 建立暫存與輸出路徑
STORAGE_DIR = Path("/tmp/gradio-music-tools")
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

# 1. 音訊分析 API
def analyze_api(audio_file):
    if not audio_file:
        return {"error": "No file uploaded"}
    try:
        res = analyze_audio(Path(audio_file))
        return res
    except Exception as e:
        return {"error": str(e)}

# 2. 變速變調 API
def transform_api(audio_file, semitones, target_bpm):
    if not audio_file:
        return None
    try:
        # 分析原始 BPM
        analysis = analyze_audio(Path(audio_file))
        source_bpm = analysis.get("bpm", 120)
        
        out_dir = STORAGE_DIR / "output"
        out_dir.mkdir(parents=True, exist_ok=True)
        output_path = out_dir / f"transform_{semitones}_{target_bpm}.mp3"
        
        work_dir = STORAGE_DIR / "work_transform"
        local_transform_audio(
            Path(audio_file),
            output_path,
            semitones=int(semitones),
            source_bpm=float(source_bpm),
            target_bpm=float(target_bpm),
            work_dir=work_dir
        )
        return str(output_path)
    except Exception as e:
        raise gr.Error(f"處理失敗: {str(e)}")

# 3. 人聲分離 API (不再需要 GPU，因為外包給了 abidlabs/music-separation)
def separate_vocals_api(audio_file, progress=gr.Progress(track_tqdm=True)):
    if not audio_file:
        return None
    try:
        work_dir = STORAGE_DIR / "work_vocals"
        output_zip = STORAGE_DIR / "output" / "vocals_accompaniment.zip"
        output_zip.parent.mkdir(parents=True, exist_ok=True)
        
        # 呼叫底層分離 (在背景透過 API 外包計算)
        local_separate_vocals(
            Path(audio_file), 
            work_dir, 
            output_zip, 
            progress_callback=lambda p: progress(p / 100.0, desc="人聲分離中...")
        )
        return str(output_zip)
    except Exception as e:
        raise gr.Error(f"分離人聲失敗: {str(e)}")

# 4. 樂器分離 API (在本地 CPU 上運行)
def separate_instruments_api(audio_file, stems, quality, progress=gr.Progress(track_tqdm=True)):
    if not audio_file or not stems:
        return None
    try:
        work_dir = STORAGE_DIR / "work_instruments"
        output_zip = STORAGE_DIR / "output" / "instruments.zip"
        output_zip.parent.mkdir(parents=True, exist_ok=True)
        
        # 映射 shifts 參數
        shifts = 0
        if quality == "high":
            shifts = 2
        elif quality == "highest":
            shifts = 4
            
        local_separate_instruments(
            Path(audio_file),
            work_dir,
            output_zip,
            selected_stems=stems,
            shifts=shifts,
            progress_callback=lambda p: progress(p / 100.0, desc="樂器分離中...")
        )
        return str(output_zip)
    except Exception as e:
        raise gr.Error(f"分離樂器失敗: {str(e)}")

# 5. YouTube 下載 API
def youtube_download_api(url):
    try:
        temp_dir = STORAGE_DIR / "youtube"
        output_path = download_youtube_mp3(url, temp_dir)
        return str(output_path)
    except Exception as e:
        raise gr.Error(f"YouTube 下載失敗: {str(e)}")


# 建立 Gradio Blocks 介面供 REST API 對接
with gr.Blocks(title="Music Tools Engine") as demo:
    gr.Markdown("# Music Tools Backend (ZeroGPU)")
    gr.Markdown("此為 Gradio API 入口，由 React 前端透過 Gradio Client 連線調用。")
    
    # 這裡宣告 API，以供 React 前端以 /gradio_api/ 方式呼叫
    with gr.Tab("APIs"):
        # 分析
        inp_analyze = gr.Audio(type="filepath", label="Input Audio")
        out_analyze = gr.JSON(label="Analysis Results")
        btn_analyze = gr.Button("Analyze")
        btn_analyze.click(fn=analyze_api, inputs=inp_analyze, outputs=out_analyze, api_name="analyze")
        
        # 變速變調
        inp_trans = [
            gr.Audio(type="filepath", label="Input Audio"), 
            gr.Slider(-24, 24, step=1, label="Semitones"), 
            gr.Number(label="Target BPM")
        ]
        out_trans = gr.File(label="Transformed Audio")
        btn_trans = gr.Button("Transform")
        btn_trans.click(fn=transform_api, inputs=inp_trans, outputs=out_trans, api_name="transform")
        
        # 人聲分離
        inp_vocals = gr.Audio(type="filepath", label="Input Audio")
        out_vocals = gr.File(label="Vocals & Accompaniment Zip")
        btn_vocals = gr.Button("Separate Vocals")
        btn_vocals.click(fn=separate_vocals_api, inputs=inp_vocals, outputs=out_vocals, api_name="separate_vocals")
        
        # 樂器分離
        inp_stems = [
            gr.Audio(type="filepath", label="Input Audio"), 
            gr.CheckboxGroup(choices=["vocals", "drums", "bass", "guitar", "piano", "other"], label="Stems"), 
            gr.Dropdown(choices=["standard", "high", "highest"], label="Quality")
        ]
        out_stems = gr.File(label="Stems Zip")
        btn_stems = gr.Button("Separate Instruments")
        btn_stems.click(fn=separate_instruments_api, inputs=inp_stems, outputs=out_stems, api_name="separate_instruments")
        
        # YouTube 下載
        inp_yt = gr.Textbox(label="YouTube URL")
        out_yt = gr.File(label="Downloaded MP3")
        btn_yt = gr.Button("Download YT")
        btn_yt.click(fn=youtube_download_api, inputs=inp_yt, outputs=out_yt, api_name="youtube")

if __name__ == "__main__":
    demo.queue().launch(server_name="0.0.0.0", server_port=7860)
