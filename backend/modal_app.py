import os
import io
import shutil
import zipfile
import subprocess
from pathlib import Path
import modal
import fastapi

# 1. 定義 Modal 容器環境 (Debian + GCC + FFmpeg + PyTorch + Demucs)
image = (
    modal.Image.debian_slim(python_version="3.10")
    .apt_install("ffmpeg", "git", "gcc", "g++")
    .pip_install(
        "torch==2.0.1", 
        "torchaudio==2.0.2", 
        "numpy==1.26.4",
        "fastapi[standard]",
        "git+https://github.com/facebookresearch/demucs#egg=demucs",
        extra_index_url="https://download.pytorch.org/whl/cu118"
    )
    # 直接在建置時執行 python 一行指令下載模型權重，永久烘焙入環境中
    .run_commands(
        "python3 -c \"import demucs.api; demucs.api.Separator(model='htdemucs'); demucs.api.Separator(model='htdemucs_6s')\""
    )
)

app = modal.App("music-tools-gpu", image=image)

# 3. 輔助函式：使用 ffmpeg 將 wav 轉成 320k mp3
def convert_to_mp3(input_path: Path, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg",
        "-nostdin",
        "-y",
        "-i",
        str(input_path),
        "-vn",
        "-codec:a",
        "libmp3lame",
        "-b:a",
        "320k",
        str(output_path),
    ]
    subprocess.run(command, check=True, capture_output=True, stdin=subprocess.DEVNULL)

# 4. 輔助函式：將多個音軌混合並轉成 320k mp3
def mix_to_mp3(input_paths: list[Path], output_path: Path) -> None:
    if not input_paths:
        raise ValueError("At least one input is required for mixing")
    if len(input_paths) == 1:
        convert_to_mp3(input_paths[0], output_path)
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = ["ffmpeg", "-nostdin", "-y"]
    for input_path in input_paths:
        command.extend(["-i", str(input_path)])
    command.extend(
        [
            "-filter_complex",
            f"amix=inputs={len(input_paths)}:duration=longest:normalize=0",
            "-vn",
            "-codec:a",
            "libmp3lame",
            "-b:a",
            "320k",
            str(output_path),
        ]
    )
    subprocess.run(command, check=True, capture_output=True, stdin=subprocess.DEVNULL)

# 5. 核心 GPU 函式：人聲伴奏分離 (htdemucs)
@app.function(
    gpu="a10g", 
    timeout=120, 
    max_containers=1, 
    min_containers=0
)
def separate_vocals_gpu(file_bytes: bytes, filename: str) -> bytes:
    import demucs.api
    import torch

    # 建立臨時工作目錄
    temp_dir = Path("/tmp/vocals")
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True, exist_ok=True)

    input_path = temp_dir / filename
    input_path.write_bytes(file_bytes)

    # 執行分離 (htdemucs)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    separator = demucs.api.Separator(model="htdemucs", device=device, shifts=0)
    origin, separated = separator.separate_audio_file(str(input_path))

    # 儲存分離的 wav 檔
    vocals_wav = temp_dir / "vocals.wav"
    accompaniment_wav = temp_dir / "accompaniment.wav"
    
    # 儲存 vocals 軌
    demucs.api.save_audio(separated["vocals"], str(vocals_wav), samplerate=separator.samplerate)
    
    # 混音其餘軌道作為伴奏 (drums + bass + other)
    acc_stems = [separated[stem] for stem in ["drums", "bass", "other"] if stem in separated]
    acc_tensor = sum(acc_stems)
    demucs.api.save_audio(acc_tensor, str(accompaniment_wav), samplerate=separator.samplerate)

    # 轉檔並封裝成 ZIP
    zip_path = temp_dir / "output.zip"
    final_dir = temp_dir / "converted"
    final_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, wav_path in [("vocals", vocals_wav), ("accompaniment", accompaniment_wav)]:
            mp3_path = final_dir / f"{name}.mp3"
            convert_to_mp3(wav_path, mp3_path)
            archive.write(mp3_path, arcname=mp3_path.name)

    res_bytes = zip_path.read_bytes()
    # 清理臨時檔案
    shutil.rmtree(temp_dir)
    return res_bytes

# 6. 核心 GPU 函式：樂器分離 (htdemucs_6s)
@app.function(
    gpu="a10g", 
    timeout=180, 
    max_containers=1, 
    min_containers=0
)
def separate_instruments_gpu(file_bytes: bytes, filename: str, selected_stems: list[str], shifts: int = 0) -> bytes:
    import demucs.api
    import torch

    temp_dir = Path("/tmp/instruments")
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True, exist_ok=True)

    input_path = temp_dir / filename
    input_path.write_bytes(file_bytes)

    # 執行分離 (htdemucs_6s)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    separator = demucs.api.Separator(model="htdemucs_6s", device=device, shifts=shifts)
    origin, separated = separator.separate_audio_file(str(input_path))

    # 儲存所有 6 個軌道為 wav 檔
    MODEL_STEMS_6S = ["vocals", "drums", "bass", "guitar", "piano", "other"]
    stems_wav: dict[str, Path] = {}
    for stem_name in MODEL_STEMS_6S:
        stem_wav = temp_dir / f"{stem_name}.wav"
        demucs.api.save_audio(separated[stem_name], str(stem_wav), samplerate=separator.samplerate)
        stems_wav[stem_name] = stem_wav

    # 處理選取聲部與其餘混音
    zip_path = temp_dir / "output.zip"
    final_dir = temp_dir / "converted"
    final_dir.mkdir(parents=True, exist_ok=True)

    selected = [s for s in selected_stems if s in MODEL_STEMS_6S]
    selected_paths = {stem_name: stems_wav[stem_name] for stem_name in selected}
    remainder_paths = [path for stem_name, path in stems_wav.items() if stem_name not in selected]
    remainder_name = "remaining" if "other" in selected else "other"

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        # 轉換選定的聲部
        for stem_name, wav_path in selected_paths.items():
            mp3_path = final_dir / f"{stem_name}.mp3"
            convert_to_mp3(wav_path, mp3_path)
            archive.write(mp3_path, arcname=mp3_path.name)
        # 混合並轉換未選定的聲部
        if remainder_paths:
            mix_mp3_path = final_dir / f"{remainder_name}.mp3"
            mix_to_mp3(remainder_paths, mix_mp3_path)
            archive.write(mix_mp3_path, arcname=mix_mp3_path.name)

    res_bytes = zip_path.read_bytes()
    shutil.rmtree(temp_dir)
    return res_bytes

# 7. Web Endpoints (提供 FastAPI 同步呼叫)
@app.function(secrets=[modal.Secret.from_name("music-tools-secrets")])
@modal.fastapi_endpoint(method="POST")
async def separate_vocals_endpoint(file: fastapi.UploadFile = fastapi.File(...), filename: str = "audio.mp3", authorization: str = fastapi.Header(None)):
    correct_key = os.environ.get("MTS_ENGINE_SECRET")
    if not authorization or authorization != f"Bearer {correct_key}":
        return fastapi.Response(content="Unauthorized", status_code=401)

    file_bytes = await file.read()
    zip_data = await separate_vocals_gpu.remote.aio(file_bytes, filename)
    return fastapi.Response(
        content=zip_data,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=vocals.zip"}
    )

@app.function(secrets=[modal.Secret.from_name("music-tools-secrets")])
@modal.fastapi_endpoint(method="POST")
async def separate_instruments_endpoint(stems: str, file: fastapi.UploadFile = fastapi.File(...), filename: str = "audio.mp3", shifts: int = 0, authorization: str = fastapi.Header(None)):
    correct_key = os.environ.get("MTS_ENGINE_SECRET")
    if not authorization or authorization != f"Bearer {correct_key}":
        return fastapi.Response(content="Unauthorized", status_code=401)

    file_bytes = await file.read()
    # stems 透過 HTTP 傳輸是以逗號分隔的字串，例如 "vocals,drums"
    stems_list = [s.strip() for s in stems.split(",") if s.strip()]
    zip_data = await separate_instruments_gpu.remote.aio(file_bytes, filename, stems_list, shifts)
    return fastapi.Response(
        content=zip_data,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=instruments.zip"}
    )
