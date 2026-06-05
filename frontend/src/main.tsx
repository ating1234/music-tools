import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  API_BASE,
  AudioAnalysis,
  Job,
  analyzeAudio,
  createYoutubeJob,
  deleteJob,
  downloadUrl,
  getJob,
  listJobs,
  separateInstruments,
  separateVocals,
  transformAudio,
  uploadWav,
} from './api';

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {});
  });
}
import { UI_TEXT } from './uiText';
import './styles.css';

const INSTRUMENT_OPTIONS = [
  { value: 'vocals', label: 'Vocals 人聲' },
  { value: 'drums', label: 'Drums 鼓組' },
  { value: 'bass', label: 'Bass 貝斯' },
  { value: 'guitar', label: 'Guitar 吉他' },
  { value: 'piano', label: 'Piano 鋼琴' },
  { value: 'other', label: 'Other 其他樂器' },
];

const QUALITY_OPTIONS = [
  { value: 'standard', label: '標準：快', description: '不使用 shifts' },
  { value: 'high', label: '高品質', description: '--shifts 2' },
  { value: 'highest', label: '最高品質', description: '--shifts 4，速度較慢' },
];

const NOTES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];
const ENHARMONIC_NOTES: Record<string, string> = {
  'C#': 'Db',
  'D#': 'Eb',
  'F#': 'Gb',
  'G#': 'Ab',
  'A#': 'Bb',
};

function statusLabel(job: Job | null): string {
  if (!job) return '尚未建立任務';
  const step = job.step ? ` / ${job.step}` : '';
  return `${job.status}${step}`;
}

function App() {
  // Module power states (Toggle components display)
  const [showWav, setShowWav] = useState(true);
  const [showYoutube, setShowYoutube] = useState(true);
  const [showVocalSep, setShowVocalSep] = useState(true);
  const [showStemsSep, setShowStemsSep] = useState(true);
  const [showPitch, setShowPitch] = useState(true);
  // VU Meter needle angles
  const [needleL, setNeedleL] = useState(-35);
  const [needleR, setNeedleR] = useState(-35);

  // File states
  const [file, setFile] = useState<File | null>(null);
  const [vocalFile, setVocalFile] = useState<File | null>(null);
  const [instrumentFile, setInstrumentFile] = useState<File | null>(null);
  const [transformFile, setTransformFile] = useState<File | null>(null);

  // Drag states
  const [draggingWav, setDraggingWav] = useState(false);
  const [draggingVocal, setDraggingVocal] = useState(false);
  const [draggingInstrument, setDraggingInstrument] = useState(false);
  const [draggingTransform, setDraggingTransform] = useState(false);

  // Other form states
  const [analysis, setAnalysis] = useState<AudioAnalysis | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [semitones, setSemitones] = useState(0);
  const [targetBpm, setTargetBpm] = useState('');
  const [selectedInstruments, setSelectedInstruments] = useState<string[]>([]);
  const [instrumentQuality, setInstrumentQuality] = useState('standard');
  const [youtubeUrl, setYoutubeUrl] = useState('');
  const [job, setJob] = useState<Job | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<Job[]>([]);
  const [historyOpen, setHistoryOpen] = useState(false);
  // 手機版單頁 RWD 選單狀態
  const [isMobile, setIsMobile] = useState(false);
  const [activeMobileModule, setActiveMobileModule] = useState<'menu' | 'wav' | 'youtube' | 'vocal' | 'stems' | 'pitch'>('menu');

  useEffect(() => {
    const handleResize = () => {
      setIsMobile(window.innerWidth <= 768);
    };
    handleResize();
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  const selectMobileModule = (module: 'menu' | 'wav' | 'youtube' | 'vocal' | 'stems' | 'pitch') => {
    setActiveMobileModule(module);
    if (module === 'wav') {
      setShowWav(true);
    } else if (module === 'youtube') {
      setShowYoutube(true);
    } else if (module === 'vocal') {
      setShowVocalSep(true);
    } else if (module === 'stems') {
      setShowStemsSep(true);
    } else if (module === 'pitch') {
      setShowPitch(true);
    }
  };

  // CH 01 - 03 Newly Added Hardware States (v8)
  const [wavBitrate, setWavBitrate] = useState('320');
  const [wavLowCut, setWavLowCut] = useState(false);
  const [wavMono, setWavMono] = useState(false);

  const [ytFormat, setYtFormat] = useState('mp3');
  const [ytGain, setYtGain] = useState('0');
  const [ytNormalize, setYtNormalize] = useState(false);

  const [vocalNoise, setVocalNoise] = useState('mid');
  const [vocalVolume, setVocalVolume] = useState(8);
  const [vocalBoost, setVocalBoost] = useState(false);

  // Polling logic for jobs with temporary error tolerance
  useEffect(() => {
    if (!job || job.status === 'finished' || job.status === 'failed') return;

    let consecutiveFailures = 0;
    const timer = window.setInterval(async () => {
      try {
        const updatedJob = await getJob(job.id);
        setJob(updatedJob);
        consecutiveFailures = 0; // 成功連線，重置失敗計數
        
        // 任務若順利完成，清空之前的臨時連線錯誤
        if (updatedJob.status === 'finished') {
          setError(null);
        }
      } catch (err) {
        consecutiveFailures++;
        // 只有在連續失敗超過 5 次（約 7.5 秒連不上）時，才向使用者警報
        if (consecutiveFailures > 5) {
          setError(err instanceof Error ? err.message : '查詢任務失敗');
        }
      }
    }, 1500);

    return () => window.clearInterval(timer);
  }, [job]);

  // 當歷史面板開啟時，載入所有任務
  useEffect(() => {
    if (!historyOpen) return;
    listJobs().then(setHistory).catch(() => {});
  }, [historyOpen]);

  async function handleDeleteJob(jobId: string) {
    await deleteJob(jobId);
    setHistory(prev => prev.filter(j => j.id !== jobId));
    if (job?.id === jobId) setJob(null);
  }

  // VU Meter needle jittering when busy or analyzing
  useEffect(() => {
    if (!busy && !analyzing) {
      setNeedleL(-35);
      setNeedleR(-35);
      return;
    }

    const interval = window.setInterval(() => {
      // Jitter needle angles between -20 and +20 degrees
      const jitterL = Math.floor(Math.random() * 41) - 20;
      const jitterR = Math.floor(Math.random() * 41) - 20;
      setNeedleL(jitterL);
      setNeedleR(jitterR);
    }, 80);

    return () => window.clearInterval(interval);
  }, [busy, analyzing]);

  async function runAction(action: () => Promise<Job>) {
    setBusy(true);
    setError(null);
    try {
      setJob(await action());
    } catch (err) {
      setError(err instanceof Error ? err.message : '建立任務失敗');
    } finally {
      setBusy(false);
    }
  }

  const currentDownloadUrl = job ? downloadUrl(job) : null;
  const downloadLabel = job?.kind?.startsWith('separate_') || job?.kind === 'transcribe_audio' 
    ? UI_TEXT.status.downloadZip 
    : UI_TEXT.status.downloadMp3;
  const progress = job?.progress ?? 0;
  const currentKey = analysis ? formatKey(analysis.tonic, analysis.mode) : UI_TEXT.pitch.notAnalyzed;
  const adjustedKey = analysis ? transposeKey(analysis.tonic, analysis.mode, semitones) : UI_TEXT.pitch.notAnalyzed;
  const adjustedBpm = targetBpm || (analysis ? String(analysis.bpm) : '');

  function toggleInstrument(stem: string) {
    setSelectedInstruments((current) =>
      current.includes(stem) ? current.filter((item) => item !== stem) : [...current, stem],
    );
  }

  async function runAnalyze() {
    if (!transformFile) {
      setError('請先選擇要分析的音訊檔');
      return;
    }
    setAnalyzing(true);
    setError(null);
    try {
      const result = await analyzeAudio(transformFile);
      setAnalysis(result);
      setSemitones(0);
      setTargetBpm(String(result.bpm));
    } catch (err) {
      setError(err instanceof Error ? err.message : '分析音訊失敗');
    } finally {
      setAnalyzing(false);
    }
  }

  // Drag and drop helper
  function createDragHandlers(setDragging: (val: boolean) => void, setUploadedFile: (file: File) => void) {
    return {
      onDragOver: (e: React.DragEvent) => {
        e.preventDefault();
        setDragging(true);
      },
      onDragLeave: (e: React.DragEvent) => {
        e.preventDefault();
        setDragging(false);
      },
      onDrop: (e: React.DragEvent) => {
        e.preventDefault();
        setDragging(false);
        const droppedFile = e.dataTransfer.files?.[0];
        if (droppedFile) {
          setUploadedFile(droppedFile);
        }
      }
    };
  }

  // Calculate Knob Angles for UI
  const getQualityKnobAngle = (val: string) => {
    if (val === 'standard') return -60;
    if (val === 'high') return 0;
    if (val === 'highest') return 60;
    return 0;
  };

  // Knob Angle Calculators for CH 01 - 03 (v8)
  const getBitrateKnobAngle = (val: string) => {
    if (val === '128') return -90;
    if (val === '192') return -30;
    if (val === '256') return 30;
    if (val === '320') return 90;
    return 90;
  };

  const getFormatKnobAngle = (val: string) => {
    if (val === 'mp3') return -90;
    if (val === 'wav') return -30;
    if (val === 'm4a') return 30;
    if (val === 'flac') return 90;
    return -90;
  };

  const getGainKnobAngle = (val: string) => {
    if (val === '-3') return -90;
    if (val === '0') return -30;
    if (val === '+3') return 30;
    if (val === '+6') return 90;
    return -30;
  };

  const getNoiseKnobAngle = (val: string) => {
    if (val === 'off') return -90;
    if (val === 'low') return -30;
    if (val === 'mid') return 30;
    if (val === 'high') return 90;
    return 30;
  };

  const getVolumeKnobAngle = (val: number) => {
    return -100 + val * 20; // 0~10 maps to -100~100 deg
  };

  // Generate ASCII progress bar for LCD
  const renderLcdProgress = () => {
    if (!job) return '';
    const barLength = 15;
    const filledCount = Math.round((progress / 100) * barLength);
    const emptyCount = barLength - filledCount;
    return `[${'█'.repeat(filledCount)}${'░'.repeat(emptyCount)}] ${progress}%`;
  };

  const jobRunning = job !== null && job.status !== 'finished' && job.status !== 'failed';

  return (
    <div className="studio-cabinet">
      <main className="studio-console">
        {/* Cabinet Screws Decoration */}
        <div className="screw top-left" />
        <div className="screw top-right" />
        <div className="screw bottom-left" />
        <div className="screw bottom-right" />

        <div className="console-panel">
          {/* Console Header: Title, Power Panel, VU Meters */}
          <header className="console-header">
            <div className="console-title">
              <h1>{UI_TEXT.global.title}</h1>
              <p>{UI_TEXT.global.subtitle}</p>
              <div style={{ fontSize: '10px', color: 'rgba(255, 162, 23, 0.65)', marginTop: '4px', letterSpacing: '0.05em' }}>
                採用網路上的免費資源，所以轉檔速度慢，請耐心等待！
              </div>
              <div className="api-node">{UI_TEXT.global.apiBase}{API_BASE}</div>
            </div>

            {/* Module Power Distribution Board */}
            <div className="power-panel" aria-label={UI_TEXT.powerPanel.title}>
              <div className="power-panel-title">{UI_TEXT.powerPanel.title}</div>
              <div className="power-switches-grid">
                {/* CH1: WAV - POWER (red LED) */}
                <div className="power-switch-item">
                  <span className="power-switch-label">{UI_TEXT.powerPanel.wavToggle}</span>
                  <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <span className={`led-indicator ${showWav ? 'on' : ''}`} />
                    <label className="toggle-lever">
                      <input
                        type="checkbox"
                        checked={showWav}
                        onChange={(e) => setShowWav(e.target.checked)}
                      />
                      <div className="switch-track">
                        <div className="switch-lever" />
                      </div>
                    </label>
                  </span>
                </div>

                {/* CH2: YT */}
                {!isMobile && (
                  <div className="power-switch-item">
                    <span className="power-switch-label">{UI_TEXT.powerPanel.ytToggle}</span>
                    <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <span className={`led-indicator green ${showYoutube ? 'on' : ''}`} />
                      <label className="toggle-lever">
                        <input
                          type="checkbox"
                          checked={showYoutube}
                          onChange={(e) => setShowYoutube(e.target.checked)}
                        />
                        <div className="switch-track">
                          <div className="switch-lever" />
                        </div>
                      </label>
                    </span>
                  </div>
                )}

                {/* CH3: VOCAL */}
                {!isMobile && (
                  <div className="power-switch-item">
                    <span className="power-switch-label">{UI_TEXT.powerPanel.vocalToggle}</span>
                    <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <span className={`led-indicator green ${showVocalSep ? 'on' : ''}`} />
                      <label className="toggle-lever">
                        <input
                          type="checkbox"
                          checked={showVocalSep}
                          onChange={(e) => setShowVocalSep(e.target.checked)}
                        />
                        <div className="switch-track">
                          <div className="switch-lever" />
                        </div>
                      </label>
                    </span>
                  </div>
                )}

                {/* CH4: STEMS */}
                {!isMobile && (
                  <div className="power-switch-item">
                    <span className="power-switch-label">{UI_TEXT.powerPanel.stemsToggle}</span>
                    <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <span className={`led-indicator green ${showStemsSep ? 'on' : ''}`} />
                      <label className="toggle-lever">
                        <input
                          type="checkbox"
                          checked={showStemsSep}
                          onChange={(e) => setShowStemsSep(e.target.checked)}
                        />
                        <div className="switch-track">
                          <div className="switch-lever" />
                        </div>
                      </label>
                    </span>
                  </div>
                )}

                {/* CH5: PITCH */}
                {!isMobile && (
                  <div className="power-switch-item">
                    <span className="power-switch-label">{UI_TEXT.powerPanel.pitchToggle}</span>
                    <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <span className={`led-indicator green ${showPitch ? 'on' : ''}`} />
                      <label className="toggle-lever">
                        <input
                          type="checkbox"
                          checked={showPitch}
                          onChange={(e) => setShowPitch(e.target.checked)}
                        />
                        <div className="switch-track">
                          <div className="switch-lever" />
                        </div>
                      </label>
                    </span>
                  </div>
                )}
              </div>
            </div>

            {/* Dual VU Meters */}
            {!isMobile && (
              <div className="vu-meter-container">
                <div className="vu-meters-row">
                  <div className="vu-meter">
                    <div className="vu-meter-scale" />
                    <div className="vu-needle" style={{ transform: `rotate(${needleL}deg)` }} />
                    <div className="vu-needle-pivot" />
                    <div className="vu-label">L</div>
                  </div>
                  <div className="vu-meter">
                    <div className="vu-meter-scale" />
                    <div className="vu-needle" style={{ transform: `rotate(${needleR}deg)` }} />
                    <div className="vu-needle-pivot" />
                    <div className="vu-label">R</div>
                  </div>
                </div>
                <div className="vu-master-label">MASTER</div>
              </div>
            )}

            {/* Weathered Speaker Mesh Grill */}
            {!isMobile && (
              <div className="mesh-grill" />
            )}
          </header>

          {/* Main Grid: Interactive Modules */}
          <div className="studio-cabinet-layout">
            {/* Left Column: 主要音訊處理模組 */}
            <div className="main-rack">
              {/* 手機版返回選單按鈕 */}
              {isMobile && activeMobileModule !== 'menu' && (
                <button 
                  type="button" 
                  className="console-btn mobile-back-btn" 
                  onClick={() => setActiveMobileModule('menu')}
                >
                  [ ← RETURN TO STUDIO MENU ]
                </button>
              )}

              {/* 手機版功能主選單 */}
              {isMobile && activeMobileModule === 'menu' && (
                <div className="mobile-menu-grid">
                  <button type="button" className="mobile-menu-card" onClick={() => selectMobileModule('wav')}>
                    <div className="card-led" />
                    <div className="card-header">
                      <span className="card-ch">CH 01</span>
                      <h3>📀 {UI_TEXT.wavConverter.title}</h3>
                    </div>
                    <p>{UI_TEXT.wavConverter.desc}</p>
                  </button>
                  
                  <button type="button" className="mobile-menu-card" onClick={() => selectMobileModule('youtube')}>
                    <div className="card-led green" />
                    <div className="card-header">
                      <span className="card-ch">CH 02</span>
                      <h3>📺 {UI_TEXT.ytExtractor.title}</h3>
                    </div>
                    <p>{UI_TEXT.ytExtractor.desc}</p>
                  </button>

                  <button type="button" className="mobile-menu-card" onClick={() => selectMobileModule('vocal')}>
                    <div className="card-led green" />
                    <div className="card-header">
                      <span className="card-ch">CH 03</span>
                      <h3>🎙️ {UI_TEXT.vocalSeparator.title}</h3>
                    </div>
                    <p>{UI_TEXT.vocalSeparator.desc}</p>
                  </button>

                  <button type="button" className="mobile-menu-card" onClick={() => selectMobileModule('stems')}>
                    <div className="card-led green" />
                    <div className="card-header">
                      <span className="card-ch">CH 04</span>
                      <h3>🎸 {UI_TEXT.stemsSeparator.title}</h3>
                    </div>
                    <p>{UI_TEXT.stemsSeparator.desc}</p>
                  </button>

                  <button type="button" className="mobile-menu-card" onClick={() => selectMobileModule('pitch')}>
                    <div className="card-led green" />
                    <div className="card-header">
                      <span className="card-ch">CH 05</span>
                      <h3>🎛️ {UI_TEXT.pitch.title}</h3>
                    </div>
                    <p>{UI_TEXT.pitch.desc}</p>
                  </button>
                </div>
              )}

              {/* 只有在非手機端，或者在手機端且有選中 CH01~CH04 時才渲染此 grid */}
              {(!isMobile || ['wav', 'youtube', 'vocal', 'stems'].includes(activeMobileModule)) && (
                <div className="audio-modules-grid">

            {/* CH 01: WAV TO MP3 */}
            {(!isMobile && showWav) || (isMobile && activeMobileModule === 'wav') ? (
              <div className="channel-strip short-channel">
                <div className="screw top-left" />
                <div className="screw top-right" />
                <div className="screw bottom-left" />
                <div className="screw bottom-right" />
                <div className="channel-strip-header">
                  <h2>📀 {UI_TEXT.wavConverter.title}</h2>
                  <span className="ch-number">CH 01</span>
                </div>
                <p className="channel-desc">{UI_TEXT.wavConverter.desc}</p>
                
                <form
                  style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginTop: 'auto' }}
                  onSubmit={(event) => {
                    event.preventDefault();
                    if (!file) {
                      setError('請先選擇 WAV 檔');
                      return;
                    }
                    void runAction(() => uploadWav(file));
                  }}
                >
                  {/* CH 01 Hardware Controls */}
                  <div style={{ display: 'flex', gap: '12px', alignItems: 'center', justifyContent: 'space-between' }}>
                    <div className="console-field" style={{ flex: 1 }}>
                      <span className="console-field-label">BITRATE</span>
                      <select className="console-select" value={wavBitrate} onChange={(e) => setWavBitrate(e.target.value)}>
                        <option value="128">128 Kbps</option>
                        <option value="192">192 Kbps</option>
                        <option value="256">256 Kbps</option>
                        <option value="320">320 Kbps</option>
                      </select>
                    </div>
                    <div className="knob-container">
                      <div className="knob-dial-wrapper">
                        <div className="knob-ticks" />
                        <div 
                          className="knob-rotator" 
                          style={{ transform: `rotate(${getBitrateKnobAngle(wavBitrate)}deg)` }}
                        >
                          <div className="knob-pointer" />
                        </div>
                      </div>
                    </div>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
                    <div className="lever-selector-mini">
                      <span className="lever-selector-text">LOW CUT 80Hz</span>
                      <label className="toggle-lever">
                        <input
                          type="checkbox"
                          checked={wavLowCut}
                          onChange={(e) => setWavLowCut(e.target.checked)}
                        />
                        <div className="switch-track">
                          <div className="switch-lever" />
                        </div>
                      </label>
                    </div>
                    <div className="lever-selector-mini">
                      <span className="lever-selector-text">MONO MODE</span>
                      <label className="toggle-lever">
                        <input
                          type="checkbox"
                          checked={wavMono}
                          onChange={(e) => setWavMono(e.target.checked)}
                        />
                        <div className="switch-track">
                          <div className="switch-lever" />
                        </div>
                      </label>
                    </div>
                  </div>

                  <label className={`tape-deck-zone ${draggingWav ? 'dragging' : ''}`} {...createDragHandlers(setDraggingWav, setFile)}>
                    <span className="tape-deck-icon">📼</span>
                    <span className="tape-deck-text">{file ? file.name : UI_TEXT.wavConverter.dragPrompt}</span>
                    <input
                      type="file"
                      accept=".wav,audio/wav,audio/x-wav"
                      onChange={(event) => setFile(event.target.files?.[0] ?? null)}
                    />
                  </label>
                  <button type="submit" className="console-btn btn-accent btn-wide" disabled={busy || jobRunning}>
                    {busy ? UI_TEXT.wavConverter.buttonBusy : UI_TEXT.wavConverter.buttonStart}
                  </button>
                </form>
              </div>
            ) : (!isMobile ? (
              <div className="blind-panel short-channel">
                <div className="screw top-left" />
                <div className="screw top-right" />
                <div className="screw bottom-left" />
                <div className="screw bottom-right" />
                <div className="blind-panel-text">{UI_TEXT.global.emptyRackSlot} - CH 01</div>
              </div>
            ) : null)}

            {/* CH 02: YOUTUBE TO MP3 */}
            {(!isMobile && showYoutube) || (isMobile && activeMobileModule === 'youtube') ? (
              <div className="channel-strip short-channel">
                <div className="screw top-left" />
                <div className="screw top-right" />
                <div className="screw bottom-left" />
                <div className="screw bottom-right" />
                <div className="channel-strip-header">
                  <h2>📺 {UI_TEXT.ytExtractor.title}</h2>
                  <span className="ch-number">CH 02</span>
                </div>
                <p className="channel-desc">{UI_TEXT.ytExtractor.desc}</p>
                
                <form
                  style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginTop: 'auto' }}
                  onSubmit={(event) => {
                    event.preventDefault();
                    if (!youtubeUrl.trim()) {
                      setError('請貼上 YouTube 連結');
                      return;
                    }
                    void runAction(() => createYoutubeJob(youtubeUrl.trim()));
                  }}
                >
                  {/* CH 02 Hardware Controls */}
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
                    <div style={{ display: 'flex', gap: '6px', alignItems: 'center', justifyContent: 'space-between' }}>
                      <div className="console-field" style={{ flex: 1 }}>
                        <span className="console-field-label">FORMAT</span>
                        <select className="console-select" value={ytFormat} onChange={(e) => setYtFormat(e.target.value)}>
                          <option value="mp3">MP3</option>
                          <option value="wav">WAV</option>
                          <option value="m4a">M4A</option>
                          <option value="flac">FLAC</option>
                        </select>
                      </div>
                      <div className="knob-container">
                        <div className="knob-dial-wrapper">
                          <div className="knob-ticks" />
                          <div 
                            className="knob-rotator" 
                            style={{ transform: `rotate(${getFormatKnobAngle(ytFormat)}deg)` }}
                          >
                            <div className="knob-pointer" />
                          </div>
                        </div>
                      </div>
                    </div>

                    <div style={{ display: 'flex', gap: '6px', alignItems: 'center', justifyContent: 'space-between' }}>
                      <div className="console-field" style={{ flex: 1 }}>
                        <span className="console-field-label">GAIN</span>
                        <select className="console-select" value={ytGain} onChange={(e) => setYtGain(e.target.value)}>
                          <option value="-3">-3dB</option>
                          <option value="0">0dB</option>
                          <option value="+3">+3dB</option>
                          <option value="+6">+6dB</option>
                        </select>
                      </div>
                      <div className="knob-container">
                        <div className="knob-dial-wrapper">
                          <div className="knob-ticks" />
                          <div 
                            className="knob-rotator" 
                            style={{ transform: `rotate(${getGainKnobAngle(ytGain)}deg)` }}
                          >
                            <div className="knob-pointer" />
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '8px' }}>
                    <div className="lever-selector-mini" style={{ width: '100%' }}>
                      <span className="lever-selector-text">VOLUME NORMALIZER</span>
                      <label className="toggle-lever">
                        <input
                          type="checkbox"
                          checked={ytNormalize}
                          onChange={(e) => setYtNormalize(e.target.checked)}
                        />
                        <div className="switch-track">
                          <div className="switch-lever" />
                        </div>
                      </label>
                    </div>
                  </div>

                  <div className="console-field">
                    <span className="console-field-label">YOUTUBE URL</span>
                    <input
                      className="console-input-text"
                      type="url"
                      placeholder={UI_TEXT.ytExtractor.placeholder}
                      value={youtubeUrl}
                      onChange={(event) => setYoutubeUrl(event.target.value)}
                    />
                  </div>
                  <button type="submit" className="console-btn btn-accent btn-wide" disabled={busy || jobRunning}>
                    {busy ? UI_TEXT.ytExtractor.buttonBusy : UI_TEXT.ytExtractor.buttonStart}
                  </button>
                </form>
              </div>
            ) : (!isMobile ? (
              <div className="blind-panel short-channel">
                <div className="screw top-left" />
                <div className="screw top-right" />
                <div className="screw bottom-left" />
                <div className="screw bottom-right" />
                <div className="blind-panel-text">{UI_TEXT.global.emptyRackSlot} - CH 02</div>
              </div>
            ) : null)}

            {/* CH 03: VOCAL SEPARATOR */}
            {(!isMobile && showVocalSep) || (isMobile && activeMobileModule === 'vocal') ? (
              <div className="channel-strip short-channel">
                <div className="screw top-left" />
                <div className="screw top-right" />
                <div className="screw bottom-left" />
                <div className="screw bottom-right" />
                <div className="channel-strip-header">
                  <h2>🎙️ {UI_TEXT.vocalSeparator.title}</h2>
                  <span className="ch-number">CH 03</span>
                </div>
                <p className="channel-desc">{UI_TEXT.vocalSeparator.desc}</p>
                
                <form
                  style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginTop: 'auto' }}
                  onSubmit={(event) => {
                    event.preventDefault();
                    if (!vocalFile) {
                      setError('請先選擇要分離的音訊檔');
                      return;
                    }
                    void runAction(() => separateVocals(vocalFile));
                  }}
                >
                  {/* CH 03 Hardware Controls */}
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
                    <div style={{ display: 'flex', gap: '6px', alignItems: 'center', justifyContent: 'space-between' }}>
                      <div className="console-field" style={{ flex: 1 }}>
                        <span className="console-field-label">NOISE GATE</span>
                        <select className="console-select" value={vocalNoise} onChange={(e) => setVocalNoise(e.target.value)}>
                          <option value="off">OFF</option>
                          <option value="low">LOW</option>
                          <option value="mid">MID</option>
                          <option value="high">HIGH</option>
                        </select>
                      </div>
                      <div className="knob-container">
                        <div className="knob-dial-wrapper">
                          <div className="knob-ticks" />
                          <div 
                            className="knob-rotator" 
                            style={{ transform: `rotate(${getNoiseKnobAngle(vocalNoise)}deg)` }}
                          >
                            <div className="knob-pointer" />
                          </div>
                        </div>
                      </div>
                    </div>

                    <div style={{ display: 'flex', gap: '6px', alignItems: 'center', justifyContent: 'space-between' }}>
                      <div className="console-field" style={{ flex: 1 }}>
                        <span className="console-field-label">OUT VOL ({vocalVolume})</span>
                        <input 
                          type="range" 
                          min="0" 
                          max="10" 
                          step="1" 
                          value={vocalVolume} 
                          onChange={(e) => setVocalVolume(Number(e.target.value))}
                          style={{ width: '100%', height: '8px', cursor: 'pointer', accentColor: 'var(--color-amber-glow)' }}
                        />
                      </div>
                      <div className="knob-container">
                        <div className="knob-dial-wrapper">
                          <div className="knob-ticks" />
                          <div 
                            className="knob-rotator" 
                            style={{ transform: `rotate(${getVolumeKnobAngle(vocalVolume)}deg)` }}
                          >
                            <div className="knob-pointer" />
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '8px' }}>
                    <div className="lever-selector-mini" style={{ width: '100%' }}>
                      <span className="lever-selector-text">TREBLE BOOST</span>
                      <label className="toggle-lever">
                        <input
                          type="checkbox"
                          checked={vocalBoost}
                          onChange={(e) => setVocalBoost(e.target.checked)}
                        />
                        <div className="switch-track">
                          <div className="switch-lever" />
                        </div>
                      </label>
                    </div>
                  </div>

                  <label className={`tape-deck-zone ${draggingVocal ? 'dragging' : ''}`} {...createDragHandlers(setDraggingVocal, setVocalFile)}>
                    <span className="tape-deck-icon">🎙️</span>
                    <span className="tape-deck-text">{vocalFile ? vocalFile.name : UI_TEXT.vocalSeparator.dragPrompt}</span>
                    <input
                      type="file"
                      accept=".wav,.mp3,.flac,.m4a,.aac,audio/*"
                      onChange={(event) => setVocalFile(event.target.files?.[0] ?? null)}
                    />
                  </label>
                  <button type="submit" className="console-btn btn-accent btn-wide" disabled={busy || jobRunning}>
                    {busy ? UI_TEXT.vocalSeparator.buttonBusy : UI_TEXT.vocalSeparator.buttonStart}
                  </button>
                </form>
              </div>
            ) : (!isMobile ? (
              <div className="blind-panel short-channel">
                <div className="screw top-left" />
                <div className="screw top-right" />
                <div className="screw bottom-left" />
                <div className="screw bottom-right" />
                <div className="blind-panel-text">{UI_TEXT.global.emptyRackSlot} - CH 03</div>
              </div>
            ) : null)}

            {/* CH 04: STEMS SEPARATOR */}
            {(!isMobile && showStemsSep) || (isMobile && activeMobileModule === 'stems') ? (
              <div className="channel-strip">
                <div className="screw top-left" />
                <div className="screw top-right" />
                <div className="screw bottom-left" />
                <div className="screw bottom-right" />
                <div className="channel-strip-header">
                  <h2>🥁 {UI_TEXT.stemsSeparator.title}</h2>
                  <span className="ch-number">CH 04</span>
                </div>
                <p className="channel-desc">{UI_TEXT.stemsSeparator.desc}</p>
                
                <form
                  style={{ display: 'flex', flexDirection: 'column', gap: '12px', marginTop: 'auto' }}
                  onSubmit={(event) => {
                    event.preventDefault();
                    if (!instrumentFile) {
                      setError('請先選擇要做樂器分離的音訊檔');
                      return;
                    }
                    if (selectedInstruments.length === 0) {
                      setError('請至少選擇一個要分離的聲部');
                      return;
                    }
                    void runAction(() => separateInstruments(instrumentFile, selectedInstruments, instrumentQuality));
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '10px' }}>
                    <div className="console-field" style={{ flex: 1 }}>
                      <span className="console-field-label">{UI_TEXT.stemsSeparator.qualityLabel}</span>
                      <select className="console-select" value={instrumentQuality} onChange={(event) => setInstrumentQuality(event.target.value)}>
                        {QUALITY_OPTIONS.map((option) => (
                          <option key={option.value} value={option.value}>
                            {option.label}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className="knob-container" style={{ alignSelf: 'flex-end', padding: '0 10px' }}>
                      <div className="knob-dial-wrapper" title={QUALITY_OPTIONS.find((option) => option.value === instrumentQuality)?.description}>
                        <div className="knob-ticks" />
                        <div 
                          className="knob-rotator" 
                          style={{ transform: `rotate(${getQualityKnobAngle(instrumentQuality)}deg)` }}
                        >
                          <div className="knob-pointer" />
                        </div>
                      </div>
                    </div>
                  </div>

                  <div style={{ display: 'flex', gap: '8px' }}>
                    <button type="button" className="console-btn" style={{ flex: 1, padding: '4px 8px', minHeight: '28px' }} onClick={() => setSelectedInstruments(INSTRUMENT_OPTIONS.map((option) => option.value))}>
                      {UI_TEXT.stemsSeparator.selectAll}
                    </button>
                    <button type="button" className="console-btn" style={{ flex: 1, padding: '4px 8px', minHeight: '28px' }} onClick={() => setSelectedInstruments([])}>
                      {UI_TEXT.stemsSeparator.clearAll}
                    </button>
                  </div>
                  
                  <div className="stems-panel" aria-label="選擇要分離的聲部">
                    {INSTRUMENT_OPTIONS.map((option) => (
                      <div className="stem-switch-wrapper" key={option.value}>
                        <span className="stem-switch-label">{option.label}</span>
                        <label className="toggle-lever">
                          <input
                            type="checkbox"
                            checked={selectedInstruments.includes(option.value)}
                            onChange={() => toggleInstrument(option.value)}
                          />
                          <div className="switch-track">
                            <div className="switch-lever" />
                          </div>
                        </label>
                      </div>
                    ))}
                  </div>

                  <label className={`tape-deck-zone ${draggingInstrument ? 'dragging' : ''}`} {...createDragHandlers(setDraggingInstrument, setInstrumentFile)}>
                    <span className="tape-deck-icon">🥁</span>
                    <span className="tape-deck-text">{instrumentFile ? instrumentFile.name : UI_TEXT.stemsSeparator.dragPrompt}</span>
                    <input
                      type="file"
                      accept=".wav,.mp3,.flac,.m4a,.aac,audio/*"
                      onChange={(event) => setInstrumentFile(event.target.files?.[0] ?? null)}
                    />
                  </label>
                  <button type="submit" className="console-btn btn-wide" disabled={busy || jobRunning}>
                    {busy ? UI_TEXT.stemsSeparator.buttonBusy : UI_TEXT.stemsSeparator.buttonStart}
                  </button>
                </form>
              </div>
            ) : (!isMobile ? (
              <div className="blind-panel">
                <div className="screw top-left" />
                <div className="screw top-right" />
                <div className="screw bottom-left" />
                <div className="screw bottom-right" />
                <div className="blind-panel-text">{UI_TEXT.global.emptyRackSlot} - CH 04</div>
              </div>
            ) : null)}
          </div>
          )}

          {/* 只有在非手機端，或者在手機端且有選中 CH 05 時才渲染此 unit */}
          {(!isMobile || activeMobileModule === 'pitch') && (
            <div className="pitch-tempo-rack-unit">
              {/* CH 05: PITCH & TEMPO */}
              {(!isMobile && showPitch) || (isMobile && activeMobileModule === 'pitch') ? (
              <div className="channel-strip">
                <div className="screw top-left" />
                <div className="screw top-right" />
                <div className="screw bottom-left" />
                <div className="screw bottom-right" />
                <div className="channel-strip-header">
                  <h2>🎵 {UI_TEXT.pitch.title}</h2>
                  <span className="ch-number">CH 05</span>
                </div>
                <p className="channel-desc">{UI_TEXT.pitch.desc}</p>
                
                <form
                  style={{ display: 'flex', flexDirection: 'column', gap: '12px', marginTop: 'auto' }}
                  onSubmit={(event) => {
                    event.preventDefault();
                    if (!analysis) {
                      setError('請先上傳並分析音訊');
                      return;
                    }
                    const bpm = Number(targetBpm);
                    if (!Number.isFinite(bpm) || bpm <= 0) {
                      setError('請輸入有效的目標 BPM');
                      return;
                    }
                    void runAction(() => transformAudio(analysis.file_id, semitones, bpm));
                  }}
                >
                  <label className={`tape-deck-zone ${draggingTransform ? 'dragging' : ''}`} {...createDragHandlers(setDraggingTransform, (f) => { setTransformFile(f); setAnalysis(null); })}>
                    <span className="tape-deck-icon">🎛️</span>
                    <span className="tape-deck-text">{transformFile ? transformFile.name : UI_TEXT.pitch.dragPrompt}</span>
                    <input
                      type="file"
                      accept=".wav,.mp3,.flac,.m4a,.aac,audio/*"
                      onChange={(event) => {
                        setTransformFile(event.target.files?.[0] ?? null);
                        setAnalysis(null);
                      }}
                    />
                  </label>
                  
                  <button type="button" className="console-btn btn-accent btn-wide" disabled={analyzing || !transformFile || jobRunning} onClick={() => void runAnalyze()}>
                    {analyzing ? UI_TEXT.pitch.buttonAnalyzing : UI_TEXT.pitch.buttonAnalyze}
                  </button>
                  
                  <div className="studio-analysis-display">
                    <div className="analysis-item">
                      <span>{UI_TEXT.pitch.keyCurrent}</span>
                      <strong>{currentKey}</strong>
                    </div>
                    <div className="analysis-item">
                      <span>{UI_TEXT.pitch.keyAdjusted}</span>
                      <strong>{adjustedKey}</strong>
                    </div>
                    <div className="analysis-item">
                      <span>{UI_TEXT.pitch.bpmOriginal}</span>
                      <strong>{analysis?.bpm ?? UI_TEXT.pitch.notAnalyzed}</strong>
                    </div>
                    <div className="analysis-item">
                      <span>{UI_TEXT.pitch.bpmTarget}</span>
                      <strong>{adjustedBpm || UI_TEXT.pitch.notSet}</strong>
                    </div>
                  </div>
                  
                  <div className="fader-section">
                    <span className="console-field-label" style={{ width: '100%', textAlign: 'center' }}>
                      {UI_TEXT.pitch.semitonesLabel}
                      <div className="fader-value-num" style={{ marginTop: '4px', fontSize: '1.2rem', color: 'var(--color-amber-glow)', fontFamily: 'var(--font-mono)' }}>
                        {semitones > 0 ? `+${semitones}` : semitones}
                      </div>
                    </span>
                    
                    {/* Skeuomorphic Vertical Fader */}
                    <div className="fader-scale-container">
                      <div className="fader-scale-lines" />
                      <div className="fader-scale-labels">
                        <span>+12</span>
                        <span>+6</span>
                        <span>0</span>
                        <span>-6</span>
                        <span>-12</span>
                      </div>
                      <div className="console-fader-input-wrapper">
                        <input
                          type="range"
                          min="-12"
                          max="12"
                          step="1"
                          value={semitones}
                          onChange={(event) => setSemitones(Number(event.target.value))}
                        />
                      </div>
                      <div className="fader-scale-labels right">
                        <span>ST</span>
                        <span>--</span>
                        <span>--</span>
                        <span>--</span>
                        <span>ST</span>
                      </div>
                    </div>
                  </div>
                  
                  <div className="console-field">
                    <span className="console-field-label">{UI_TEXT.pitch.bpmLabel}</span>
                    <input
                      className="console-input-text"
                      type="number"
                      min="1"
                      step="0.1"
                      value={targetBpm}
                      onChange={(event) => setTargetBpm(event.target.value)}
                    />
                  </div>
                  
                  <button type="submit" className="console-btn btn-wide" disabled={busy || !analysis || jobRunning}>
                    {busy ? UI_TEXT.wavConverter.buttonBusy : UI_TEXT.pitch.buttonStart}
                  </button>
                </form>
              </div>
            ) : (!isMobile ? (
              <div className="blind-panel">
                <div className="screw top-left" />
                <div className="screw top-right" />
                <div className="screw bottom-left" />
                <div className="screw bottom-right" />
                <div className="blind-panel-text">{UI_TEXT.global.emptyRackSlot} - CH 05</div>
              </div>
            ) : null)}
            </div>
          )}
            </div> {/* main-rack end */}

            {/* Right Column: 狀態監控與廣告面板 */}
            <div className="sidebar-rack">
              {/* LCD DISPLAY STATUS */}
              <div className={`lcd-container ${jobRunning ? 'processing' : ''}`}>
                <div className="screw top-left" />
                <div className="screw top-right" />
                <div className="screw bottom-left" />
                <div className="screw bottom-right" />
                <div className="lcd-display">
                  <div className="lcd-header">{UI_TEXT.status.title}</div>
                  
                  {!job || job.status === 'finished' ? (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                      <div className="lcd-text">{UI_TEXT.status.noJob}</div>
                      {job?.status === 'finished' && (
                        <div className="lcd-text" style={{ fontSize: '0.75rem', color: '#00ff66', opacity: 0.85 }}>
                          SUCCESS: {job.kind?.toUpperCase()} COMPLETED
                        </div>
                      )}
                    </div>
                  ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                      <div className="lcd-text">
                        <strong>JOB KND: </strong>{job.kind?.toUpperCase()}
                      </div>
                       <div className="lcd-text">
                        <strong>STATUS: </strong>{
                          job.status === 'queued' && job.queue_position && job.queue_position > 0
                            ? `QUEUED (排隊中，前方還有 ${job.queue_position - 1} 個任務)`
                            : statusLabel(job).toUpperCase()
                        }
                      </div>
                      <div className="lcd-text">
                        <strong>JOB ID: </strong>{job.id}
                      </div>
                      {job.output_name && (
                        <div className="lcd-text">
                          <strong>OUTPUT: </strong>{job.output_name}
                        </div>
                      )}
                      {/* ASCII Progress bar in LCD */}
                      <div className="lcd-progress-bar">
                        <div className="lcd-progress-fill">{renderLcdProgress()}</div>
                      </div>
                    </div>
                  )}

                  {/* Red LED indicator style panels for errors */}
                  {error && <div className="alert-led-panel">SYSTEM ERR: {error}</div>}
                  {job?.error && <div className="alert-led-panel">JOB ERR: {job.error}</div>}
                </div>

                {/* Tape Eject style download button */}
                {currentDownloadUrl && (
                  <div style={{ marginTop: '10px', display: 'flex' }}>
                    <a className="cassette-eject" href={currentDownloadUrl}>
                      {downloadLabel}
                    </a>
                  </div>
                )}
              </div>

              {/* JOB HISTORY PANEL */}
              <div className="lcd-container">
                <div className="screw top-left" />
                <div className="screw top-right" />
                <div className="screw bottom-left" />
                <div className="screw bottom-right" />
                <div className="lcd-display">
                  <div className="lcd-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span>TASK HISTORY / JOB LOG</span>
                    <button
                      className="cassette-eject"
                      style={{ padding: '2px 10px', fontSize: '10px' }}
                      onClick={() => setHistoryOpen(o => !o)}
                    >
                      {historyOpen ? '▲ HIDE' : '▼ SHOW'}
                    </button>
                  </div>
                  {historyOpen && (
                    history.length === 0
                      ? <div className="lcd-text" style={{ marginTop: '6px' }}>NO RECORDS FOUND</div>
                      : <div style={{ marginTop: '6px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
                          {history.map(j => (
                            <div key={j.id} className="lcd-text history-row">
                              <span className="history-kind">{(j.kind ?? 'JOB').toUpperCase().replace(/_/g, ' ')}</span>
                              <span className={`history-status ${j.status}`}>{j.status.toUpperCase()}</span>
                              {j.output_name && <span className="history-file">{j.output_name}</span>}
                              <span style={{ marginLeft: 'auto', display: 'flex', gap: '6px', alignItems: 'center', flexShrink: 0 }}>
                                {j.download_url && (
                                  <a className="cassette-eject" style={{ padding: '1px 8px', fontSize: '9px' }} href={`${API_BASE}${j.download_url}`}>
                                    DL
                                  </a>
                                )}
                                <button
                                  className="cassette-eject"
                                  style={{ padding: '1px 8px', fontSize: '9px', background: 'rgba(255,59,48,0.15)', borderColor: 'rgba(255,59,48,0.4)', color: '#ff3b30' }}
                                  onClick={() => void handleDeleteJob(j.id)}
                                >
                                  DEL
                                </button>
                              </span>
                            </div>
                          ))}
                        </div>
                  )}
                </div>
              </div>

              {/* AD-MODULE 1: VU METER GOOGLE AD SLOT */}
              <div className="ad-module-container ad-module-vu">
                <div className="screw top-left" />
                <div className="screw top-right" />
                <div className="screw bottom-left" />
                <div className="screw bottom-right" />
                
                <div className="ad-module-header">
                  <span>SYSTEM SPONSOR</span>
                  <span>AD-MODULE 1</span>
                </div>
                
                {/* Fallback Blind Panel (Visible when adblocked or no ad loaded) */}
                <div className="ad-blind-fallback">
                  <div className="ad-blind-text">SPONSOR AD</div>
                  <div className="ad-blind-text" style={{ fontSize: '0.55rem', opacity: 0.6 }}>SYSTEM NOISE GATE</div>
                  <div className="ad-blind-subtext">POWER BY GOOGLE</div>
                </div>
                
                {/* Simulated VU Meter (Aesthetic background) */}
                <div className="simulated-vu-display">
                  <svg className="vu-face-svg" viewBox="0 0 300 200">
                    <path className="vu-dial-path" d="M 30,190 A 130,130 0 0,1 270,190" />
                    <text x="50" y="145" className="vu-scale-text">-20</text>
                    <text x="90" y="100" className="vu-scale-text">-10</text>
                    <text x="150" y="80" className="vu-scale-text">0</text>
                    <text x="210" y="100" className="vu-scale-text">+3</text>
                    <text x="250" y="145" className="vu-scale-text" fill="#ff3b30">+6</text>
                    <text x="150" y="180" className="vu-scale-text" style={{ fontSize: '10px', fontWeight: 'bold' }}>VU</text>
                    <line className="vu-needle-simulated" x1="150" y1="200" x2="150" y2="40" />
                  </svg>
                </div>
                
                {/* Real AdSense Container */}
                <div 
                  id="google-ad-sidebar-container" 
                  style={{ position: 'absolute', top: '36px', left: '10px', right: '10px', bottom: '10px', zIndex: 2, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
                  aria-label={UI_TEXT.status.adLabel}
                  title="未來放置 300x250 Google 廣告直立看板處"
                >
                  {/* AdSense Code Placeholder for production:
                  <ins className="adsbygoogle"
                       style={{display: 'inline-block', width: '300px', height: '250px'}}
                       data-ad-client="ca-pub-XXXXXXXXXXXXXXXX"
                       data-ad-slot="XXXXXXXXXX"></ins>
                  <script>(adsbygoogle = window.adsbygoogle || []).push({});</script>
                  */}
                </div>
              </div>
            </div>
          </div>

          {/* AD-MODULE 2: BASE POWER STRIP */}
          <div className="ad-module-power">
            <div className="screw top-left" />
            <div className="screw top-right" />
            <div className="screw bottom-left" />
            <div className="screw bottom-right" />

            <div className="power-switch-analog">
              <div className="power-switch-rocker" />
            </div>

            <div className="ad-banner-frame">
              {/* Fallback Blind Panel */}
              <div className="ad-blind-fallback" style={{ top: 0, left: 0, right: 0, bottom: 0, border: 'none' }}>
                <div className="ad-blind-text" style={{ fontSize: '0.62rem', letterSpacing: '4px' }}>
                  ANALOG AC POWER DISTRIBUTION STRIP &bull; SPONSOR SECTION
                </div>
              </div>

              {/* Real Ad Container */}
              <div 
                id="google-ad-banner-container" 
                style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, zIndex: 2, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
                aria-label={UI_TEXT.status.adLabel}
                title="未來放置 728x90 Google 廣告橫幅處"
              >
                {/* AdSense Code Placeholder for production:
                <ins className="adsbygoogle"
                     style={{display: 'inline-block', width: '728px', height: '90px'}}
                     data-ad-client="ca-pub-XXXXXXXXXXXXXXXX"
                     data-ad-slot="XXXXXXXXXX"></ins>
                <script>(adsbygoogle = window.adsbygoogle || []).push({});</script>
                */}
              </div>
            </div>

            <div className="power-sockets-group">
              <div className="simulated-socket" />
              <div className="simulated-socket" />
              <div className="simulated-socket" />
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}

function transposeKey(tonic: string, mode: string, semitones: number): string {
  const index = NOTES.indexOf(tonic);
  if (index < 0) return formatKey(tonic, mode);
  const shifted = (index + semitones + 1200) % 12;
  return formatKey(NOTES[shifted], mode);
}

function formatKey(tonic: string, mode: string): string {
  const enharmonic = ENHARMONIC_NOTES[tonic];
  const key = `${tonic} ${mode}`;
  return enharmonic ? `${key} (${enharmonic} ${mode})` : key;
}

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
