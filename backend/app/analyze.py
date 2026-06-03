from pathlib import Path
import json

import librosa
import numpy as np


NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
MAJOR_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


def analyze_audio(path: Path) -> dict[str, object]:
    y, sr = librosa.load(path, mono=True, duration=300)
    if y.size == 0:
        raise ValueError("Audio file is empty")

    bpm = float(librosa.feature.tempo(y=y, sr=sr)[0])
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    chroma_mean = chroma.mean(axis=1)
    tonic, mode = _estimate_key(chroma_mean)
    key = f"{NOTES[tonic]} {mode}"

    return {
        "key": key,
        "tonic": NOTES[tonic],
        "mode": mode,
        "bpm": round(bpm, 1),
    }


def write_analysis(path: Path, analysis: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(analysis), encoding="utf-8")


def read_analysis(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _estimate_key(chroma_mean: np.ndarray) -> tuple[int, str]:
    if np.allclose(chroma_mean.sum(), 0):
        return 0, "major"

    values = (chroma_mean - chroma_mean.mean()) / (chroma_mean.std() or 1)
    best_score = -np.inf
    best_key = (0, "major")

    for tonic in range(12):
        major = np.roll(MAJOR_PROFILE, tonic)
        minor = np.roll(MINOR_PROFILE, tonic)
        for mode, profile in (("major", major), ("minor", minor)):
            normalized = (profile - profile.mean()) / profile.std()
            score = float(np.dot(values, normalized))
            if score > best_score:
                best_score = score
                best_key = (tonic, mode)

    return best_key
