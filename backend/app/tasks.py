from pathlib import Path
import shutil

from rq import get_current_job

from .audio import convert_to_mp3, transform_audio
from .demucs import separate_instruments, separate_vocals
from .storage import output_dir, safe_filename, temp_dir

def _set_meta(**values: object) -> None:
    job = get_current_job()
    if job is None:
        return
    job.meta.update(values)
    job.save_meta()


def convert_wav_to_mp3(input_path: str, original_name: str) -> str:
    job = get_current_job()
    if job is None:
        raise RuntimeError("This task must run inside an RQ worker")

    source = Path(input_path)
    output_name = f"{Path(safe_filename(original_name)).stem or 'audio'}.mp3"
    target = output_dir(job.id) / output_name

    _set_meta(step="converting", progress=25)
    convert_to_mp3(source, target)
    _set_meta(step="finished", progress=100, output_path=str(target), output_name=output_name, output_type="audio/mpeg")
    return str(target)



def separate_vocals_job(input_path: str, original_name: str) -> str:
    job = get_current_job()
    if job is None:
        raise RuntimeError("This task must run inside an RQ worker")

    source = Path(input_path)
    output_name = f"{Path(safe_filename(original_name)).stem or 'separated'}-vocals.zip"
    target = output_dir(job.id) / output_name

    _set_meta(step="separating", progress=10)
    separate_vocals(source, temp_dir(job.id) / "demucs", target, lambda progress: _set_meta(step="separating", progress=progress))
    _set_meta(step="finished", progress=100, output_path=str(target), output_name=output_name, output_type="application/zip")
    return str(target)


QUALITY_SHIFTS = {"standard": 0, "high": 2, "highest": 4}


def separate_instruments_job(input_path: str, original_name: str, selected_stems: list[str], quality: str = "standard") -> str:
    job = get_current_job()
    if job is None:
        raise RuntimeError("This task must run inside an RQ worker")

    source = Path(input_path)
    output_name = f"{Path(safe_filename(original_name)).stem or 'separated'}-instruments.zip"
    target = output_dir(job.id) / output_name

    shifts = QUALITY_SHIFTS.get(quality, 0)
    _set_meta(step="separating", progress=10, selected_stems=selected_stems, quality=quality, shifts=shifts)
    separate_instruments(
        source,
        temp_dir(job.id) / "demucs-instruments",
        target,
        selected_stems,
        shifts,
        lambda progress: _set_meta(step="separating", progress=progress),
    )
    _set_meta(step="finished", progress=100, output_path=str(target), output_name=output_name, output_type="application/zip")
    return str(target)


def transform_audio_job(input_path: str, original_name: str, semitones: int, source_bpm: float, target_bpm: float) -> str:
    job = get_current_job()
    if job is None:
        raise RuntimeError("This task must run inside an RQ worker")

    source = Path(input_path)
    output_name = f"{Path(safe_filename(original_name)).stem or 'audio'}-transformed.mp3"
    target = output_dir(job.id) / output_name

    _set_meta(step="transforming", progress=20)
    transform_audio(source, target, semitones, source_bpm, target_bpm, temp_dir(job.id) / "transform")
    _set_meta(step="finished", progress=100, output_path=str(target), output_name=output_name, output_type="audio/mpeg")
    return str(target)
