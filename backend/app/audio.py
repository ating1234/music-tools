from pathlib import Path
import subprocess


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
    subprocess.run(command, check=True, capture_output=True, text=True, stdin=subprocess.DEVNULL)


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
    subprocess.run(command, check=True, capture_output=True, text=True, stdin=subprocess.DEVNULL)


def transform_audio(input_path: Path, output_path: Path, semitones: int, source_bpm: float, target_bpm: float, work_dir: Path) -> None:
    work_dir.mkdir(parents=True, exist_ok=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    source_wav = work_dir / "source.wav"
    transformed_wav = work_dir / "transformed.wav"

    subprocess.run(
        ["ffmpeg", "-nostdin", "-y", "-i", str(input_path), "-vn", str(source_wav)],
        check=True,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
    )

    command = ["rubberband", "-3", "-F"]
    if semitones != 0:
        command.extend(["-p", str(semitones)])
    if target_bpm > 0 and source_bpm > 0 and abs(target_bpm - source_bpm) >= 0.1:
        command.extend(["-T", f"{source_bpm}:{target_bpm}"])
    if len(command) == 3:
        convert_to_mp3(input_path, output_path)
        return

    command.extend([str(source_wav), str(transformed_wav)])
    subprocess.run(command, check=True, capture_output=True, text=True, stdin=subprocess.DEVNULL)
    convert_to_mp3(transformed_wav, output_path)
