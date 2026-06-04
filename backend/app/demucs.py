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

    from gradio_client import Client
    
    if progress_callback:
        progress_callback(20)

    try:
        # 連線至公開的免費 ZeroGPU 空間（abidlabs/music-separation）
        client = Client("abidlabs/music-separation")
        
        if progress_callback:
            progress_callback(40)

        # 執行預測。Gradio Client 會自動將 input_path 上傳並等待 A100 GPU 運算完成
        # 對方接口會返回已下載到本機暫存目錄的 (vocals_path, no_vocals_path)
        result = client.predict(
            audio=str(input_path),
            api_name="/predict"
        )
        
        vocals_wav_path, accompaniment_wav_path = result
        
        if progress_callback:
            progress_callback(80)

        # 轉為 MP3 並壓縮成 ZIP
        # 因為對方返回的已經是本地臨時 WAV 檔案路徑，我們可以直接使用它們進行壓縮
        _zip_mp3s(output_path, {
            "vocals": Path(vocals_wav_path), 
            "accompaniment": Path(accompaniment_wav_path)
        })
        
        if progress_callback:
            progress_callback(96)

    except Exception as e:
        raise RuntimeError(f"透過外部 GPU 分離人聲失敗，請改用本地分離。錯誤原因: {str(e)}")


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

    device = "cuda" if torch.cuda.is_available() else "cpu"
    
    # 建立 Separator (使用 htdemucs_6s 模型)
    separator = demucs.api.Separator(
        model="htdemucs_6s",
        device=device,
        shifts=shifts
    )
    
    if progress_callback:
        progress_callback(30)

    # 執行分離
    origin, separated = separator.separate_audio_file(str(input_path))
    
    if progress_callback:
        progress_callback(80)

    # 儲存所有 6 個軌道到工作目錄
    work_dir.mkdir(parents=True, exist_ok=True)
    stems: dict[str, Path] = {}
    for stem_name in MODEL_STEMS_6S:
        stem_wav = work_dir / f"{stem_name}.wav"
        demucs.api.save_audio(separated[stem_name], str(stem_wav), samplerate=separator.samplerate)
        stems[stem_name] = stem_wav

    if progress_callback:
        progress_callback(88)

    # 處理選取的聲部與其餘聲部的混音
    selected_paths = {stem_name: stems[stem_name] for stem_name in selected}
    remainder_paths = [path for stem_name, path in stems.items() if stem_name not in selected]
    remainder_name = "remaining" if "other" in selected else "other"
    mixes = {remainder_name: remainder_paths} if remainder_paths else None
    
    # 轉為 MP3 並壓縮成 ZIP
    _zip_mp3s(output_path, selected_paths, mixes)
    
    if progress_callback:
        progress_callback(96)
