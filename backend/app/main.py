from pathlib import Path
import os

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from rq.exceptions import NoSuchJobError

from .config import MAX_UPLOAD_BYTES, OUTPUTS_DIR, UPLOADS_DIR
from .analyze import analyze_audio, read_analysis, write_analysis
from .jobs import enqueue_audio_transform, enqueue_instrument_separation, enqueue_vocal_separation, enqueue_wav_conversion, fetch_job, job_payload, queue_overview, list_all_jobs, delete_job_and_files, clean_expired_jobs
from .schemas import AudioAnalysisResponse, JobResponse
from .storage import analysis_path, ensure_storage_dirs, new_job_id, upload_path, uploaded_file

app = FastAPI(title="Music Tools API")
SUPPORTED_SEPARATION_EXTENSIONS = {".wav", ".mp3", ".flac", ".m4a", ".aac"}
SUPPORTED_AUDIO_EXTENSIONS = SUPPORTED_SEPARATION_EXTENSIONS
SUPPORTED_INSTRUMENT_STEMS = {"vocals", "drums", "bass", "guitar", "piano", "other"}
SUPPORTED_QUALITY_MODES = {"standard", "high", "highest"}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer(auto_error=False)

def verify_api_key(request: Request, credentials: HTTPAuthorizationCredentials = Depends(security)) -> None:
    correct_key = os.getenv("MTS_ENGINE_SECRET")
    if not correct_key:
        raise HTTPException(status_code=500, detail="Server API Key is not configured")
    
    token = None
    if credentials:
        token = credentials.credentials
    else:
        token = request.query_params.get("token")
        
    if not token or token != correct_key:
        raise HTTPException(status_code=401, detail="Invalid API Key")


@app.on_event("startup")
def startup() -> None:
    ensure_storage_dirs()


@app.get("/api/health")
def health() -> dict[str, object]:
    return {"ok": True, "queue": queue_overview()}


@app.post("/api/jobs/upload", response_model=JobResponse, dependencies=[Depends(verify_api_key)])
async def create_upload_job(file: UploadFile = File(...)) -> dict[str, object]:
    if not file.filename or not file.filename.lower().endswith(".wav"):
        raise HTTPException(status_code=400, detail="Only .wav files are supported in v1")

    job_id = new_job_id()
    target = upload_path(job_id, file.filename)
    target.parent.mkdir(parents=True, exist_ok=True)

    size = 0
    with target.open("wb") as output:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                target.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="Uploaded file is too large")
            output.write(chunk)

    job = enqueue_wav_conversion(job_id, target, file.filename)
    return job_payload(job)


@app.post("/api/audio/analyze", response_model=AudioAnalysisResponse, dependencies=[Depends(verify_api_key)])
async def analyze_uploaded_audio(file: UploadFile = File(...)) -> dict[str, object]:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in SUPPORTED_AUDIO_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Supported formats: wav, mp3, flac, m4a, aac")

    file_id = new_job_id()
    target = upload_path(file_id, file.filename or "audio")
    target.parent.mkdir(parents=True, exist_ok=True)

    size = 0
    with target.open("wb") as output:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                target.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="Uploaded file is too large")
            output.write(chunk)

    try:
        analysis = analyze_audio(target)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Could not analyze audio: {exc}") from exc

    payload = {"file_id": file_id, "filename": file.filename or target.name, **analysis}
    write_analysis(analysis_path(file_id), payload)
    return payload


@app.post("/api/jobs/transform", response_model=JobResponse, dependencies=[Depends(verify_api_key)])
def create_transform_job(file_id: str = Form(...), semitones: int = Form(0), target_bpm: float = Form(...)) -> dict[str, object]:
    source = uploaded_file(file_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Analyzed file not found")
    if semitones < -24 or semitones > 24:
        raise HTTPException(status_code=400, detail="Semitones must be between -24 and 24")
    if target_bpm <= 0:
        raise HTTPException(status_code=400, detail="Target BPM must be greater than 0")

    try:
        analysis = read_analysis(analysis_path(file_id))
    except Exception:
        analysis = analyze_audio(source)

    source_bpm = float(analysis.get("bpm") or 0)
    if source_bpm <= 0:
        raise HTTPException(status_code=422, detail="Could not determine source BPM")

    job_id = new_job_id()
    job = enqueue_audio_transform(job_id, source, source.name, semitones, source_bpm, target_bpm)
    return job_payload(job)


@app.post("/api/jobs/separate-vocals", response_model=JobResponse, dependencies=[Depends(verify_api_key)])
async def create_vocal_separation_job(file: UploadFile = File(...)) -> dict[str, object]:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in SUPPORTED_SEPARATION_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Supported formats: wav, mp3, flac, m4a, aac")

    job_id = new_job_id()
    target = upload_path(job_id, file.filename or "audio")
    target.parent.mkdir(parents=True, exist_ok=True)

    size = 0
    with target.open("wb") as output:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                target.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="Uploaded file is too large")
            output.write(chunk)

    job = enqueue_vocal_separation(job_id, target, file.filename or "audio")
    return job_payload(job)


@app.post("/api/jobs/separate-instruments", response_model=JobResponse, dependencies=[Depends(verify_api_key)])
async def create_instrument_separation_job(
    file: UploadFile = File(...),
    stems: list[str] = Form(...),
    quality: str = Form("standard"),
) -> dict[str, object]:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in SUPPORTED_SEPARATION_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Supported formats: wav, mp3, flac, m4a, aac")

    selected_stems = list(dict.fromkeys(stem for stem in stems if stem in SUPPORTED_INSTRUMENT_STEMS))
    if not selected_stems:
        raise HTTPException(status_code=400, detail="Select at least one stem: vocals, drums, bass, guitar, piano, other")
    if quality not in SUPPORTED_QUALITY_MODES:
        raise HTTPException(status_code=400, detail="Quality must be standard, high, or highest")

    job_id = new_job_id()
    target = upload_path(job_id, file.filename or "audio")
    target.parent.mkdir(parents=True, exist_ok=True)

    size = 0
    with target.open("wb") as output:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                target.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="Uploaded file is too large")
            output.write(chunk)

    job = enqueue_instrument_separation(job_id, target, file.filename or "audio", selected_stems, quality)
    return job_payload(job)


@app.get("/api/jobs", response_model=list[JobResponse], dependencies=[Depends(verify_api_key)])
def get_all_jobs(background_tasks: BackgroundTasks) -> list[dict[str, object]]:
    background_tasks.add_task(clean_expired_jobs, UPLOADS_DIR, OUTPUTS_DIR)
    return list_all_jobs()


@app.delete("/api/jobs/{job_id}", status_code=204, dependencies=[Depends(verify_api_key)])
def delete_job(job_id: str) -> None:
    delete_job_and_files(job_id, UPLOADS_DIR, OUTPUTS_DIR)


@app.get("/api/jobs/{job_id}", response_model=JobResponse, dependencies=[Depends(verify_api_key)])
def get_job(job_id: str) -> dict[str, object]:
    try:
        job = fetch_job(job_id)
    except NoSuchJobError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc
    return job_payload(job)


@app.get("/api/jobs/{job_id}/download", dependencies=[Depends(verify_api_key)])
def download_job_output(job_id: str) -> FileResponse:
    try:
        job = fetch_job(job_id)
    except NoSuchJobError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc

    payload = job_payload(job)
    if payload["status"] != "finished":
        raise HTTPException(status_code=409, detail="Job is not finished yet")

    output_path = job.meta.get("output_path")
    if not output_path:
        raise HTTPException(status_code=404, detail="Output file not found")

    path = Path(output_path)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Output file not found")

    return FileResponse(path, media_type=job.meta.get("output_type") or "application/octet-stream", filename=job.meta.get("output_name") or path.name)
