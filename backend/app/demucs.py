from pathlib import Path
import os
import re
import subprocess
import sys
import zipfile
from collections.abc import Callable

import certifi

from .config import DEMUCS_DEVICE
from .audio import convert_to_mp3, mix_to_mp3


INSTRUMENT_STEMS = ["vocals", "drums", "bass", "guitar", "piano", "other"]
MODEL_STEMS_6S = INSTRUMENT_STEMS


ProgressCallback = Callable[[int], None]


def _run_demucs(
    input_path: Path,
    work_dir: Path,
    model: str,
    extra_args: list[str] | None = None,
    progress_callback: ProgressCallback | None = None,
) -> None:
    work_dir.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        "-m",
        "demucs.separate",
        "-n",
        model,
        "-d",
        DEMUCS_DEVICE,
        "-o",
        str(work_dir),
    ]
    if extra_args:
        command.extend(extra_args)
    command.append(str(input_path))

    env = os.environ.copy()
    env.setdefault("SSL_CERT_FILE", certifi.where())
    env.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
    process = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
        bufsize=1,
    )
    output = ""
    last_progress = 0
    if process.stdout is not None:
        while True:
            char = process.stdout.read(1)
            if char == "" and process.poll() is not None:
                break
            if not char:
                continue
            output = (output + char)[-4000:]
            match = re.search(r"(\d{1,3})%", output[-120:])
            if match and progress_callback:
                percent = min(100, int(match.group(1)))
                mapped = min(85, 10 + int(percent * 0.75))
                if mapped > last_progress:
                    last_progress = mapped
                    progress_callback(mapped)

    return_code = process.wait()
    if return_code != 0:
        raise RuntimeError(f"Demucs failed: {output[-4000:]}")


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
    _run_demucs(input_path, work_dir, "htdemucs_ft", ["--two-stems", "vocals"], progress_callback)
    if progress_callback:
        progress_callback(88)

    vocals = next(work_dir.rglob("vocals.wav"), None)
    accompaniment = next(work_dir.rglob("no_vocals.wav"), None)
    if vocals is None or accompaniment is None:
        raise RuntimeError("Demucs completed but expected output files were not found")

    _zip_mp3s(output_path, {"vocals": vocals, "accompaniment": accompaniment})
    if progress_callback:
        progress_callback(96)


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

    extra_args = ["--shifts", str(shifts)] if shifts > 0 else None
    _run_demucs(input_path, work_dir, "htdemucs_6s", extra_args=extra_args, progress_callback=progress_callback)
    if progress_callback:
        progress_callback(88)

    stems: dict[str, Path] = {}
    for stem_name in MODEL_STEMS_6S:
        stem_path = next(work_dir.rglob(f"{stem_name}.wav"), None)
        if stem_path is None:
            raise RuntimeError(f"Demucs completed but {stem_name}.wav was not found")
        stems[stem_name] = stem_path

    selected_paths = {stem_name: stems[stem_name] for stem_name in selected}
    remainder_paths = [path for stem_name, path in stems.items() if stem_name not in selected]
    remainder_name = "remaining" if "other" in selected else "other"
    mixes = {remainder_name: remainder_paths} if remainder_paths else None
    _zip_mp3s(output_path, selected_paths, mixes)
    if progress_callback:
        progress_callback(96)
