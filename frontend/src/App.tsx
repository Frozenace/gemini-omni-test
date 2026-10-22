import React, { useState, useRef, useEffect, useCallback } from 'react';
import './index.css';

interface SceneItem {
  id: string;
  title: string;
  act: string;
  location: string;
  image_prompt: string;
  video_prompt: string;
  candidates: string[];
  winner_url?: string | null;
  preview_video_url?: string | null;
  video_url?: string | null;
  judge_verdict?: any;
  status?: string;
}

export default function App() {
  const [activeView, setActiveView] = useState<'cinema' | 'kiosk'>('cinema');
  const [storyboard, setStoryboard] = useState<{
    film_title: string;
    logline: string;
    master_video_url?: string | null;
    verification?: any;
    scenes: SceneItem[];
  } | null>(null);

  // Interactive Kiosk State (Codelab + Driver Name Replacement)
  const [driverName, setDriverName] = useState<string>('Toshiro Sakamoto');
  const [inputMode, setInputMode] = useState<'camera' | 'upload'>('upload');
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [cameraActive, setCameraActive] = useState<boolean>(false);
  const [cameraError, setCameraError] = useState<string | null>(null);

  const [option, setOption] = useState('podium_celebration');
  const [jobId, setJobId] = useState<string | null>(null);
  const [status, setStatus] = useState<string>('');
  const [stage, setStage] = useState<string>('');
  const [progressPct, setProgressPct] = useState<number>(0);
  const [resultUrl, setResultUrl] = useState<string | null>(null);
  const [previewVideoUrl, setPreviewVideoUrl] = useState<string | null>(null);
  const [avatarUrl, setAvatarUrl] = useState<string | null>(null);
  const [candidates, setCandidates] = useState<string[]>([]);
  const [verification, setVerification] = useState<any>(null);
  const [scenesProgress, setScenesProgress] = useState<Record<string, string> | null>(null);
  const [executionMode, setExecutionMode] = useState<string | null>(null);

  const videoRef = useRef<HTMLVideoElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);

  const apiBase = (import.meta as any).env?.VITE_API_BASE || '';

  const fetchStoryboard = useCallback(async () => {
    try {
      const res = await fetch(`${apiBase}/api/storyboard`);
      if (res.ok) {
        const data = await res.json();
        setStoryboard(data);
      }
    } catch (err) {
      console.error('Failed to load storyboard:', err);
    }
  }, [apiBase]);

  useEffect(() => {
    fetchStoryboard();
  }, [fetchStoryboard]);

  const stopCamera = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
    setCameraActive(false);
  }, []);

  const startCamera = useCallback(async () => {
    stopCamera();
    setCameraError(null);
    try {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        throw new Error('Camera is not supported on this browser or device.');
      }
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          width: { ideal: 1280 },
          height: { ideal: 720 },
          facingMode: 'user',
        },
        audio: false,
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
      setCameraActive(true);
    } catch (err: any) {
      setCameraError(
        err.message || 'Unable to access camera. Please check permissions or switch to file upload.'
      );
      setCameraActive(false);
    }
  }, [stopCamera]);

  useEffect(() => {
    if (activeView === 'kiosk' && inputMode === 'camera' && !file && !jobId) {
      startCamera();
    } else {
      stopCamera();
    }
    return () => {
      stopCamera();
    };
  }, [activeView, inputMode, file, jobId, startCamera, stopCamera]);

  const handleCapture = () => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas) return;

    const width = video.videoWidth || 640;
    const height = video.videoHeight || 480;
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    ctx.translate(width, 0);
    ctx.scale(-1, 1);
    ctx.drawImage(video, 0, 0, width, height);

    canvas.toBlob(
      (blob) => {
        if (!blob) return;
        const capturedFile = new File([blob], `driver_photo_${Date.now()}.jpg`, {
          type: 'image/jpeg',
        });
        setFile(capturedFile);
        setPreviewUrl(URL.createObjectURL(blob));
        stopCamera();
      },
      'image/jpeg',
      0.95
    );
  };

  const handleRetake = () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setFile(null);
    setPreviewUrl(null);
    if (inputMode === 'camera') startCamera();
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0] || null;
    if (selected) {
      setFile(selected);
      if (previewUrl) URL.revokeObjectURL(previewUrl);
      setPreviewUrl(URL.createObjectURL(selected));
    }
  };

  const handleModeChange = (mode: 'camera' | 'upload') => {
    if (mode === inputMode) return;
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setFile(null);
    setPreviewUrl(null);
    setInputMode(mode);
  };

  const handleUpload = async () => {
    if (!file) return;
    stopCamera();

    const formData = new FormData();
    formData.append('file', file);
    formData.append('option', option);
    formData.append('driver_name', driverName || 'Toshiro Sakamoto');

    const res = await fetch(`${apiBase}/api/process-driver`, { method: 'POST', body: formData });
    const data = await res.json();
    setJobId(data.job_id);
    setStatus('processing');
    setStage('Queued pipeline...');
    pollJob(data.job_id);
  };

  const handleGenerateFullFilm = async () => {
    const formData = new FormData();
    formData.append('driver_name', driverName || 'Toshiro Sakamoto');
    const res = await fetch(`${apiBase}/api/generate-full-film`, {
      method: 'POST',
      body: formData,
    });
    const data = await res.json();
    setJobId(data.job_id);
    setStatus('processing');
    setStage('Starting 6-Scene 35mm Film Fan-Out Pipeline...');
    pollJob(data.job_id);
  };

  const pollJob = (id: string) => {
    const interval = window.setInterval(async () => {
      try {
        const res = await fetch(`${apiBase}/api/job/${id}`);
        const data = await res.json();
        setStatus(data.status);
        setStage(data.stage);
        if (typeof data.progress_pct === 'number') setProgressPct(data.progress_pct);
        if (data.preview_video_url) setPreviewVideoUrl(data.preview_video_url);
        if (data.avatar_url) setAvatarUrl(data.avatar_url);
        if (data.candidates?.length) setCandidates(data.candidates);
        if (data.verification) setVerification(data.verification);
        if (data.scenes_progress) setScenesProgress(data.scenes_progress);
        if (data.execution_mode) setExecutionMode(data.execution_mode);

        // Refresh storyboard while 6-scene fan-out is running so scene cards animate live
        if (id.startsWith('film-')) {
          fetchStoryboard();
        }

        if (data.status === 'completed') {
          setResultUrl(data.result_url);
          clearInterval(interval);
          fetchStoryboard();
        } else if (data.status === 'failed') {
          clearInterval(interval);
        }
      } catch (err) {
        console.error('Error polling job:', err);
      }
    }, 1500);
  };

  const handleReset = () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setFile(null);
    setPreviewUrl(null);
    setJobId(null);
    setStatus('');
    setStage('');
    setProgressPct(0);
    setResultUrl(null);
    setPreviewVideoUrl(null);
    setAvatarUrl(null);
    setCandidates([]);
    setVerification(null);
    setScenesProgress(null);
    setExecutionMode(null);
  };

  return (
    <div>
      <header className="fe-header liquid-glass">
        <div className="brand-badge">
          <div className="brand-orb" />
          <span style={{ fontWeight: 500, letterSpacing: '0.06em', fontSize: '0.95rem' }}>
            ALBION ELECTRIC RACING • GEN4 STUDIO
          </span>
        </div>
        <div style={{ display: 'flex', gap: '0.6rem' }}>
          <button
            type="button"
            className={`fe-tab-btn ${activeView === 'cinema' ? 'active' : ''}`}
            onClick={() => setActiveView('cinema')}
          >
            🎞️ 35mm Film & Storyboard
          </button>
          <button
            type="button"
            className={`fe-tab-btn ${activeView === 'kiosk' ? 'active' : ''}`}
            onClick={() => setActiveView('kiosk')}
          >
            🏎️ Step Into Toshiro’s Helmet
          </button>
        </div>
      </header>

      <main className="fe-container">
        <section className="hero-banner">
          <span className="hero-eyebrow">35MM KODAK VISION3 • 600KW GEN4 ACTIVE AWD • TOKYO BIG SIGHT</span>
          <h1 className="hero-title">Sakura in the Slipstream</h1>
          <p className="hero-subtitle">
            {storyboard?.logline ||
              'Dropped from Formula 2 after family sponsorship ran out, young Japanese driver Toshiro Sakamoto rebuilds his career in the rainy UK alongside Momoko—returning home to Tokyo Big Sight in a 600kW Formula E GEN4 machine.'}
          </p>
        </section>

        {activeView === 'cinema' ? (
          <div>
            {/* Master Film Player Card */}
            <div className="fe-card liquid-glass" style={{ textAlign: 'center' }}>
              <h2 style={{ marginTop: 0, fontWeight: 500 }}>
                Master 35mm Short Film — Starring {driverName || 'Toshiro Sakamoto'} & Momoko
              </h2>
              <p style={{ color: '#94a3b8', fontSize: '0.95rem', marginBottom: '1.5rem' }}>
                Soundtrack: Neo-Noir Analog CS-80 Brass Synth × Futuristic J-Pop Electro-Synthwave
              </p>

              {storyboard?.master_video_url || resultUrl ? (
                <video
                  src={resultUrl || storyboard?.master_video_url || ''}
                  controls
                  autoPlay
                  loop
                  style={{
                    width: '100%',
                    maxWidth: '760px',
                    borderRadius: '20px',
                    border: '1px solid rgba(255,255,255,0.18)',
                  }}
                />
              ) : (
                <div
                  style={{
                    padding: '2.5rem 1.5rem',
                    borderRadius: '20px',
                    background: 'rgba(6, 9, 17, 0.55)',
                    border: '1px dashed rgba(255,255,255,0.18)',
                    marginBottom: '1.5rem',
                  }}
                >
                  <p style={{ color: '#cbd5e1', marginBottom: '1.2rem' }}>
                    Ready to execute the parallel 6-scene Multimodal Chaining Pipeline (4x concurrent Nano Banana keyframes per scene → Visual Judge → Live 35mm Motion Preview → Gemini Omni 8s 60fps Video → FFmpeg Master Cut + 35mm Ending Slate).
                  </p>
                  <button
                    type="button"
                    className="fe-btn"
                    onClick={handleGenerateFullFilm}
                    disabled={status === 'processing'}
                  >
                    {status === 'processing'
                      ? `⚡ ${stage}`
                      : '🎬 GENERATE FULL 6-SCENE 35MM FILM (PARALLEL FAN-OUT)'}
                  </button>

                  {status === 'processing' && (
                    <div style={{ marginTop: '1.4rem' }}>
                      <div className="fe-progress-track">
                        <div className="fe-progress-bar" style={{ width: `${Math.max(8, progressPct)}%` }} />
                      </div>
                      {scenesProgress && (
                        <div className="scene-status-grid">
                          {Object.entries(scenesProgress).map(([sKey, sState]) => (
                            <span
                              key={sKey}
                              className={`scene-status-pill ${
                                sState === 'completed' ? 'done' : sState !== 'queued' ? 'active' : ''
                              }`}
                            >
                              {sKey}: {sState}
                            </span>
                          ))}
                        </div>
                      )}
                      {(previewVideoUrl || avatarUrl) && (
                        <div className="ken-burns-viewport">
                          {previewVideoUrl ? (
                            <video
                              src={previewVideoUrl}
                              autoPlay
                              loop
                              muted
                              playsInline
                              style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                            />
                          ) : (
                            <img src={avatarUrl!} alt="35mm Live Preview" className="ken-burns-img" />
                          )}
                          <div className="film-hud-badge">
                            ● LIVE 35MM TAKE STREAMING ({executionMode || 'PARALLEL'})
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}

              {(storyboard?.verification || verification) && (
                <div
                  style={{
                    marginTop: '1.2rem',
                    padding: '1rem 1.4rem',
                    borderRadius: '16px',
                    background: 'rgba(0, 229, 255, 0.08)',
                    border: '1px solid rgba(0, 229, 255, 0.25)',
                    textAlign: 'left',
                    fontSize: '0.9rem',
                  }}
                >
                  <strong>✅ Multimodal Judge Verification Verdict:</strong>{' '}
                  {(verification || storyboard?.verification)?.summary_critique}
                </div>
              )}
            </div>

            {/* 6-Scene Storyboard Grid */}
            <div className="scene-grid">
              {(storyboard?.scenes || []).map((scene) => (
                <div key={scene.id} className="scene-card liquid-glass">
                  <div>
                    <div className="scene-act">{scene.act}</div>
                    <h3 className="scene-title">{scene.title}</h3>
                    <div className="scene-location">📍 {scene.location}</div>

                    <div className="scene-prompt-box">
                      <strong>35mm Keyframe Direction:</strong>
                      <div style={{ marginTop: '0.3rem' }}>{scene.image_prompt}</div>
                    </div>

                    {(scene.video_url || scene.preview_video_url || scene.winner_url) && (
                      <div style={{ marginBottom: '0.8rem', position: 'relative', borderRadius: '12px', overflow: 'hidden' }}>
                        {scene.video_url || scene.preview_video_url ? (
                          <video
                            src={scene.video_url || scene.preview_video_url || ''}
                            autoPlay
                            loop
                            muted
                            playsInline
                            controls={Boolean(scene.video_url)}
                            style={{ width: '100%', borderRadius: '12px', display: 'block' }}
                          />
                        ) : (
                          <img
                            src={scene.winner_url!}
                            alt={scene.title}
                            className="ken-burns-img"
                            style={{ width: '100%', borderRadius: '12px', display: 'block' }}
                          />
                        )}
                      </div>
                    )}

                    {scene.candidates && scene.candidates.length > 0 && (
                      <div>
                        <span style={{ fontSize: '0.78rem', color: '#94a3b8' }}>
                          4 Nano Banana Candidates (Judge Winner Highlighted):
                        </span>
                        <div className="candidate-strip">
                          {scene.candidates.map((cUrl, idx) => (
                            <img
                              key={idx}
                              src={cUrl}
                              alt={`Candidate ${idx + 1}`}
                              className="candidate-thumb"
                              style={{
                                borderColor:
                                  cUrl === scene.winner_url ? '#00e5ff' : 'rgba(255,255,255,0.15)',
                              }}
                            />
                          ))}
                        </div>
                      </div>
                    )}
                  </div>

                  <div style={{ marginTop: '0.8rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontSize: '0.8rem', color: '#f472b6' }}>8s • 60fps HD • Chained ID</span>
                    <button
                      type="button"
                      className="fe-btn-secondary"
                      onClick={() => {
                        setOption(scene.id);
                        setActiveView('kiosk');
                      }}
                    >
                      Star in This Scene →
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : (
          /* Interactive Kiosk View: Replace Toshiro with Your Own Photo & Name */
          <div>
            {!jobId ? (
              <div className="fe-card liquid-glass" style={{ textAlign: 'center' }}>
                <h2 style={{ marginTop: 0, fontWeight: 500 }}>
                  Step Into the GEN4 Cockpit (Replace Toshiro with Yourself)
                </h2>
                <p style={{ color: '#94a3b8', marginBottom: '1.8rem' }}>
                  Upload or snap your portrait, enter your driver name, and our Multimodal Chaining Pipeline will cast you alongside Momoko and the 600kW Albion GEN4 race car on 35mm film.
                </p>

                <div style={{ marginBottom: '1.8rem' }}>
                  <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.95rem', color: '#cbd5e1' }}>
                    Driver Name (Replaces Toshiro Sakamoto in Scene & Ending Credits):
                  </label>
                  <input
                    type="text"
                    className="fe-input"
                    value={driverName}
                    onChange={(e) => setDriverName(e.target.value)}
                    placeholder="Enter your name (e.g., Toshiro Sakamoto)"
                  />
                </div>

                <h3>Step 1: Take or Upload Your Driver Portrait</h3>
                <div className="fe-tabs">
                  <button
                    type="button"
                    className={`fe-tab-btn ${inputMode === 'camera' ? 'active' : ''}`}
                    onClick={() => handleModeChange('camera')}
                  >
                    📷 Take Photo
                  </button>
                  <button
                    type="button"
                    className={`fe-tab-btn ${inputMode === 'upload' ? 'active' : ''}`}
                    onClick={() => handleModeChange('upload')}
                  >
                    📁 Upload Photo
                  </button>
                </div>

                {inputMode === 'camera' && (
                  <div className="fe-camera-container">
                    {cameraError && (
                      <div className="fe-alert">
                        <p>{cameraError}</p>
                        <button
                          type="button"
                          className="fe-btn-secondary"
                          onClick={startCamera}
                          style={{ marginTop: '0.5rem' }}
                        >
                          Try Camera Again
                        </button>
                      </div>
                    )}

                    <div className="fe-camera-feed-box">
                      {!file ? (
                        <video ref={videoRef} className="fe-video" autoPlay playsInline muted />
                      ) : (
                        previewUrl && (
                          <img src={previewUrl} alt="Captured Driver" className="fe-captured-img" />
                        )
                      )}
                    </div>

                    <canvas ref={canvasRef} style={{ display: 'none' }} />

                    <div style={{ marginTop: '1rem', display: 'flex', gap: '0.75rem', justifyContent: 'center' }}>
                      {!file ? (
                        <button
                          type="button"
                          className="fe-btn"
                          onClick={handleCapture}
                          disabled={!cameraActive}
                        >
                          📸 Snap Photo
                        </button>
                      ) : (
                        <button type="button" className="fe-btn-secondary" onClick={handleRetake}>
                          🔄 Retake Photo
                        </button>
                      )}
                    </div>
                  </div>
                )}

                {inputMode === 'upload' && (
                  <div className="fe-file-picker">
                    {!file ? (
                      <input type="file" accept="image/*" onChange={handleFileChange} />
                    ) : (
                      <div>
                        {previewUrl && (
                          <div className="fe-camera-feed-box" style={{ margin: '0 auto 1rem auto' }}>
                            <img src={previewUrl} alt="Uploaded Driver" className="fe-captured-img" />
                          </div>
                        )}
                        <button type="button" className="fe-btn-secondary" onClick={handleRetake}>
                          Choose Different Photo
                        </button>
                      </div>
                    )}
                  </div>
                )}

                <h3 style={{ marginTop: '1.8rem' }}>Step 2: Choose Your 35mm Scene</h3>
                <select
                  value={option}
                  onChange={(e) => setOption(e.target.value)}
                  className="fe-input"
                >
                  <option value="uk_rain_handoff">🌧️ Scene 01: Rainy UK Helmet Handoff with Momoko</option>
                  <option value="uk_simulator_night">🖥️ Scene 02: Late-Night UK Factory GEN4 Simulator</option>
                  <option value="tokyo_paddock_arrival">🌸 Scene 03: Tokyo Big Sight Sakura Paddock Walk</option>
                  <option value="pit_lane_launch">⚡ Scene 04: Tokyo Grid 600kW Active-AWD Launch</option>
                  <option value="sakura_vortex">🌪️ Scene 05: 208mph Ariake Sakura Slipstream Vortex</option>
                  <option value="podium_celebration">🏆 Scene 06: Parc Fermé Victory Embrace with Momoko</option>
                </select>

                <div style={{ marginTop: '2.2rem' }}>
                  <button className="fe-btn" onClick={handleUpload} disabled={!file}>
                    START GENERATIVE PIPELINE
                  </button>
                </div>
              </div>
            ) : (
              <div className="fe-card liquid-glass" style={{ textAlign: 'center' }}>
                <h2>Multimodal Chaining Pipeline Progress</h2>
                <p>
                  <strong>Status:</strong> {status.toUpperCase() || 'INITIALIZING...'} ({progressPct}%)
                </p>
                <div className="fe-progress-track">
                  <div className="fe-progress-bar" style={{ width: `${Math.max(8, progressPct)}%` }} />
                </div>
                <p style={{ color: '#00e5ff' }}>
                  <strong>Stage:</strong> {stage || 'Starting processing...'}
                </p>

                {/* Live 35mm Motion Viewport while Gemini Omni 60fps video is rendering */}
                {!resultUrl && (previewVideoUrl || avatarUrl || previewUrl) && (
                  <div className="ken-burns-viewport">
                    {previewVideoUrl ? (
                      <video
                        src={previewVideoUrl}
                        autoPlay
                        loop
                        muted
                        playsInline
                        style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                      />
                    ) : (
                      <img
                        src={avatarUrl || previewUrl!}
                        alt="Live 35mm Motion Preview"
                        className="ken-burns-img"
                      />
                    )}
                    <div className="film-hud-badge">
                      {previewVideoUrl
                        ? '● 35MM MOTION PREVIEW LIVE — RENDERING OMNI 60FPS HD...'
                        : avatarUrl
                        ? '● 35MM KEYFRAME LOCKED — ANAMORPHIC MOTION ACTIVE'
                        : '● ANALYZING DRIVER LIKENESS — GEMINI 3.8 FLASH'}
                    </div>
                  </div>
                )}

                {candidates.length > 0 && (
                  <div style={{ margin: '1.5rem 0' }}>
                    <h4>
                      {candidates.length}/4 Nano Banana 2 Keyframe Candidates Streamed (4x Parallel):
                    </h4>
                    <div className="candidate-strip">
                      {candidates.map((cUrl, i) => (
                        <img
                          key={i}
                          src={cUrl}
                          alt={`Take ${i + 1}`}
                          className="candidate-thumb"
                          style={{
                            borderColor: cUrl === avatarUrl ? '#00e5ff' : 'rgba(255,255,255,0.15)',
                          }}
                        />
                      ))}
                    </div>
                  </div>
                )}

                {resultUrl && (
                  <div style={{ marginTop: '2rem' }}>
                    <h3>Your 35mm GEN4 Film Cut (Starring {driverName})</h3>
                    <video
                      src={resultUrl}
                      controls
                      autoPlay
                      loop
                      style={{ width: '100%', maxWidth: '720px', borderRadius: '18px' }}
                    />
                  </div>
                )}

                {(status === 'completed' || status === 'failed') && (
                  <div style={{ marginTop: '2rem' }}>
                    <button type="button" className="fe-btn-secondary" onClick={handleReset}>
                      CREATE ANOTHER SCENE
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
