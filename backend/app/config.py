from pathlib import Path
import os


PROJECT_ROOT = Path(__file__).resolve().parents[2]
STORAGE_ROOT = Path(os.getenv("MUSIC_TOOLS_STORAGE", PROJECT_ROOT / "storage"))
UPLOADS_DIR = STORAGE_ROOT / "uploads"
OUTPUTS_DIR = STORAGE_ROOT / "outputs"
TEMP_DIR = STORAGE_ROOT / "temp"

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
QUEUE_NAME = os.getenv("QUEUE_NAME", "music-tools")
DEMUCS_DEVICE = os.getenv("DEMUCS_DEVICE", "cpu")

MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(500 * 1024 * 1024)))
