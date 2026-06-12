from pydantic import BaseModel, HttpUrl



class JobResponse(BaseModel):
    id: str
    status: str
    kind: str | None = None
    step: str | None = None
    progress: int = 0
    queue_position: int = 0
    output_name: str | None = None
    download_url: str | None = None
    error: str | None = None


class AudioAnalysisResponse(BaseModel):
    file_id: str
    filename: str
    key: str
    tonic: str
    mode: str
    bpm: float
