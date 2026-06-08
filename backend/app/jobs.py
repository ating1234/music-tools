from pathlib import Path
from typing import Any

from redis import Redis
from rq import Queue
from rq.job import Job
from rq.registry import FailedJobRegistry, FinishedJobRegistry, StartedJobRegistry

from .config import QUEUE_NAME, REDIS_URL


redis_conn = Redis.from_url(REDIS_URL)
queue = Queue(QUEUE_NAME, connection=redis_conn)


def enqueue_wav_conversion(job_id: str, input_path: Path, original_name: str) -> Job:
    return queue.enqueue(
        "app.tasks.convert_wav_to_mp3",
        str(input_path),
        original_name,
        job_id=job_id,
        job_timeout="2h",
        result_ttl=86400,
        failure_ttl=86400,
        meta={"kind": "wav_to_mp3", "step": "queued", "progress": 0},
    )



def enqueue_vocal_separation(job_id: str, input_path: Path, original_name: str) -> Job:
    return queue.enqueue(
        "app.tasks.separate_vocals_job",
        str(input_path),
        original_name,
        job_id=job_id,
        job_timeout="6h",
        result_ttl=86400,
        failure_ttl=86400,
        meta={"kind": "separate_vocals", "step": "queued", "progress": 0},
    )


def enqueue_instrument_separation(job_id: str, input_path: Path, original_name: str, selected_stems: list[str], quality: str) -> Job:
    return queue.enqueue(
        "app.tasks.separate_instruments_job",
        str(input_path),
        original_name,
        selected_stems,
        quality,
        job_id=job_id,
        job_timeout="8h",
        result_ttl=86400,
        failure_ttl=86400,
        meta={"kind": "separate_instruments", "step": "queued", "progress": 0, "selected_stems": selected_stems, "quality": quality},
    )


def enqueue_audio_transform(job_id: str, input_path: Path, original_name: str, semitones: int, source_bpm: float, target_bpm: float) -> Job:
    return queue.enqueue(
        "app.tasks.transform_audio_job",
        str(input_path),
        original_name,
        semitones,
        source_bpm,
        target_bpm,
        job_id=job_id,
        job_timeout="2h",
        result_ttl=86400,
        failure_ttl=86400,
        meta={"kind": "transform_audio", "step": "queued", "progress": 0, "semitones": semitones, "source_bpm": source_bpm, "target_bpm": target_bpm},
    )


def fetch_job(job_id: str) -> Job:
    return Job.fetch(job_id, connection=redis_conn)


def _status_as_text(job: Job) -> str:
    status = job.get_status(refresh=True)
    return getattr(status, "value", str(status))


def job_payload(job: Job) -> dict[str, Any]:
    status = _status_as_text(job)
    progress = job.meta.get("progress")
    if status == "finished":
        progress = 100
    elif progress is None:
        progress = 0

    queue_position = 0
    if status == "queued":
        try:
            job_ids = queue.job_ids
            if job.id in job_ids:
                queue_position = job_ids.index(job.id) + 1
        except Exception:
            pass

    payload: dict[str, Any] = {
        "id": job.id,
        "status": status,
        "kind": job.meta.get("kind"),
        "step": job.meta.get("step"),
        "progress": progress,
        "queue_position": queue_position,
        "output_name": job.meta.get("output_name"),
        "download_url": f"/api/jobs/{job.id}/download" if status == "finished" and job.meta.get("output_path") else None,
        "error": None,
    }
    if status == "failed":
        payload["error"] = job.meta.get("error") or job.exc_info or "Job failed"
    return payload


def queue_overview() -> dict[str, int]:
    return {
        "queued": len(queue),
        "started": len(StartedJobRegistry(queue=queue)),
        "finished": len(FinishedJobRegistry(queue=queue)),
        "failed": len(FailedJobRegistry(queue=queue)),
    }


def list_all_jobs() -> list[dict[str, Any]]:
    job_ids: list[str] = []
    job_ids += FinishedJobRegistry(queue=queue).get_job_ids()
    job_ids += FailedJobRegistry(queue=queue).get_job_ids()
    job_ids += StartedJobRegistry(queue=queue).get_job_ids()
    job_ids += queue.job_ids

    seen: set[str] = set()
    results = []
    for jid in job_ids:
        if jid in seen:
            continue
        seen.add(jid)
        try:
            job = Job.fetch(jid, connection=redis_conn)
            results.append(job_payload(job))
        except Exception:
            pass
    return results


def delete_job_and_files(job_id: str, uploads_dir: Path, outputs_dir: Path) -> None:
    try:
        job = Job.fetch(job_id, connection=redis_conn)
        job.delete()
    except Exception:
        pass

    import shutil
    for root in (uploads_dir / job_id, outputs_dir / job_id):
        if root.exists():
            shutil.rmtree(root, ignore_errors=True)


def clean_expired_jobs(uploads_dir: Path, outputs_dir: Path, max_age_seconds: int = 3600) -> int:
    import shutil
    import time
    
    cleaned_count = 0
    now = time.time()
    
    for directory in (uploads_dir, outputs_dir):
        if not directory.exists():
            continue
            
        for path in directory.iterdir():
            if path.is_dir() and not path.name.startswith("."):
                try:
                    mtime = path.stat().st_mtime
                    if now - mtime > max_age_seconds:
                        try:
                            job = Job.fetch(path.name, connection=redis_conn)
                            job.delete()
                        except Exception:
                            pass
                        
                        shutil.rmtree(path, ignore_errors=True)
                        cleaned_count += 1
                except Exception:
                    pass
    return cleaned_count
