export type Job = {
  id: string;
  status: string;
  kind: string | null;
  step: string | null;
  progress: number;
  queue_position?: number;
  output_name: string | null;
  download_url: string | null;
  error: string | null;
};

export type AudioAnalysis = {
  file_id: string;
  filename: string;
  key: string;
  tonic: string;
  mode: string;
  bpm: number;
};

const defaultApiBase = `${window.location.protocol}//${window.location.hostname}:8005`;
export const API_BASE = import.meta.env.VITE_API_BASE_URL || defaultApiBase;

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail || `Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export async function uploadWav(file: File): Promise<Job> {
  const form = new FormData();
  form.append('file', file);
  const response = await fetch(`${API_BASE}/api/jobs/upload`, {
    method: 'POST',
    body: form,
  });
  return parseResponse<Job>(response);
}

export async function analyzeAudio(file: File): Promise<AudioAnalysis> {
  const form = new FormData();
  form.append('file', file);
  const response = await fetch(`${API_BASE}/api/audio/analyze`, {
    method: 'POST',
    body: form,
  });
  return parseResponse<AudioAnalysis>(response);
}

export async function transformAudio(fileId: string, semitones: number, targetBpm: number): Promise<Job> {
  const form = new FormData();
  form.append('file_id', fileId);
  form.append('semitones', String(semitones));
  form.append('target_bpm', String(targetBpm));
  const response = await fetch(`${API_BASE}/api/jobs/transform`, {
    method: 'POST',
    body: form,
  });
  return parseResponse<Job>(response);
}
export async function separateVocals(file: File): Promise<Job> {
  const form = new FormData();
  form.append('file', file);
  const response = await fetch(`${API_BASE}/api/jobs/separate-vocals`, {
    method: 'POST',
    body: form,
  });
  return parseResponse<Job>(response);
}

export async function separateInstruments(file: File, stems: string[], quality: string): Promise<Job> {
  const form = new FormData();
  form.append('file', file);
  for (const stem of stems) {
    form.append('stems', stem);
  }
  form.append('quality', quality);
  const response = await fetch(`${API_BASE}/api/jobs/separate-instruments`, {
    method: 'POST',
    body: form,
  });
  return parseResponse<Job>(response);
}

export async function createYoutubeJob(url: string): Promise<Job> {
  const response = await fetch(`${API_BASE}/api/jobs/youtube`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url }),
  });
  return parseResponse<Job>(response);
}

export async function getJob(jobId: string): Promise<Job> {
  const response = await fetch(`${API_BASE}/api/jobs/${jobId}`);
  return parseResponse<Job>(response);
}

export async function listJobs(): Promise<Job[]> {
  const response = await fetch(`${API_BASE}/api/jobs`);
  return parseResponse<Job[]>(response);
}

export async function deleteJob(jobId: string): Promise<void> {
  await fetch(`${API_BASE}/api/jobs/${jobId}`, { method: 'DELETE' });
}

export function downloadUrl(job: Job): string | null {
  if (!job.download_url) return null;
  return `${API_BASE}${job.download_url}`;
}
