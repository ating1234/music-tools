from pathlib import Path
import re
from uuid import uuid4

from .config import OUTPUTS_DIR, TEMP_DIR, UPLOADS_DIR


SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def ensure_storage_dirs() -> None:
    for directory in (UPLOADS_DIR, OUTPUTS_DIR, TEMP_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def safe_filename(name: str) -> str:
    base = Path(name).name.strip() or "audio"
    sanitized = SAFE_NAME_RE.sub("_", base)
    return sanitized[:180] or "audio"


def new_job_id() -> str:
    return uuid4().hex


def upload_path(job_id: str, original_name: str) -> Path:
    return UPLOADS_DIR / job_id / safe_filename(original_name)


def output_dir(job_id: str) -> Path:
    return OUTPUTS_DIR / job_id


def temp_dir(job_id: str) -> Path:
    return TEMP_DIR / job_id


def analysis_path(file_id: str) -> Path:
    return UPLOADS_DIR / file_id / "analysis.json"


def uploaded_file(file_id: str) -> Path | None:
    directory = UPLOADS_DIR / file_id
    if not directory.exists():
        return None
    for path in directory.iterdir():
        if path.is_file() and path.name != "analysis.json":
            return path
    return None
