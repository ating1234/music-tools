import torch
import demucs.api
import torchaudio
import zipfile
from pathlib import Path
from collections.abc import Callable

from .audio import convert_to_mp3, mix_to_mp3

INSTRUMENT_STEMS = ["vocals", "drums", "bass", "guitar", "piano", "other"]
MODEL_STEMS_6S = INSTRUMENT_STEMS

ProgressCallback = Callable[[int], None]

def _zip_mp3s(output_path: Path, source_paths: dict[str, Path], mixes: dict[str, list[Path]] | None = None) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    final_dir = output_path.parent / output_path.stem
    final_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for stem_name, source_path in source_paths.items():
            final_path = final_dir / f"{stem_name}.mp3"
            convert_to_mp3(source_path, final_path)
            archive.write(final_path, arcname=final_path.name)
        for stem_name, mix_paths in (mixes or {}).items():
            final_path = final_dir / f"{stem_name}.mp3"
            mix_to_mp3(mix_paths, final_path)
            archive.write(final_path, arcname=final_path.name)


def separate_vocals(input_path: Path, work_dir: Path, output_path: Path, progress_callback: ProgressCallback | None = None) -> None:
    if progress_callback:
        progress_callback(10)

    # 檢查是否啟用 Modal.com 加速後端
    from .config import MODAL_VOCALS_URL
    if MODAL_VOCALS_URL:
        print("【Music-Tools】偵測到 MODAL_VOCALS_URL，正在發送請求至 Modal GPU 加速端...")
        try:
            import requests
            if progress_callback:
                progress_callback(30)

            # 讀取本地暫存檔與金鑰，傳送至 Modal GPU 運算
            import os
            api_key = os.getenv("MTS_ENGINE_SECRET", "")
            headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
            with open(input_path, "rb") as f:
                files = {"file": (input_path.name, f, "audio/mpeg")}
                response = requests.post(MODAL_VOCALS_URL, files=files, headers=headers, params={"filename": input_path.name})

            if progress_callback:
                progress_callback(85)

            if response.status_code != 200:
                raise RuntimeError(f"Modal API 回傳錯誤 ({response.status_code}): {response.text}")

            # 將 Modal 回傳的 ZIP 二進位資料寫入輸出路徑
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(response.content)

            if progress_callback:
                progress_callback(100)
            return
        except Exception as e:
            raise RuntimeError(f"透過 Modal 進行人聲分離失敗，原因: {str(e)}")

    # 備用方案 (Fallback)：使用本地設備進行分離
    print("【Music-Tools】未偵測到 MODAL_VOCALS_URL，降級走本地 CPU 分離...")
    try:
        import demucs.api
        
        device = "cuda" if torch.cuda.is_available() else "cpu"
        separator = demucs.api.Separator(
            model="htdemucs",
            device=device,
            shifts=0
        )
        
        if progress_callback:
            progress_callback(40)

        origin, separated = separator.separate_audio_file(str(input_path))
        
        if progress_callback:
            progress_callback(80)

        work_dir.mkdir(parents=True, exist_ok=True)
        vocals_wav = work_dir / "vocals.wav"
        accompaniment_wav = work_dir / "accompaniment.wav"
        
        demucs.api.save_audio(separated["vocals"], str(vocals_wav), samplerate=separator.samplerate)
        
        accompaniment_stems = [separated[stem] for stem in ["drums", "bass", "other"] if stem in separated]
        acc_tensor = sum(accompaniment_stems)
        demucs.api.save_audio(acc_tensor, str(accompaniment_wav), samplerate=separator.samplerate)
        
        if progress_callback:
            progress_callback(90)

        _zip_mp3s(output_path, {
            "vocals": vocals_wav,
            "accompaniment": accompaniment_wav
        })
        
        if progress_callback:
            progress_callback(100)
            
    except Exception as e:
        raise RuntimeError(f"本地人聲分離失敗，原因: {str(e)}")


def separate_instruments(
    input_path: Path,
    work_dir: Path,
    output_path: Path,
    selected_stems: list[str],
    shifts: int = 0,
    progress_callback: ProgressCallback | None = None,
) -> None:
    selected = [stem for stem in selected_stems if stem in INSTRUMENT_STEMS]
    if not selected:
        raise ValueError("At least one instrument stem must be selected")

    if progress_callback:
        progress_callback(10)

    # 檢查是否啟用 Modal.com 加速後端
    from .config import MODAL_INSTRUMENTS_URL
    if MODAL_INSTRUMENTS_URL:
        print("【Music-Tools】偵測到 MODAL_INSTRUMENTS_URL，正在發送請求至 Modal GPU 加速端...")
        try:
            import requests
            if progress_callback:
                progress_callback(30)

            # 讀取本地暫存檔與金鑰，傳送至 Modal GPU 運算
            import os
            api_key = os.getenv("MTS_ENGINE_SECRET", "")
            headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
            with open(input_path, "rb") as f:
                files = {"file": (input_path.name, f, "audio/mpeg")}
                params = {
                    "stems": ",".join(selected),
                    "filename": input_path.name,
                    "shifts": shifts
                }
                response = requests.post(MODAL_INSTRUMENTS_URL, files=files, headers=headers, params=params)

            if progress_callback:
                progress_callback(85)

            if response.status_code != 200:
                raise RuntimeError(f"Modal API 回傳錯誤 ({response.status_code}): {response.text}")

            # 將 Modal 回傳的 ZIP 二進位資料寫入輸出路徑
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(response.content)

            if progress_callback:
                progress_callback(100)
            return
        except Exception as e:
            raise RuntimeError(f"透過 Modal 進行樂器分離失敗，原因: {str(e)}")

    # 備用方案 (Fallback)：使用本地設備進行分離
    print("【Music-Tools】未偵測到 MODAL_INSTRUMENTS_URL，降級走本地 CPU 分離...")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    separator = demucs.api.Separator(
        model="htdemucs_6s",
        device=device,
        shifts=shifts
    )
    
    if progress_callback:
        progress_callback(30)

    origin, separated = separator.separate_audio_file(str(input_path))
    
    if progress_callback:
        progress_callback(80)

    work_dir.mkdir(parents=True, exist_ok=True)
    stems: dict[str, Path] = {}
    for stem_name in MODEL_STEMS_6S:
        stem_wav = work_dir / f"{stem_name}.wav"
        demucs.api.save_audio(separated[stem_name], str(stem_wav), samplerate=separator.samplerate)
        stems[stem_name] = stem_wav

    if progress_callback:
        progress_callback(88)

    selected_paths = {stem_name: stems[stem_name] for stem_name in selected}
    remainder_paths = [path for stem_name, path in stems.items() if stem_name not in selected]
    remainder_name = "remaining" if "other" in selected else "other"
    mixes = {remainder_name: remainder_paths} if remainder_paths else None
    
    _zip_mp3s(output_path, selected_paths, mixes)
    
    if progress_callback:
        progress_callback(100)
