import { Client } from "@gradio/client";

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

// 預設本地 Gradio Port，如果是生產環境請由 VITE_API_BASE_URL 指定 (指向 https://您的帳號-Space名稱.hf.space)
const defaultApiBase = `http://localhost:7860`;
export const API_BASE = import.meta.env.VITE_API_BASE_URL || defaultApiBase;

// 虛擬記憶體 Job 倉庫，用來橋接 Gradio 的即時狀態與 main.tsx 的輪詢機制
const activeJobs = new Map<string, Job>();

// 音訊分析暫存，用來儲存 File 物件以便後續 Transform 時可以呼叫
const analyzedFiles = new Map<string, File>();

// 自動清洗與相容網址格式，將各種輸入格式轉為 Gradio Client 最穩定的 Space ID 或乾淨 URL
function cleanApiBase(url: string): string {
  let clean = url.trim();
  if (clean.endsWith("/")) {
    clean = clean.slice(0, -1);
  }
  
  // 匹配 https://huggingface.co/spaces/username/spacename 格式並轉為 username/spacename
  const spaceMatch = clean.match(/huggingface\.co\/spaces\/([^/]+)\/([^/]+)/);
  if (spaceMatch) {
    return `${spaceMatch[1]}/${spaceMatch[2]}`;
  }
  
  // 匹配 https://username-spacename.hf.space 并移除 https:// 和尾隨路由，保留乾淨網址
  if (clean.startsWith("https://")) {
    // 很多時候，Gradio 客戶端對 hf.space 裸網址支援較佳，亦可直接使用
    return clean;
  }
  
  return clean;
}

let clientPromise: Promise<any> | null = null;
async function getClient() {
  if (!clientPromise) {
    clientPromise = Client.connect(cleanApiBase(API_BASE), { events: ["data", "status"] });
  }
  return clientPromise;
}

function generateId() {
  return Math.random().toString(36).substring(2, 15);
}

export async function getJob(jobId: string): Promise<Job> {
  const job = activeJobs.get(jobId);
  if (!job) {
    throw new Error("Job not found");
  }
  return job;
}

export async function listJobs(): Promise<Job[]> {
  return Array.from(activeJobs.values());
}

export async function deleteJob(jobId: string): Promise<void> {
  activeJobs.delete(jobId);
}

// 1. WAV 轉檔 API (利用 Transform 的不變速不變調功能來包裝)
export async function uploadWav(file: File): Promise<Job> {
  const jobId = generateId();
  const job: Job = {
    id: jobId,
    status: 'queued',
    kind: 'wav_conversion',
    step: 'queued',
    progress: 0,
    output_name: null,
    download_url: null,
    error: null
  };
  activeJobs.set(jobId, job);

  void (async () => {
    let progressTimer: any = null;
    try {
      // 任務一建立，立刻進入處理狀態
      job.status = 'processing';
      job.step = 'converting';
      job.progress = 5;
      activeJobs.set(jobId, { ...job });

      // 虛擬進度定時器，每 1.2 秒遞增 1%~4%，最高到 90%
      progressTimer = setInterval(() => {
        if (job.status === 'processing' && job.progress < 90) {
          job.progress = Math.min(90, job.progress + Math.floor(Math.random() * 4) + 1);
          activeJobs.set(jobId, { ...job });
        }
      }, 1200);

      const app = await getClient();
      const submission = app.submit("/transform", [file, 0, 120]);
      let lastData: any = null;

      for await (const msg of submission) {
        if (msg.type === "status") {
          const evt = msg as any;
          if (evt.stage === 'pending') {
            if (progressTimer) {
              clearInterval(progressTimer);
              progressTimer = null;
            }
            job.status = 'queued';
            job.step = 'queued';
            job.queue_position = evt.queue_position;
          } else if (evt.stage === 'complete') {
            if (progressTimer) clearInterval(progressTimer);
            job.status = 'finished';
            job.step = 'finished';
            job.progress = 100;
          } else if (evt.stage === 'error') {
            if (progressTimer) clearInterval(progressTimer);
            job.status = 'failed';
            job.step = 'failed';
            job.error = evt.message || '音訊轉檔失敗';
          } else {
            job.status = 'processing';
            job.step = 'converting';
            if (!progressTimer && job.progress < 90) {
              progressTimer = setInterval(() => {
                if (job.status === 'processing' && job.progress < 90) {
                  job.progress = Math.min(90, job.progress + Math.floor(Math.random() * 4) + 1);
                  activeJobs.set(jobId, { ...job });
                }
              }, 1200);
            }
            if (evt.progress_data && evt.progress_data[0]) {
              const realProgress = Math.round(evt.progress_data[0].progress * 100);
              if (realProgress > job.progress) {
                job.progress = realProgress;
              }
            }
          }
          activeJobs.set(jobId, { ...job });
        } else if (msg.type === "data") {
          lastData = msg.data;
        }
      }

      if (progressTimer) clearInterval(progressTimer);

      if (!lastData) {
        throw new Error("沒有接收到返回的音訊資料");
      }

      const fileObj = lastData[0] as any;
      
      job.status = 'finished';
      job.step = 'finished';
      job.progress = 100;
      job.output_name = fileObj.orig_name || 'output.mp3';
      job.download_url = fileObj.url;
      activeJobs.set(jobId, { ...job });
    } catch (err) {
      if (progressTimer) clearInterval(progressTimer);
      job.status = 'failed';
      job.error = err instanceof Error ? err.message : String(err);
      activeJobs.set(jobId, { ...job });
    }
  })();

  return job;
}

// 2. 音訊分析 API (同步預測)
export async function analyzeAudio(file: File): Promise<AudioAnalysis> {
  const app = await getClient();
  const result = await app.predict("/analyze", [file]);
  const data = result.data[0] as any;
  if (data.error) {
    throw new Error(data.error);
  }
  
  const fileId = generateId();
  // 將 File 實體存起來，給後續的 transformAudio 使用
  analyzedFiles.set(fileId, file);
  
  return {
    file_id: fileId,
    filename: file.name,
    key: data.key || 'C',
    tonic: data.tonic || 'C',
    mode: data.mode || 'major',
    bpm: data.bpm || 120
  };
}

// 3. 變速變調 API (藉由 analyzedFiles 拿到音訊 File)
export async function transformAudio(fileId: string, semitones: number, targetBpm: number): Promise<Job> {
  const file = analyzedFiles.get(fileId);
  if (!file) {
    throw new Error("找不到對應的音訊暫存檔案，請重新上傳並分析");
  }

  const jobId = generateId();
  const job: Job = {
    id: jobId,
    status: 'queued',
    kind: 'transform_audio',
    step: 'queued',
    progress: 0,
    output_name: null,
    download_url: null,
    error: null
  };
  activeJobs.set(jobId, job);

  void (async () => {
    let progressTimer: any = null;
    try {
      // 任務一建立，立刻進入處理狀態
      job.status = 'processing';
      job.step = 'processing';
      job.progress = 5;
      activeJobs.set(jobId, { ...job });

      // 虛擬進度定時器，每 1.2 秒遞增 1%~4%，最高到 90%
      progressTimer = setInterval(() => {
        if (job.status === 'processing' && job.progress < 90) {
          job.progress = Math.min(90, job.progress + Math.floor(Math.random() * 4) + 1);
          activeJobs.set(jobId, { ...job });
        }
      }, 1200);

      const app = await getClient();
      const submission = app.submit("/transform", [file, semitones, targetBpm]);
      let lastData: any = null;

      for await (const msg of submission) {
        if (msg.type === "status") {
          const evt = msg as any;
          if (evt.stage === 'pending') {
            if (progressTimer) {
              clearInterval(progressTimer);
              progressTimer = null;
            }
            job.status = 'queued';
            job.step = 'queued';
            job.queue_position = evt.queue_position;
          } else if (evt.stage === 'complete') {
            if (progressTimer) clearInterval(progressTimer);
            job.status = 'finished';
            job.step = 'finished';
            job.progress = 100;
          } else if (evt.stage === 'error') {
            if (progressTimer) clearInterval(progressTimer);
            job.status = 'failed';
            job.step = 'failed';
            job.error = evt.message || '變速變調失敗';
          } else {
            job.status = 'processing';
            job.step = 'processing';
            if (!progressTimer && job.progress < 90) {
              progressTimer = setInterval(() => {
                if (job.status === 'processing' && job.progress < 90) {
                  job.progress = Math.min(90, job.progress + Math.floor(Math.random() * 4) + 1);
                  activeJobs.set(jobId, { ...job });
                }
              }, 1200);
            }
            if (evt.progress_data && evt.progress_data[0]) {
              const realProgress = Math.round(evt.progress_data[0].progress * 100);
              if (realProgress > job.progress) {
                job.progress = realProgress;
              }
            }
          }
          activeJobs.set(jobId, { ...job });
        } else if (msg.type === "data") {
          lastData = msg.data;
        }
      }

      if (progressTimer) clearInterval(progressTimer);

      if (!lastData) {
        throw new Error("沒有接收到變速變調的音訊資料");
      }

      const fileObj = lastData[0] as any;
      
      job.status = 'finished';
      job.step = 'finished';
      job.progress = 100;
      job.output_name = fileObj.orig_name || 'transformed.mp3';
      job.download_url = fileObj.url;
      activeJobs.set(jobId, { ...job });
    } catch (err) {
      if (progressTimer) clearInterval(progressTimer);
      job.status = 'failed';
      job.error = err instanceof Error ? err.message : String(err);
      activeJobs.set(jobId, { ...job });
    }
  })();

  return job;
}

// 4. 人聲分離 API
export async function separateVocals(file: File): Promise<Job> {
  const jobId = generateId();
  const job: Job = {
    id: jobId,
    status: 'queued',
    kind: 'separate_vocals',
    step: 'queued',
    progress: 0,
    output_name: null,
    download_url: null,
    error: null
  };
  activeJobs.set(jobId, job);

  void (async () => {
    let progressTimer: any = null;
    try {
      // 任務一建立，立刻進入處理狀態
      job.status = 'processing';
      job.step = 'separating';
      job.progress = 5;
      activeJobs.set(jobId, { ...job });

      // 虛擬進度定時器，每 1.2 秒遞增 1%~4%，最高到 90%
      progressTimer = setInterval(() => {
        if (job.status === 'processing' && job.progress < 90) {
          job.progress = Math.min(90, job.progress + Math.floor(Math.random() * 4) + 1);
          activeJobs.set(jobId, { ...job });
        }
      }, 1200);

      const app = await getClient();
      const submission = app.submit("/separate_vocals", [file]);
      let lastData: any = null;

      for await (const msg of submission) {
        if (msg.type === "status") {
          const evt = msg as any;
          if (evt.stage === 'pending') {
            if (progressTimer) {
              clearInterval(progressTimer);
              progressTimer = null;
            }
            job.status = 'queued';
            job.step = 'queued';
            job.queue_position = evt.queue_position;
          } else if (evt.stage === 'complete') {
            if (progressTimer) clearInterval(progressTimer);
            job.status = 'finished';
            job.step = 'finished';
            job.progress = 100;
          } else if (evt.stage === 'error') {
            if (progressTimer) clearInterval(progressTimer);
            job.status = 'failed';
            job.step = 'failed';
            job.error = evt.message || '人聲分離失敗';
          } else {
            job.status = 'processing';
            job.step = 'separating';
            if (!progressTimer && job.progress < 90) {
              progressTimer = setInterval(() => {
                if (job.status === 'processing' && job.progress < 90) {
                  job.progress = Math.min(90, job.progress + Math.floor(Math.random() * 4) + 1);
                  activeJobs.set(jobId, { ...job });
                }
              }, 1200);
            }
            if (evt.progress_data && evt.progress_data[0]) {
              const realProgress = Math.round(evt.progress_data[0].progress * 100);
              if (realProgress > job.progress) {
                job.progress = realProgress;
              }
            }
          }
          activeJobs.set(jobId, { ...job });
        } else if (msg.type === "data") {
          lastData = msg.data;
        }
      }

      if (progressTimer) clearInterval(progressTimer);

      if (!lastData) {
        throw new Error("沒有接收到人聲分離的壓縮資料");
      }

      const fileObj = lastData[0] as any;
      
      job.status = 'finished';
      job.step = 'finished';
      job.progress = 100;
      job.output_name = 'vocals_accompaniment.zip';
      job.download_url = fileObj.url;
      activeJobs.set(jobId, { ...job });
    } catch (err) {
      if (progressTimer) clearInterval(progressTimer);
      job.status = 'failed';
      job.error = err instanceof Error ? err.message : String(err);
      activeJobs.set(jobId, { ...job });
    }
  })();

  return job;
}

// 5. 樂器分離 API
export async function separateInstruments(file: File, stems: string[], quality: string): Promise<Job> {
  const jobId = generateId();
  const job: Job = {
    id: jobId,
    status: 'queued',
    kind: 'separate_instruments',
    step: 'queued',
    progress: 0,
    output_name: null,
    download_url: null,
    error: null
  };
  activeJobs.set(jobId, job);

  void (async () => {
    let progressTimer: any = null;
    try {
      // 任務一建立，立刻進入處理狀態
      job.status = 'processing';
      job.step = 'separating';
      job.progress = 5;
      activeJobs.set(jobId, { ...job });

      // 虛擬進度定時器，每 1.2 秒遞增 1%~4%，最高到 90%
      progressTimer = setInterval(() => {
        if (job.status === 'processing' && job.progress < 90) {
          job.progress = Math.min(90, job.progress + Math.floor(Math.random() * 4) + 1);
          activeJobs.set(jobId, { ...job });
        }
      }, 1200);

      const app = await getClient();
      const submission = app.submit("/separate_instruments", [file, stems, quality]);
      let lastData: any = null;

      for await (const msg of submission) {
        if (msg.type === "status") {
          const evt = msg as any;
          if (evt.stage === 'pending') {
            if (progressTimer) {
              clearInterval(progressTimer);
              progressTimer = null;
            }
            job.status = 'queued';
            job.step = 'queued';
            job.queue_position = evt.queue_position;
          } else if (evt.stage === 'complete') {
            if (progressTimer) clearInterval(progressTimer);
            job.status = 'finished';
            job.step = 'finished';
            job.progress = 100;
          } else if (evt.stage === 'error') {
            if (progressTimer) clearInterval(progressTimer);
            job.status = 'failed';
            job.step = 'failed';
            job.error = evt.message || '樂器分離失敗';
          } else {
            job.status = 'processing';
            job.step = 'separating';
            if (!progressTimer && job.progress < 90) {
              progressTimer = setInterval(() => {
                if (job.status === 'processing' && job.progress < 90) {
                  job.progress = Math.min(90, job.progress + Math.floor(Math.random() * 4) + 1);
                  activeJobs.set(jobId, { ...job });
                }
              }, 1200);
            }
            if (evt.progress_data && evt.progress_data[0]) {
              const realProgress = Math.round(evt.progress_data[0].progress * 100);
              if (realProgress > job.progress) {
                job.progress = realProgress;
              }
            }
          }
          activeJobs.set(jobId, { ...job });
        } else if (msg.type === "data") {
          lastData = msg.data;
        }
      }

      if (progressTimer) clearInterval(progressTimer);

      if (!lastData) {
        throw new Error("沒有接收到樂器分離的壓縮資料");
      }

      const fileObj = lastData[0] as any;
      
      job.status = 'finished';
      job.step = 'finished';
      job.progress = 100;
      job.output_name = 'instruments.zip';
      job.download_url = fileObj.url;
      activeJobs.set(jobId, { ...job });
    } catch (err) {
      if (progressTimer) clearInterval(progressTimer);
      job.status = 'failed';
      job.error = err instanceof Error ? err.message : String(err);
      activeJobs.set(jobId, { ...job });
    }
  })();

  return job;
}

// 6. YouTube 轉檔 API
export async function createYoutubeJob(url: string): Promise<Job> {
  const jobId = generateId();
  const job: Job = {
    id: jobId,
    status: 'queued',
    kind: 'youtube_to_mp3',
    step: 'queued',
    progress: 0,
    output_name: null,
    download_url: null,
    error: null
  };
  activeJobs.set(jobId, job);

  void (async () => {
    let progressTimer: any = null;
    try {
      // 任務一建立，立刻進入處理狀態
      job.status = 'processing';
      job.step = 'downloading';
      job.progress = 5;
      activeJobs.set(jobId, { ...job });

      // 虛擬進度定時器，每 1.2 秒遞增 1%~4%，最高到 90%
      progressTimer = setInterval(() => {
        if (job.status === 'processing' && job.progress < 90) {
          job.progress = Math.min(90, job.progress + Math.floor(Math.random() * 4) + 1);
          activeJobs.set(jobId, { ...job });
        }
      }, 1200);

      const app = await getClient();
      const submission = app.submit("/youtube", [url]);
      let lastData: any = null;

      for await (const msg of submission) {
        if (msg.type === "status") {
          const evt = msg as any;
          if (evt.stage === 'pending') {
            if (progressTimer) {
              clearInterval(progressTimer);
              progressTimer = null;
            }
            job.status = 'queued';
            job.step = 'queued';
            job.queue_position = evt.queue_position;
          } else if (evt.stage === 'complete') {
            if (progressTimer) clearInterval(progressTimer);
            job.status = 'finished';
            job.step = 'finished';
            job.progress = 100;
          } else if (evt.stage === 'error') {
            if (progressTimer) clearInterval(progressTimer);
            job.status = 'failed';
            job.step = 'failed';
            job.error = evt.message || 'YouTube下載失敗';
          } else {
            job.status = 'processing';
            job.step = 'downloading';
            if (!progressTimer && job.progress < 90) {
              progressTimer = setInterval(() => {
                if (job.status === 'processing' && job.progress < 90) {
                  job.progress = Math.min(90, job.progress + Math.floor(Math.random() * 4) + 1);
                  activeJobs.set(jobId, { ...job });
                }
              }, 1200);
            }
            if (evt.progress_data && evt.progress_data[0]) {
              const realProgress = Math.round(evt.progress_data[0].progress * 100);
              if (realProgress > job.progress) {
                job.progress = realProgress;
              }
            }
          }
          activeJobs.set(jobId, { ...job });
        } else if (msg.type === "data") {
          lastData = msg.data;
        }
      }

      if (progressTimer) clearInterval(progressTimer);

      if (!lastData) {
        throw new Error("沒有接收到 YouTube 下載的音訊資料");
      }

      const fileObj = lastData[0] as any;
      
      job.status = 'finished';
      job.step = 'finished';
      job.progress = 100;
      job.output_name = fileObj.orig_name || 'youtube.mp3';
      job.download_url = fileObj.url;
      activeJobs.set(jobId, { ...job });
    } catch (err) {
      if (progressTimer) clearInterval(progressTimer);
      job.status = 'failed';
      job.error = err instanceof Error ? err.message : String(err);
      activeJobs.set(jobId, { ...job });
    }
  })();

  return job;
}

export function downloadUrl(job: Job): string | null {
  // Gradio 返回的 url 已經是完整的 HTTPS 下載網址，直接返回即可
  return job.download_url;
}

export async function submitBug(title: string, description: string, email: string = "") {
  try {
    const app = await getClient();
    
    // 實作 6 秒超時機制，防止遠端後端尚未部署完成時，前端呼叫 predict 永遠掛起
    const predictPromise = app.predict("/submit_bug", [title, description, email]);
    const timeoutPromise = new Promise((_, reject) =>
      setTimeout(() => reject(new Error("伺服器回應超時，可能後端服務尚未更新部署。")), 6000)
    );
    
    const result = (await Promise.race([predictPromise, timeoutPromise])) as any;
    if (!result || !result.data || !result.data[0]) {
      throw new Error("伺服器回傳格式錯誤");
    }
    
    return result.data[0] as { success: boolean; message: string };
  } catch (err) {
    console.error("回報 Bug 失敗:", err);
    return {
      success: false,
      message: err instanceof Error ? err.message : String(err)
    };
  }
}


