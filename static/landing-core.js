const STEM_SAMPLES = {};

(function initSilentStems() {
  const SR = 22050;
  const DUR_S = 6.0;
  const N = Math.round(SR * DUR_S);
  try {
    ['vocals', 'drums', 'bass', 'guitar', 'other'].forEach(name => {
      STEM_SAMPLES[name] = new Float32Array(N);
    });
    STEM_SAMPLES._sr = SR;
    STEM_SAMPLES._duration = DUR_S;
  } catch (e) {
    console.warn('Silent stem init failed', e);
  }
})();


let audioCtx = null;
let stemNodes = {};
let stemBuffers = {};
let activeSources = {};
let masterGain = null;
let cueBus = null;
let cueStreamDest = null;
let masterAnalyser = null;
let masterDataArray = null;
let isPlaying = false;
let rafId = null;
const BASE_BPM = 120;
let tempoRatio = 1;
let stemAutoStretch = { vocals: 1, drums: 1, bass: 1, guitar: 1, other: 1 };
let masterVolPct = 80;
let keySemitones = 0;
let keyLockOn = true;

let masterOffset = 0;
let playStartCtxTime = 0;
const stemNudge = { vocals: 0, drums: 0, bass: 0, guitar: 0, other: 0 };
const LOOP_DUR = 6.0;
// New: per-stem SAMPLE-mode toggle state, driven by the visible SAMPLE
// button on each waveform row. When true for a stem, a plain (non-shift)
// click-drag on that row chops a sample region instead of nudging the
// stem's timing — Shift+drag still works as a shortcut regardless of
// this toggle.
const sampleModeByStem = { vocals: false, drums: false, bass: false, guitar: false, other: false };
const NOTE_NAMES = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B'];
function keyLabel(semis) {
  const idx = ((Math.round(semis) % 12) + 12) % 12;
  const sign = semis > 0 ? '+' : semis < 0 ? '' : '\u00B1';
  return `${sign}${Math.round(semis)}st (${NOTE_NAMES[idx]})`;
}
function tempoInducedSemitonesFor(name) {
  const rate = tempoRatio * (stemAutoStretch[name] || 1);
  return 12 * Math.log2(rate);
}
function applyKeyShift() {
  Object.entries(stemNodes).forEach(([name, node]) => {
    if (!node.pitchShift || !node.compressor) return;
    const compensate = keyLockOn ? -tempoInducedSemitonesFor(name) : 0;
    const totalShift = keySemitones + compensate;
    node.pitchShift.pitch = totalShift;

    const needsPitch = Math.abs(totalShift) > 0.25;
    if (needsPitch && !node._pitchConnectedToGain) {
      try { node.eqHigh.disconnect(node.compressor); } catch (e) {}
      Tone.connect(node.pitchShift, node.compressor);
      node._pitchConnectedToGain = true;
    } else if (!needsPitch && node._pitchConnectedToGain) {
      try { node.pitchShift.disconnect(node.compressor); } catch (e) {}
      node.eqHigh.connect(node.compressor);
      node._pitchConnectedToGain = false;
    }
  });
}

function updateAllChannelGains() {
  const anySolo = Object.values(stemNodes).some(n => n.solo);
  Object.values(stemNodes).forEach(n => {
    if (n.gainNode) {
      const silent = n.muted || (anySolo && !n.solo);
      n.gainNode.gain.value = silent ? 0 : (n.volPct / 100);
    }
    if (n.cueSendGain) {
      n.cueSendGain.gain.value = n.muted ? (n.volPct / 100) : 0;
    }
  });
}
const dbToGain = db => Math.pow(10, db / 20);

// Default EQ starting points per stem, to cut down on vocal bleed into
// "other"-family instruments separated by Demucs (guitar/other all
// come from the same catch-all stem, so they bleed into each other and
// into vocals). These are just starting knob positions -- still fully
// adjustable per channel.
// Reset to flat: every EQ knob starts in the middle (0 dB). Previous presets
// were guitar { mid: -3, high: -2.5 } and vocals { mid: -1, high: -3 }.
const EQ_DEFAULTS = {};

function initEngine() {
  Object.keys(STEM_SAMPLES).filter(k => !k.startsWith('_')).forEach(name => {
    const existing = stemNodes[name] || {};
    const eqDef = EQ_DEFAULTS[name] || {};
    stemNodes[name] = Object.assign(
      { volPct: 78, trimDb: 0, eqLowDb: eqDef.low || 0, eqMidDb: eqDef.mid || 0, eqHighDb: eqDef.high || 0, muted: false, solo: false },
      existing
    );
  });
}

let scopeCanvases = [];
let scopeCtxs = [];
function initScope() {
  scopeCanvases = ['scopeCanvasL', 'scopeCanvasR']
    .map(id => document.getElementById(id))
    .filter(Boolean);
  if (!scopeCanvases.length) return;
  scopeCtxs = scopeCanvases.map(c => c.getContext('2d'));
  const resize = () => {
    const dpr = window.devicePixelRatio || 1;
    scopeCanvases.forEach((canvas, i) => {
      const rect = canvas.getBoundingClientRect();
      canvas.width = rect.width * dpr;
      canvas.height = rect.height * dpr;
      scopeCtxs[i].setTransform(dpr, 0, 0, dpr, 0, 0);
    });
  };
  resize();
  window.addEventListener('resize', resize);
}
function drawScope(ctx, canvas, dataArray, flat) {
  if (!ctx || !canvas) return;
  const w = canvas.clientWidth, h = canvas.clientHeight;
  if (!w || !h) return;
  const cx = w / 2, cy = h / 2;
  const baseR = Math.min(w, h) * 0.32;
  const ampR = Math.min(w, h) * 0.14;

  ctx.clearRect(0, 0, w, h);

  ctx.strokeStyle = 'rgba(60,253,224,0.10)';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.arc(cx, cy, baseR, 0, Math.PI * 2);
  ctx.stroke();

  ctx.strokeStyle = '#3cfde0';
  ctx.lineWidth = 1.5;
  ctx.shadowColor = '#3cfde0';
  ctx.shadowBlur = 8;
  ctx.beginPath();
  if (flat) {
    ctx.moveTo(cx - baseR, cy);
    ctx.lineTo(cx + baseR, cy);
  } else {
    const n = dataArray.length;
    for (let i = 0; i <= n; i++) {
      const v = (dataArray[i % n] - 128) / 128;
      const angle = (i / n) * Math.PI * 2;
      const r = baseR + v * ampR;
      const x = cx + Math.cos(angle) * r;
      const y = cy + Math.sin(angle) * r;
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }
    ctx.closePath();
  }
  ctx.stroke();
  ctx.shadowBlur = 0;
}

function scopeLoop() {
  if (!scopeCanvases.length) { requestAnimationFrame(scopeLoop); return; }
  const playing = masterAnalyser && transportState === 'playing';
  if (playing) masterAnalyser.getByteTimeDomainData(masterDataArray);
  scopeCanvases.forEach((canvas, i) => {
    drawScope(scopeCtxs[i], canvas, playing ? masterDataArray : null, !playing);
  });
  requestAnimationFrame(scopeLoop);
}

function connectAnalysers() {
  audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  if (window.Tone && Tone.setContext) {
    try { Tone.setContext(audioCtx); } catch (e) { console.warn('Tone context share failed', e); }
  }
  masterGain = audioCtx.createGain();
  masterGain.gain.value = masterVolPct / 100;
  // Bus compressor: gentle glue on the full mix (live playback).
  const busComp = audioCtx.createDynamicsCompressor();
  busComp.threshold.value = -14; busComp.knee.value = 6; busComp.ratio.value = 2;
  busComp.attack.value = 0.03; busComp.release.value = 0.25;
  masterGain.connect(busComp);
  busComp.connect(audioCtx.destination);

  masterAnalyser = audioCtx.createAnalyser();
  masterAnalyser.fftSize = 256;
  masterDataArray = new Uint8Array(masterAnalyser.frequencyBinCount);
  masterGain.connect(masterAnalyser);

  cueBus = audioCtx.createGain();
  cueBus.gain.value = 1;
  cueStreamDest = audioCtx.createMediaStreamDestination();
  cueBus.connect(cueStreamDest);
  const cueEl = document.getElementById('cueMonitorAudio');
  if (cueEl) {
    cueEl.srcObject = cueStreamDest.stream;
    cueEl.play().catch(() => {});
  }

  const sr = STEM_SAMPLES._sr || 22050;

  Object.keys(stemNodes).forEach(name => {
    const node = stemNodes[name];
    const samples = STEM_SAMPLES[name];
    if (!samples) return;

    const buf = audioCtx.createBuffer(1, samples.length, sr);
    buf.copyToChannel(samples, 0);
    stemBuffers[name] = buf;

    const trimNode = audioCtx.createGain();
    trimNode.gain.value = dbToGain(node.trimDb);

    const eqLow = audioCtx.createBiquadFilter();
    eqLow.type = 'lowshelf'; eqLow.frequency.value = 320; eqLow.gain.value = node.eqLowDb;

    const eqMid = audioCtx.createBiquadFilter();
    eqMid.type = 'peaking'; eqMid.frequency.value = 1000; eqMid.Q.value = 1; eqMid.gain.value = node.eqMidDb;

    const eqHigh = audioCtx.createBiquadFilter();
    eqHigh.type = 'highshelf'; eqHigh.frequency.value = 3200; eqHigh.gain.value = node.eqHighDb;

    // Gentle per-stem compressor, sits after EQ. Smooths out the
    // watery/phasey texture separation artifacts leave behind, without
    // squashing the sound -- moderate ratio, soft knee.
    const compressor = audioCtx.createDynamicsCompressor();
    compressor.threshold.value = -24;
    compressor.knee.value = 6;
    compressor.ratio.value = 3;
    compressor.attack.value = 0.01;
    compressor.release.value = 0.2;

    const gainNode = audioCtx.createGain();
    gainNode.gain.value = node.muted ? 0 : node.volPct / 100;

    const cueSendGain = audioCtx.createGain();
    cueSendGain.gain.value = node.muted ? node.volPct / 100 : 0;

    const analyser = audioCtx.createAnalyser();
    analyser.fftSize = 256;

    let pitchShift = null;
    let pitchAvailable = false;
    if (window.Tone && Tone.PitchShift) {
      try {
        pitchShift = new Tone.PitchShift({ pitch: 0, windowSize: 0.18 });
        pitchAvailable = true;
      } catch (e) {
        console.warn('PitchShift unavailable, falling back to direct connection', e);
      }
    }

    trimNode.connect(eqLow);
    eqLow.connect(eqMid);
    eqMid.connect(eqHigh);
    eqHigh.connect(compressor);
    compressor.connect(gainNode);
    compressor.connect(cueSendGain);
    cueSendGain.connect(cueBus);
    if (pitchAvailable) {
      Tone.connect(eqHigh, pitchShift);
    }
    node._pitchConnectedToGain = false;
    gainNode.connect(analyser);
    analyser.connect(masterGain);

    node.trimNode = trimNode;
    node.compressor = compressor;
    node.eqLow = eqLow;
    node.eqMid = eqMid;
    node.eqHigh = eqHigh;
    node.gainNode = gainNode;
    node.cueSendGain = cueSendGain;
    node.analyser = analyser;
    node.pitchShift = pitchShift;
    node.dataArray = new Uint8Array(analyser.frequencyBinCount);
  });
}

function wrapOffset(offset, dur) {
  return ((offset % dur) + dur) % dur;
}

// A "real" stem is one loaded from the backend (has metadata). Once any real
// stem is loaded we are in SONG mode: placeholder channels go silent, nothing
// loops, and playback stops at the end of the song.
function hasRealSong() {
  return Object.keys(currentStemMeta).some(k => currentStemMeta[k] && stemBuffers[k]);
}

function getMasterDuration() {
  const real = hasRealSong();
  const durs = Object.keys(stemBuffers)
    .filter(k => stemBuffers[k] && (!real || currentStemMeta[k]))
    .map(k => stemBuffers[k].duration);
  return durs.length ? Math.max(...durs) : LOOP_DUR;
}

function startStem(name, masterPos) {
  stopStem(name);
  const buffer = stemBuffers[name];
  if (!buffer || !stemNodes[name]?.trimNode) return;
  const songMode = hasRealSong();
  if (songMode && !currentStemMeta[name]) return; // placeholder channel stays silent
  const src = audioCtx.createBufferSource();
  src.buffer = buffer;
  src.loop = !songMode;
  src.playbackRate.value = tempoRatio * (stemAutoStretch[name] || 1);
  if (!songMode) {
    src.loopStart = 0;
    src.loopEnd = buffer.duration;
  }
  src.connect(stemNodes[name].trimNode);
  const activeMarker = (stemMarkers[name] || []).find(m => m.active);
  const base = activeMarker ? activeMarker.time : masterPos;
  let eff;
  if (songMode) {
    eff = Math.max(0, base + stemNudge[name]);
    if (eff >= buffer.duration) { try { src.disconnect(); } catch (e) {} return; }
    src.onended = () => { if (activeSources[name] === src) checkSongEnded(); };
  } else {
    eff = wrapOffset(base + stemNudge[name], buffer.duration);
  }
  src.start(0, eff);
  activeSources[name] = src;
}

function stopStem(name) {
  const src = activeSources[name];
  if (src) {
    try { src.stop(); } catch (e) {}
    try { src.disconnect(); } catch (e) {}
    activeSources[name] = null;
  }
}

function startAllStems(masterPos) {
  masterOffset = masterPos;
  playStartCtxTime = audioCtx.currentTime;
  Object.keys(stemBuffers).forEach(name => startStem(name, masterPos));
}

function stopAllStems() {
  Object.keys(activeSources).forEach(stopStem);
}

let scrubHold = false;

function rawPlaybackTime() {
  if (transportState === 'playing' && audioCtx && !scrubHold) {
    return masterOffset + (audioCtx.currentTime - playStartCtxTime) * tempoRatio;
  }
  return masterOffset;
}

function currentPlaybackTime() {
  const dur = getMasterDuration();
  const raw = rawPlaybackTime();
  if (hasRealSong()) return Math.max(0, Math.min(raw, dur));
  return wrapOffset(raw, dur);
}

// Song mode only: when the playhead reaches the end, stop and rewind
// instead of looping back to the start.
function checkSongEnded() {
  if (transportState !== 'playing' || scrubHold || !hasRealSong()) return;
  if (rawPlaybackTime() >= getMasterDuration() - 0.02) {
    stopPreview();
  }
}

function updateFaders() {
  Object.keys(stemNodes).forEach(name => {
    const node = stemNodes[name];
    if (!node.analyser) return;
    node.analyser.getByteTimeDomainData(node.dataArray);

    let sumSquares = 0;
    for (let i = 0; i < node.dataArray.length; i++) {
      const normalized = (node.dataArray[i] - 128) / 128;
      sumSquares += normalized * normalized;
    }
    const rms = Math.sqrt(sumSquares / node.dataArray.length);
    const lit = node.muted ? 0 : Math.round(Math.min(1, rms * 4.2) * 6);

    const channel = document.querySelector(`.channel[data-stem="${name}"]`);
    if (channel) {
      const segs = channel.querySelectorAll('.meter-seg');
      segs.forEach((seg, i) => seg.classList.toggle('lit', i < lit));
    }
  });

  if (masterAnalyser) {
    masterAnalyser.getByteTimeDomainData(masterDataArray);
    let sumSquares = 0;
    for (let i = 0; i < masterDataArray.length; i++) {
      const normalized = (masterDataArray[i] - 128) / 128;
      sumSquares += normalized * normalized;
    }
    const rms = Math.sqrt(sumSquares / masterDataArray.length);
    const lit = Math.round(Math.min(1, rms * 4.0) * 10);
    document.querySelectorAll('#masterMeter .meter-col').forEach(col => {
      const segs = col.querySelectorAll('.meter-seg');
      segs.forEach((seg, i) => seg.classList.toggle('lit', i < lit));
    });
  }

  updatePlayheadPosition();
  checkSongEnded();

  rafId = requestAnimationFrame(updateFaders);
}

const originalStemBuffers = {};
const currentStemMeta = {};

async function loadBackendStemToChannel(channelKey, stemId, trackName, urlOverride) {
  const status = document.getElementById('uploadStatus');
  const showErr = (msg) => {
    if (!status) return;
    status.style.display = 'block';
    status.style.color = 'var(--clip-red)';
    status.textContent = msg;
  };
  try {
    await ensureEngineReady();
    if (!urlOverride && (typeof getToken !== 'function' || !getToken())) {
      showErr('Log in first to load a stem from your library.');
      return false;
    }
    const url = urlOverride || (window.API_BASE + '/api/v1/my-stems/' + encodeURIComponent(stemId)
              + '/download/' + encodeURIComponent(channelKey)
              + '?token=' + encodeURIComponent(getToken())
              + '&bpm=' + BASE_BPM);
    const res = await fetch(url);
    if (!res.ok) throw new Error('Server returned ' + res.status);
    const arrayBuf = await res.arrayBuffer();
    const audioBuffer = await audioCtx.decodeAudioData(arrayBuf);

    // Tempo matching now happens on the server: the stem arrives already
    // time-stretched (pitch preserved) to BASE_BPM, with its real length
    // changed, so no playbackRate trick is needed here.
    stemAutoStretch[channelKey] = 1;

    if (!originalStemBuffers[channelKey]) {
      originalStemBuffers[channelKey] = stemBuffers[channelKey];
    }
    stemBuffers[channelKey] = audioBuffer;
    currentStemMeta[channelKey] = { stemId, trackName };

    const canvas = document.querySelector('.wave-row[data-stem="' + channelKey + '"] .wave-canvas');
    if (canvas) {
      const full = audioBuffer.getChannelData(0);
      drawWaveformFromSamples(canvas, full, WAVE_COLORS[channelKey] || '#3CFDE0');
    }
    if (stemSampleRegions[channelKey]) renderStemSampleRegions(channelKey);

    const channel = document.querySelector('.channel[data-stem="' + channelKey + '"]');
    if (channel) {
      const badge = channel.querySelector('.assigned-badge');
      if (badge) { badge.textContent = trackName; badge.classList.add('show'); }
      const led = channel.querySelector('.status-led');
      if (led) { led.classList.add('playing'); led.classList.remove('muted'); }
      const muteBtnEl = channel.querySelector('.mute-btn');
      if (muteBtnEl) muteBtnEl.classList.remove('active');
    }
    if (stemNodes[channelKey]) {
      stemNodes[channelKey].muted = false;
      if (typeof updateAllChannelGains === 'function') updateAllChannelGains();
    }
    applyKeyShift();

    if (transportState === 'playing') {
      startStem(channelKey, currentPlaybackTime());
    }

    if (status) status.style.display = 'none';
    return true;
  } catch (e) {
    console.error('Load stem failed:', e);
    showErr('Could not load stem: ' + (e.message || 'unknown error'));
    return false;
  }
}

function silentBuffer() {
  const sr = (audioCtx && audioCtx.sampleRate) || 44100;
  const buf = (audioCtx || { createBuffer: (c,l,s)=>({length:l,duration:l/s}) }).createBuffer(1, 1, sr);
  return buf;
}

function drawEmptyWaveform(canvas, color) {
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  const width = Math.max(1, Math.floor(rect.width * dpr));
  const height = Math.max(1, Math.floor(rect.height * dpr));
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, width, height);
  ctx.strokeStyle = color;
  ctx.globalAlpha = 0.35;
  ctx.lineWidth = Math.max(1, dpr);
  ctx.beginPath();
  ctx.moveTo(0, height / 2);
  ctx.lineTo(width, height / 2);
  ctx.stroke();
  ctx.globalAlpha = 1;
}

function restoreOriginalStem(channelKey) {
  delete originalStemBuffers[channelKey];
  delete currentStemMeta[channelKey];
  stemAutoStretch[channelKey] = 1;
  applyKeyShift();

  const node = stemNodes[channelKey];
  const g = node && node.trimNode ? node.trimNode.gain : null;
  const restoreGain = g ? g.value : null;
  if (g && audioCtx) {
    const now = audioCtx.currentTime;
    g.cancelScheduledValues(now);
    g.setValueAtTime(g.value, now);
    g.linearRampToValueAtTime(0, now + 0.012);
  }
  setTimeout(() => {
    stopStem(channelKey);
    stemBuffers[channelKey] = silentBuffer();
    if (g && audioCtx && restoreGain !== null) {
      g.cancelScheduledValues(audioCtx.currentTime);
      g.value = restoreGain;
    }
  }, g && audioCtx ? 14 : 0);

  if (node) {
    node.muted = true;
    if (typeof updateAllChannelGains === 'function') updateAllChannelGains();
  }
  const muteBtnEl = document.querySelector('.channel[data-stem="' + channelKey + '"] .mute-btn');
  if (muteBtnEl) muteBtnEl.classList.add('active');

  const canvas = document.querySelector('.wave-row[data-stem="' + channelKey + '"] .wave-canvas');
  if (canvas) {
    drawEmptyWaveform(canvas, WAVE_COLORS[channelKey] || '#3CFDE0');
  }

  if (stemSampleRegions[channelKey]) {
    stemSampleRegions[channelKey] = [];
    renderStemSampleRegions(channelKey);
  }

  const channel = document.querySelector('.channel[data-stem="' + channelKey + '"]');
  if (channel) {
    const badge = channel.querySelector('.assigned-badge');
    if (badge) { badge.textContent = ''; badge.classList.remove('show'); }
    const led = channel.querySelector('.status-led');
    if (led) { led.classList.remove('playing'); led.classList.add('muted'); }
  }
}

function showSaveHint() {
  const tab = document.getElementById('screenStemsTab');
  if (!tab) return;
  const tip = document.createElement('div');
  tip.className = 'save-hint-tip';
  tip.textContent = 'Saved! Find it here anytime';
  tab.style.position = 'relative';
  tab.appendChild(tip);
  setTimeout(() => { tip.remove(); }, 5000);
}

async function saveChannelAsStem(channelKey, btn) {
  const meta = currentStemMeta[channelKey];
  if (!meta) {
    if (btn) {
      const prev = btn.textContent;
      btn.textContent = 'LOAD 1ST';
      setTimeout(() => { btn.textContent = prev; }, 1400);
    }
    return false;
  }
  if (typeof getToken !== 'function' || !getToken()) return false;

  if (btn) { btn.classList.add('saving'); btn.textContent = '...'; }
  try {
    const url = window.API_BASE + '/api/v1/my-stems/' + encodeURIComponent(meta.stemId)
              + '/save-instrument/' + encodeURIComponent(channelKey)
              + '?token=' + encodeURIComponent(getToken());
    const res = await fetch(url, { method: 'POST' });
    if (!res.ok) throw new Error('Server returned ' + res.status);
    if (btn) {
      btn.classList.remove('saving');
      btn.classList.add('saved');
      btn.textContent = 'SAVED';
      setTimeout(() => { btn.classList.remove('saved'); btn.textContent = 'SAVE'; }, 1600);
    }
    if (typeof window.__refreshMyStems === 'function') window.__refreshMyStems();
    if (!localStorage.getItem('stemline_seen_save_hint')) {
      localStorage.setItem('stemline_seen_save_hint', '1');
      showSaveHint();
    }
    return true;
  } catch (e) {
    console.error('Save channel failed:', e);
    if (btn) {
      btn.classList.remove('saving');
      btn.textContent = 'FAILED';
      setTimeout(() => { btn.textContent = 'SAVE'; }, 1600);
    }
    return false;
  }
}

document.querySelectorAll('.ch-save').forEach(btn => {
  btn.addEventListener('click', (e) => {
    e.stopPropagation();
    const chan = btn.getAttribute('data-save');
    saveChannelAsStem(chan, btn);
  });
});

window.__loadBackendStemToChannel = loadBackendStemToChannel;

(function () {
  const demoBtn = document.getElementById('demoBtn');
  if (!demoBtn) return;
  demoBtn.addEventListener('click', async () => {
    demoBtn.disabled = true;
    const prev = demoBtn.textContent;
    demoBtn.textContent = 'LOADING…';
    try {
      const chans = ['vocals', 'drums', 'bass', 'guitar', 'other'];
      const results = await Promise.all(chans.map(c =>
        loadBackendStemToChannel(c, 'demo', 'Demo Track', '/demo/' + c + '.mp3')));
      const ok = results.filter(Boolean).length;
      const label = document.getElementById('previewLabel');
      if (label && ok > 0) label.textContent = 'Demo Track';
      demoBtn.textContent = ok === chans.length ? 'LOADED' : ('LOADED ' + ok + '/' + chans.length);
    } catch (e) {
      demoBtn.textContent = 'FAILED';
    }
    setTimeout(() => { demoBtn.textContent = prev; demoBtn.disabled = false; }, 1500);
  });
})();
window.__restoreOriginalStem = restoreOriginalStem;
window.__saveChannelAsStem = saveChannelAsStem;

function updatePlayheadPosition() {
  const playhead = document.getElementById('wavePlayhead');
  if (!playhead) return;
  const progress = Math.max(0, Math.min(1, currentPlaybackTime() / getMasterDuration()));

  // FIX: was tracking only the wave-canvas width, which stops short of
  // the row's full width (the +CUE / SAMPLE buttons sit outside the
  // canvas). That made the playhead visually stall at the canvas edge
  // well before the song actually ended, even though audio kept playing.
  // Track the wave-canvas-wrap instead, which spans the full scrubbable
  // area of the row.
  const firstWrap = document.querySelector('.wave-row .wave-canvas-wrap');
  if (!firstWrap) return;
  const wrapRect = firstWrap.getBoundingClientRect();
  const rowsEl = document.getElementById('waveformRows');
  const rowsRect = rowsEl.getBoundingClientRect();
  // ROOT-CAUSE FIX: the whole .hero is shrunk with transform: scale(...) to
  // fit the window height (see fitHero). getBoundingClientRect() returns
  // on-screen (scaled) pixels, but style.left is in unscaled layout pixels
  // that then get scaled again -- so the playhead covered only `scale` of
  // the track (stopped ~18% short of the end and drifted away from the
  // mouse while dragging). Convert screen pixels back to layout pixels.
  const scaleX = (rowsEl.offsetWidth > 0 && rowsRect.width > 0) ? (rowsRect.width / rowsEl.offsetWidth) : 1;
  const x = ((wrapRect.left - rowsRect.left) + progress * wrapRect.width) / scaleX;
  playhead.style.left = x + 'px';
}

let transportState = 'idle';

function refreshTransportButtons() {
  const play = document.getElementById('playBtn');
  const pause = document.getElementById('pauseBtn');
  if (!play || !pause) return;
  play.classList.toggle('active', transportState === 'playing');
  pause.classList.toggle('active', transportState === 'paused');
}

async function ensureEngineReady() {
  if (!audioCtx) {
    initEngine();
    connectAnalysers();
  }
  if (audioCtx.state === 'suspended') await audioCtx.resume();
}

async function playPreview() {
  try {
    await ensureEngineReady();
  } catch (e) {
    const status = document.getElementById('uploadStatus');
    if (status) {
      status.style.display = 'block';
      status.style.color = 'var(--clip-red)';
      status.textContent = 'Audio engine failed to start: ' + (e.message || e);
    }
    console.error('ensureEngineReady failed:', e);
    return;
  }
  startAllStems(masterOffset);
  transportState = 'playing';
  isPlaying = true;
  refreshTransportButtons();
  document.querySelectorAll('.status-led').forEach(led => led.classList.add('playing'));
  document.getElementById('wavePlayhead')?.classList.add('on');
  updateFaders();
}

function pausePreview() {
  if (transportState !== 'playing') return;
  const pos = currentPlaybackTime();
  stopAllStems();
  masterOffset = pos;
  transportState = 'paused';
  isPlaying = false;
  refreshTransportButtons();
  if (rafId) cancelAnimationFrame(rafId);
  document.querySelectorAll('.status-led').forEach(led => led.classList.remove('playing'));
  document.querySelectorAll('.meter-seg').forEach(seg => seg.classList.remove('lit'));
}

function stopPreview() {
  scrubHold = false;
  stopAllStems();
  try { if (window.__stopSamples) window.__stopSamples(); } catch (e) {}
  masterOffset = 0;
  transportState = 'idle';
  isPlaying = false;
  refreshTransportButtons();
  if (rafId) cancelAnimationFrame(rafId);
  document.querySelectorAll('.status-led').forEach(led => led.classList.remove('playing'));
  document.querySelectorAll('.meter-seg').forEach(seg => seg.classList.remove('lit'));
  updatePlayheadPosition();
}

function seekTo(pos) {
  const dur = getMasterDuration();
  masterOffset = hasRealSong() ? Math.max(0, Math.min(pos, dur - 0.05)) : wrapOffset(pos, dur);
  if (transportState === 'playing') {
    startAllStems(masterOffset);
  }
  updatePlayheadPosition();
}

// Smooth scrubbing: silence audio while the playhead is dragged, then
// restart every stem together once on release (no stutter, no drift).
function beginScrub() {
  if (scrubHold) return;
  if (transportState === 'playing') {
    masterOffset = currentPlaybackTime();
    stopAllStems();
  }
  scrubHold = true;
}
function scrubMove(pos) {
  const dur = getMasterDuration();
  masterOffset = hasRealSong() ? Math.max(0, Math.min(pos, dur - 0.05)) : wrapOffset(pos, dur);
  updatePlayheadPosition();
}
function endScrub() {
  if (!scrubHold) return;
  scrubHold = false;
  if (transportState === 'playing') startAllStems(masterOffset);
  updatePlayheadPosition();
}

function setStemNudge(name, nudgeSec) {
  stemNudge[name] = nudgeSec;
  const row = document.querySelector('.wave-row[data-stem="' + name + '"]');
  if (row) {
    updateNudgeVisual(row, nudgeSec);
    updateNudgeReadout(row, nudgeSec);
  }
  if (transportState === 'playing') {
    const pos = currentPlaybackTime();
    startStem(name, pos);
  }
}

function updateNudgeVisual(row, nudgeSec) {
  // Waveform picture stays fixed in place now -- nudge still shifts actual
  // playback timing (see setStemNudge/startStem), only the visual slide
  // was removed.
  const stem = row.dataset.stem;
  if (stem) renderStemMarkers(stem);
}

function updateNudgeReadout(row, nudgeSec) {
  const label = row.querySelector('.wave-row-label');
  if (!label) return;
  const stem = row.dataset.stem;
  const stemName = { vocals: 'VOCALS', drums: 'DRUMS', bass: 'BASS', guitar: 'GUITAR', other: 'OTHER' }[stem] || stem.toUpperCase();
  if (Math.abs(nudgeSec) < 0.005) {
    label.textContent = stemName;
  } else {
    const ms = Math.round(nudgeSec * 1000);
    label.innerHTML = stemName + '<span style="opacity:0.7"> ' + (ms > 0 ? '+' : '') + ms + 'ms</span>';
  }
}

function onDrag(el, { onStart, onMove, onEnd }) {
  let active = null;
  el.addEventListener('pointerdown', e => {
    if (active !== null) return;
    active = e.pointerId;
    el.setPointerCapture(e.pointerId);
    onStart && onStart(e);
    e.preventDefault();
  });
  el.addEventListener('pointermove', e => {
    if (e.pointerId !== active) return;
    onMove && onMove(e);
    e.preventDefault();
  });
  const finish = e => {
    if (e.pointerId !== active) return;
    active = null;
    if (el.hasPointerCapture(e.pointerId)) el.releasePointerCapture(e.pointerId);
    onEnd && onEnd(e);
  };
  el.addEventListener('pointerup', finish);
  el.addEventListener('pointercancel', finish);
}

function setupEncoder(el, { onStep, onClick, detent = 18 }) {
  let angle = 0, dragging = false, touchId = null;
  let lastY = 0, accum = 0, moved = 0;

  const spin = deg => {
    angle += deg;
    el.style.setProperty('--angle', angle + 'deg');
  };

  const start = clientY => { dragging = true; lastY = clientY; accum = 0; moved = 0; };
  const move = clientY => {
    if (!dragging) return;
    const dy = lastY - clientY;
    lastY = clientY;
    moved += Math.abs(dy);
    accum += dy;
    spin(dy * 2.2);
    while (Math.abs(accum) >= detent) {
      const dir = accum > 0 ? -1 : 1;
      accum -= (accum > 0 ? 1 : -1) * detent;
      onStep(dir);
    }
  };
  const end = () => {
    if (dragging && moved < 4 && onClick) onClick();
    dragging = false; touchId = null;
  };

  onDrag(el, {
    onStart: e => start(e.clientY),
    onMove:  e => move(e.clientY),
    onEnd:   () => end()
  });

  el.addEventListener('wheel', e => {
    e.preventDefault();
    const dir = e.deltaY > 0 ? 1 : -1;
    spin(dir * 12);
    onStep(dir);
  }, { passive: false });

  return { reset: () => { angle = 0; el.style.setProperty('--angle', '0deg'); } };
}

function setupKnob(el, { min, max, initial, onChange }) {
  let value = initial;
  const range = max - min;
  const angleFor = v => -135 + ((v - min) / range) * 270;
  const apply = v => {
    value = Math.min(max, Math.max(min, v));
    el.style.setProperty('--angle', angleFor(value) + 'deg');
    onChange(value);
  };
  apply(initial);

  let dragging = false, startY = 0, startVal = 0;
  onDrag(el, {
    onStart: e => { dragging = true; startY = e.clientY; startVal = value; },
    onMove:  e => { if (dragging) apply(startVal + ((startY - e.clientY) / 130) * range); },
    onEnd:   () => { dragging = false; }
  });

  return { set: apply, get: () => value };
}

function setupFader(slotEl, capEl, { initial, onChange }) {
  let pct = initial;
  const apply = p => {
    pct = Math.min(95, Math.max(0, p));
    capEl.style.bottom = pct + '%';
    onChange(pct);
  };
  apply(initial);

  const posToPct = clientY => {
    const r = slotEl.getBoundingClientRect();
    return ((r.bottom - clientY) / r.height) * 100;
  };
  let dragging = false;
  onDrag(slotEl, {
    onStart: e => { dragging = true; apply(posToPct(e.clientY)); },
    onMove:  e => { if (dragging) apply(posToPct(e.clientY)); },
    onEnd:   () => { dragging = false; }
  });

  return { set: apply, get: () => pct };
}

const WAVE_COLORS = { vocals: '#ff5540', drums: '#ffa022', bass: '#2fe08a', guitar: '#9b6dff', other: '#3ab6ff' };

function drawWaveformFromSamples(canvas, data, color) {
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  const width = Math.max(1, Math.floor(rect.width * dpr));
  const height = Math.max(1, Math.floor(rect.height * dpr));
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, width, height);

  const samplesPerPixel = Math.max(1, Math.floor(data.length / width));
  const mid = height / 2;

  const amps = new Array(width);
  let loudest = 0;
  for (let x = 0; x < width; x++) {
    const start = x * samplesPerPixel;
    let sumSq = 0, peak = 0, count = 0;
    for (let i = 0; i < samplesPerPixel; i++) {
      const sample = data[start + i];
      if (sample === undefined) break;
      const abs = Math.abs(sample);
      sumSq += sample * sample;
      if (abs > peak) peak = abs;
      count++;
    }
    const rms = count ? Math.sqrt(sumSq / count) : 0;
    const amp = count ? (rms * 1.8 + peak * 0.2) : 0;
    amps[x] = amp;
    if (amp > loudest) loudest = amp;
  }
  const scale = loudest > 0.0001 ? (1 / loudest) : 1;

  ctx.strokeStyle = color;
  ctx.lineWidth = Math.max(1, dpr);
  ctx.shadowColor = color;
  ctx.shadowBlur = 4 * dpr;
  ctx.beginPath();
  for (let x = 0; x < width; x++) {
    const amp = Math.min(1, amps[x] * scale);
    const y1 = mid - amp * mid * 0.92;
    const y2 = mid + amp * mid * 0.92;
    ctx.moveTo(x + 0.5, y1);
    ctx.lineTo(x + 0.5, y2);
  }
  ctx.stroke();
}

function renderStemWaveforms() {
  document.querySelectorAll('.wave-row').forEach(row => {
    const stem = row.dataset.stem;
    const canvas = row.querySelector('.wave-canvas');
    const samples = STEM_SAMPLES[stem];
    if (!canvas || !samples) return;
    try {
      drawWaveformFromSamples(canvas, samples, WAVE_COLORS[stem] || '#3CFDE0');
    } catch (e) {
      console.warn('Waveform render failed for', stem, e);
    }
  });
}

const stemMarkers = { vocals: [], drums: [], bass: [], guitar: [], other: [] };
let markerIdCounter = 0;

function formatMarkerTime(t) {
  const s = Math.max(0, t);
  const mm = Math.floor(s / 60);
  const ss = (s % 60).toFixed(2).padStart(5, '0');
  return mm + ':' + ss;
}

function addStemMarkerAt(stem, t, label) {
  const list = stemMarkers[stem];
  if (!list) return null;
  if (list.some(m => Math.abs(m.time - t) < 0.05)) return null;
  const marker = { id: 'm' + (++markerIdCounter), time: t, label: label || ('Cue ' + (list.length + 1)), active: list.length === 0 };
  list.push(marker);
  list.sort((a, b) => a.time - b.time);
  renderStemMarkers(stem);
  return marker;
}

function removeStemMarker(stem, id) {
  const list = stemMarkers[stem];
  if (!list) return;
  const wasActive = list.find(m => m.id === id)?.active;
  stemMarkers[stem] = list.filter(m => m.id !== id);
  renderStemMarkers(stem);
}

function setActiveStemMarker(stem, id) {
  const list = stemMarkers[stem];
  if (!list) return;
  list.forEach(m => { m.active = (m.id === id); });
  renderStemMarkers(stem);
  if (transportState === 'playing') {
    const marker = list.find(m => m.id === id);
    if (marker) startStem(stem, masterOffset);
  }
}

function renameStemMarker(stem, id) {
  const list = stemMarkers[stem];
  const marker = list && list.find(m => m.id === id);
  if (!marker) return;
  const next = window.prompt('Label this cue:', marker.label);
  if (next === null) return;
  const trimmed = next.trim();
  if (trimmed) marker.label = trimmed;
  renderStemMarkers(stem);
}

function renderStemMarkers(stem) {
  const row = document.querySelector('.wave-row[data-stem="' + stem + '"]');
  const canvas = row && row.querySelector('.wave-canvas');
  if (!row || !canvas) return;
  row.querySelectorAll('.wave-marker').forEach(el => el.remove());
  const canvasRect = canvas.getBoundingClientRect();
  const rowRect = row.getBoundingClientRect();
  const canvasLeftInRow = canvasRect.left - rowRect.left;
  // Screen px -> layout px (the hero is scaled with CSS transform; see fitHero)
  const layoutK = (canvas.offsetWidth > 0 && canvasRect.width > 0) ? (canvasRect.width / canvas.offsetWidth) : 1;
  (stemMarkers[stem] || []).forEach(marker => {
    const stemDur = (stemBuffers[stem] && stemBuffers[stem].duration) || LOOP_DUR;
    const x = (canvasLeftInRow + (marker.time / stemDur) * canvasRect.width) / layoutK;
    const el = document.createElement('div');
    el.className = 'wave-marker' + (marker.active ? ' active' : '');
    el.style.left = x + 'px';
    el.dataset.label = marker.label;
    el.title = marker.label + ' — ' + formatMarkerTime(marker.time)
      + (marker.active ? ' (start point)' : ' — click to make this the start point')
      + ', double-click to rename, right-click to remove';

    let dragging = false, moved = false, startClientX = 0, startTime = marker.time;
    el.addEventListener('pointerdown', (e) => {
      e.stopPropagation();
      dragging = true; moved = false;
      startClientX = e.clientX; startTime = marker.time;
      el.classList.add('dragging');
      try { el.setPointerCapture(e.pointerId); } catch (err) {}
    });
    el.addEventListener('pointermove', (e) => {
      if (!dragging) return;
      const dx = e.clientX - startClientX;
      if (Math.abs(dx) > 2) moved = true;
      const secPerPx = stemDur / canvasRect.width;
      marker.time = Math.max(0, Math.min(stemDur, startTime + dx * secPerPx));
      el.style.left = ((canvasLeftInRow + (marker.time / stemDur) * canvasRect.width) / layoutK) + 'px';
      el.title = marker.label + ' — ' + formatMarkerTime(marker.time);
    });
    const endDrag = (e) => {
      if (!dragging) return;
      dragging = false;
      el.classList.remove('dragging');
      try { el.releasePointerCapture(e.pointerId); } catch (err) {}
      if (moved) {
        stemMarkers[stem].sort((a, b) => a.time - b.time);
        if (marker.active && transportState === 'playing') startStem(stem, masterOffset);
      }
    };
    el.addEventListener('pointerup', endDrag);
    el.addEventListener('pointercancel', endDrag);
    el.addEventListener('click', (e) => {
      e.stopPropagation();
      if (moved) { moved = false; return; }
      setActiveStemMarker(stem, marker.id);
    });
    el.addEventListener('dblclick', (e) => { e.stopPropagation(); renameStemMarker(stem, marker.id); });
    el.addEventListener('contextmenu', (e) => { e.preventDefault(); e.stopPropagation(); removeStemMarker(stem, marker.id); });
    row.appendChild(el);
  });
}

function renderAllStemMarkers() {
  Object.keys(stemMarkers).forEach(renderStemMarkers);
}

const stemSampleRegions = { vocals: [], drums: [], bass: [], guitar: [], other: [] };
let sampleRegionIdCounter = 0;
let selectedSampleRegion = null;

function hexToRgba(hex, alpha) {
  const h = (hex || '#3CFDE0').replace('#', '');
  const full = h.length === 3 ? h.split('').map(c => c + c).join('') : h;
  const n = parseInt(full, 16);
  const r = (n >> 16) & 255, g = (n >> 8) & 255, b = n & 255;
  return 'rgba(' + r + ',' + g + ',' + b + ',' + alpha + ')';
}

function addStemSampleRegion(stem, startT, endT, label) {
  const list = stemSampleRegions[stem];
  if (!list) return null;
  const lo = Math.min(startT, endT), hi = Math.max(startT, endT);
  if (hi - lo < 0.05) return null;
  const region = { id: 'r' + (++sampleRegionIdCounter), start: lo, end: hi, label: label || ('Chop ' + (list.length + 1)) };
  list.push(region);
  list.sort((a, b) => a.start - b.start);
  selectedSampleRegion = { stem, id: region.id };
  renderStemSampleRegions(stem);
  return region;
}

function removeStemSampleRegion(stem, id) {
  const list = stemSampleRegions[stem];
  if (!list) return;
  stemSampleRegions[stem] = list.filter(r => r.id !== id);
  if (selectedSampleRegion && selectedSampleRegion.id === id) selectedSampleRegion = null;
  renderStemSampleRegions(stem);
}

function renameStemSampleRegion(stem, id) {
  const list = stemSampleRegions[stem];
  const region = list && list.find(r => r.id === id);
  if (!region) return;
  const next = window.prompt('Label this chop:', region.label);
  if (next === null) return;
  const trimmed = next.trim();
  if (trimmed) region.label = trimmed;
  renderStemSampleRegions(stem);
}

function triggerStemSampleRegion(stem, id) {
  const list = stemSampleRegions[stem];
  const region = list && list.find(r => r.id === id);
  if (region && window.__previewRegion) return window.__previewRegion(stem, region);
  const buffer = stemBuffers[stem];
  if (!region || !buffer || !audioCtx) return;
  const dur = Math.min(region.end, buffer.duration) - region.start;
  if (dur <= 0) return;
  try {
    const src = audioCtx.createBufferSource();
    src.buffer = buffer;
    const gain = audioCtx.createGain();
    gain.gain.value = 0.9;
    src.connect(gain);
    gain.connect(audioCtx.destination);
    src.start(0, region.start, dur);
  } catch (e) {
    console.warn('Sample trigger failed', e);
  }
}

function renderStemSampleRegions(stem) {
  const row = document.querySelector('.wave-row[data-stem="' + stem + '"]');
  const wrap = row && row.querySelector('.wave-canvas-wrap');
  const canvas = row && row.querySelector('.wave-canvas');
  if (!row || !wrap || !canvas) return;
  wrap.querySelectorAll('.wave-sample-region').forEach(el => el.remove());
  const canvasRect = canvas.getBoundingClientRect();
  const regionK = (canvas.offsetWidth > 0 && canvasRect.width > 0) ? (canvasRect.width / canvas.offsetWidth) : 1;
  const stemDur = (stemBuffers[stem] && stemBuffers[stem].duration) || LOOP_DUR;
  const color = '#FFD23C'; // fixed bright selection color so it never blends into the stem's own waveform color

  (stemSampleRegions[stem] || []).forEach(region => {
    const el = document.createElement('div');
    el.className = 'wave-sample-region';
    el.dataset.label = region.label;
    el.style.setProperty('--region-color', color);
    el.style.background = hexToRgba(color, 0.32);
    if (selectedSampleRegion && selectedSampleRegion.id === region.id) el.classList.add('selected');

    const place = () => {
      const x1 = ((region.start / stemDur) * canvasRect.width) / regionK;
      const x2 = ((region.end / stemDur) * canvasRect.width) / regionK;
      el.style.left = x1 + 'px';
      el.style.width = Math.max(2, x2 - x1) + 'px';
    };
    place();
    el.title = region.label + ' — ' + formatMarkerTime(region.start) + ' to ' + formatMarkerTime(region.end)
      + ' — click to play, drag to move, drag edges to trim, double-click to rename, right-click to remove';

    const playBtn = document.createElement('button');
    playBtn.type = 'button';
    playBtn.className = 'wave-sample-play';
    playBtn.setAttribute('aria-label', 'Play ' + region.label);
    playBtn.textContent = '▶';
    playBtn.addEventListener('pointerdown', (e) => e.stopPropagation());
    playBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      triggerStemSampleRegion(stem, region.id);
    });
    el.appendChild(playBtn);

    const startHandle = document.createElement('div');
    startHandle.className = 'wave-sample-handle wave-sample-handle-start';
    el.appendChild(startHandle);
    const endHandle = document.createElement('div');
    endHandle.className = 'wave-sample-handle wave-sample-handle-end';
    el.appendChild(endHandle);

    function wireHandle(handleEl, edge) {
      let dragging = false, startClientX = 0, startVal = 0;
      handleEl.addEventListener('pointerdown', (e) => {
        e.stopPropagation();
        dragging = true;
        startClientX = e.clientX;
        startVal = edge === 'start' ? region.start : region.end;
        try { handleEl.setPointerCapture(e.pointerId); } catch (err) {}
      });
      handleEl.addEventListener('pointermove', (e) => {
        if (!dragging) return;
        const dx = e.clientX - startClientX;
        const secPerPx = stemDur / canvasRect.width;
        let val = startVal + dx * secPerPx;
        if (edge === 'start') {
          region.start = Math.max(0, Math.min(region.end - 0.05, val));
        } else {
          region.end = Math.min(stemDur, Math.max(region.start + 0.05, val));
        }
        place();
      });
      const endDrag = (e) => {
        if (!dragging) return;
        dragging = false;
        try { handleEl.releasePointerCapture(e.pointerId); } catch (err) {}
        stemSampleRegions[stem].sort((a, b) => a.start - b.start);
      };
      handleEl.addEventListener('pointerup', endDrag);
      handleEl.addEventListener('pointercancel', endDrag);
    }
    wireHandle(startHandle, 'start');
    wireHandle(endHandle, 'end');

    // Drag the whole chopped piece left/right (edges still trim it)
    el.style.cursor = 'grab';
    let bodyDrag = false, bmoved = false, bx0 = 0, bs0 = 0, be0 = 0;
    el.addEventListener('pointerdown', (e) => {
      if (e.button !== 0) return;
      e.stopPropagation();
      bodyDrag = true; bmoved = false; bx0 = e.clientX; bs0 = region.start; be0 = region.end;
      try { el.setPointerCapture(e.pointerId); } catch (err) {}
    });
    el.addEventListener('pointermove', (e) => {
      if (!bodyDrag) return;
      const dx = e.clientX - bx0;
      if (Math.abs(dx) > 3) bmoved = true;
      if (!bmoved) return;
      const len = be0 - bs0;
      const ns = Math.max(0, Math.min(stemDur - len, bs0 + dx * (stemDur / canvasRect.width)));
      region.start = ns; region.end = ns + len;
      place();
    });
    const endBodyDrag = (e) => {
      if (!bodyDrag) return;
      bodyDrag = false;
      try { el.releasePointerCapture(e.pointerId); } catch (err) {}
      if (bmoved) { el._justMoved = true; stemSampleRegions[stem].sort((a, b) => a.start - b.start); }
    };
    el.addEventListener('pointerup', endBodyDrag);
    el.addEventListener('pointercancel', endBodyDrag);

    el.addEventListener('click', (e) => {
      e.stopPropagation();
      if (el._justMoved) { el._justMoved = false; return; }
      selectedSampleRegion = { stem, id: region.id };
      document.querySelectorAll('.wave-sample-region.selected').forEach(x => x.classList.remove('selected'));
      el.classList.add('selected');
      triggerStemSampleRegion(stem, region.id);
    });
    el.addEventListener('dblclick', (e) => { e.stopPropagation(); renameStemSampleRegion(stem, region.id); });
    el.addEventListener('contextmenu', (e) => { e.preventDefault(); e.stopPropagation(); if (window.__showSampleMenu) window.__showSampleMenu(stem, region, e); else removeStemSampleRegion(stem, region.id); });

    wrap.appendChild(el);
  });
}

document.addEventListener('keydown', (e) => {
  if (e.key !== 'Delete' && e.key !== 'Backspace') return;
  const t = e.target;
  if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return;
  if (!selectedSampleRegion) return;
  e.preventDefault();
  removeStemSampleRegion(selectedSampleRegion.stem, selectedSampleRegion.id);
});

// Spacebar toggles play/pause, like every other DAW/mixer out there.
document.addEventListener('keydown', (e) => {
  if (e.code !== 'Space' && e.key !== ' ') return;
  const t = e.target;
  if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return;
  e.preventDefault();
  // If the library is auditioning a sample/stem/mix, space stops that first.
  if (window.__stopAuditions && window.__stopAuditions()) return;
  if (isPlaying) {
    pausePreview();
  } else {
    playPreview();
  }
});
// A focused button would otherwise ALSO "click" when space is released.
document.addEventListener('keyup', (e) => {
  if (e.code !== 'Space' && e.key !== ' ') return;
  const t = e.target;
  if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return;
  e.preventDefault();
});
document.addEventListener('pointerdown', (e) => {
  if (!e.target.closest('.wave-sample-region')) {
    selectedSampleRegion = null;
    document.querySelectorAll('.wave-sample-region.selected').forEach(x => x.classList.remove('selected'));
  }
});

function renderAllStemSampleRegions() {
  Object.keys(stemSampleRegions).forEach(renderStemSampleRegions);
}

// FIX 1: playhead scrub now uses the real song length (getMasterDuration)
// instead of the old hardcoded 6-second LOOP_DUR, matching the click-to-seek
// and playback behavior elsewhere in the file.
(function setupPlayheadScrub() {
  const rowsEl = document.getElementById('waveformRows');
  if (!rowsEl) return;
  const GRAB_PX = 10;
  let scrubbing = false;

  const scrubTo = (clientX) => {
    // FIX: same canvas-width bug as updatePlayheadPosition -- scrub range
    // was capped at the canvas edge, so you couldn't drag the playhead
    // into the last stretch of the row. Use the full wave-canvas-wrap.
    const firstWrap = document.querySelector('.wave-row .wave-canvas-wrap');
    if (!firstWrap) return;
    const rect = firstWrap.getBoundingClientRect();
    const fraction = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
    scrubMove(fraction * getMasterDuration());
  };

  rowsEl.addEventListener('pointerdown', (e) => {
    // Measure against the yellow line's real on-screen position so the
    // grab zone sits exactly on it.
    const ph = document.getElementById('wavePlayhead');
    if (!ph) return;
    const phRect = ph.getBoundingClientRect();
    if (Math.abs(e.clientX - (phRect.left + phRect.width / 2)) > GRAB_PX) return;
    scrubbing = true;
    beginScrub();
    rowsEl.classList.add('scrubbing');
    try { rowsEl.setPointerCapture(e.pointerId); } catch (err) {}
    e.stopPropagation();
    e.preventDefault();
  }, true);

  rowsEl.addEventListener('pointermove', (e) => {
    if (!scrubbing) return;
    scrubTo(e.clientX);
  });

  // Was named endScrub, which shadowed the global endScrub() and called
  // itself, so the release step (restart audio, clear the hold) never ran.
  const endPlayheadScrub = (e) => {
    if (!scrubbing) return;
    scrubbing = false;
    endScrub();
    rowsEl.classList.remove('scrubbing');
    try { rowsEl.releasePointerCapture(e.pointerId); } catch (err) {}
  };
  rowsEl.addEventListener('pointerup', endPlayheadScrub);
  rowsEl.addEventListener('pointercancel', endPlayheadScrub);
})();

document.addEventListener('DOMContentLoaded', () => {
  initScope();
  requestAnimationFrame(scopeLoop);
  document.getElementById('playBtn')?.addEventListener('click', playPreview);
  document.getElementById('pauseBtn')?.addEventListener('click', pausePreview);
  document.getElementById('stopBtn')?.addEventListener('click', stopPreview);

  renderStemWaveforms();
  document.getElementById('wavePlayhead')?.classList.add('on');
  updatePlayheadPosition();
  renderAllStemMarkers();
  renderAllStemSampleRegions();
  window.addEventListener('resize', () => { updatePlayheadPosition(); renderAllStemMarkers(); renderAllStemSampleRegions(); });

  document.querySelectorAll('.wave-canvas').forEach(canvas => {
    canvas.addEventListener('click', (e) => {
      if (canvas._suppressClick) { canvas._suppressClick = false; return; }
      // Use the same reference box as the playhead (wave-canvas-wrap) so a
      // click lands exactly on the yellow line instead of an inch off.
      const rect = (document.querySelector('.wave-row .wave-canvas-wrap') || canvas).getBoundingClientRect();
      const fraction = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
      seekTo(fraction * getMasterDuration());
    });
    canvas.addEventListener('dblclick', (e) => {
      const row = canvas.closest('.wave-row');
      const stem = row && row.dataset.stem;
      if (!stem) return;
      const rect = canvas.getBoundingClientRect();
      const fraction = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
      const dur = (stemBuffers[stem] && stemBuffers[stem].duration) || LOOP_DUR;
      addStemMarkerAt(stem, fraction * dur);
    });
  });

  document.querySelectorAll('.add-marker-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const stem = btn.dataset.stem;
      if (!stem) return;
      addStemMarkerAt(stem, currentPlaybackTime());
    });
  });

  // SAMPLE toggle button is hidden in the UI now (see CSS: display:none)
  // so this wiring stays for future re-enable but sampleModeByStem will
  // always read false from here on -- Shift+drag remains the only way
  // to reach the chop handler below.
  document.querySelectorAll('.sample-toggle-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const stem = btn.dataset.stem;
      if (!stem || !(stem in sampleModeByStem)) return;
      sampleModeByStem[stem] = !sampleModeByStem[stem];
      btn.classList.toggle('active', sampleModeByStem[stem]);
      const row = document.querySelector('.wave-row[data-stem="' + stem + '"]');
      if (row) row.classList.toggle('sampling-mode', sampleModeByStem[stem]);
    });
  });

  // ===== Drag-on-wave now scrubs the shared playhead only =====
  // Plain click-drag (no Shift) on ANY stem's waveform seeks the whole
  // song continuously as you drag -- it does NOT nudge that stem's
  // timing and does NOT touch the underlying audio buffer. Shift+drag
  // still reaches the sample-chop handler below.
  document.querySelectorAll('.wave-row').forEach(row => {
    const stem = row.dataset.stem;
    const canvas = row.querySelector('.wave-canvas');
    if (!canvas || !(stem in stemNudge)) return;
    let dragging = false;
    let moved = false;

    const scrubFromEvent = (e) => {
      const rect = (document.querySelector('.wave-row .wave-canvas-wrap') || canvas).getBoundingClientRect();
      const fraction = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
      scrubMove(fraction * getMasterDuration());
    };

    canvas.addEventListener('pointerdown', (e) => {
      if (e.button !== 0) return;
      if (e.shiftKey || sampleModeByStem[stem]) return; // sample-chop handler takes this drag instead
      canvas.setPointerCapture(e.pointerId);
      dragging = true;
      moved = false;
      beginScrub();
      canvas.classList.add('dragging');
      scrubFromEvent(e);
    });
    canvas.addEventListener('pointermove', (e) => {
      if (!dragging) return;
      moved = true;
      scrubFromEvent(e);
    });
    const endDrag = (e) => {
      if (!dragging) return;
      dragging = false;
      endScrub();
      canvas.classList.remove('dragging');
      if (moved) canvas._suppressClick = true;
      try { canvas.releasePointerCapture(e.pointerId); } catch (err) {}
    };
    canvas.addEventListener('pointerup', endDrag);
    canvas.addEventListener('pointercancel', endDrag);
  });

  // ===== Sample chopping: Shift+drag only (SAMPLE toggle button hidden) =====
  document.querySelectorAll('.wave-row').forEach(row => {
    const stem = row.dataset.stem;
    const canvas = row.querySelector('.wave-canvas');
    const wrap = row.querySelector('.wave-canvas-wrap');
    if (!canvas || !wrap || !(stem in stemSampleRegions)) return;
    let selecting = false;
    let startX = 0;
    let ghostEl = null;

    canvas.addEventListener('pointerdown', (e) => {
      if (e.button !== 0) return;
      return; // sampling/editing moved to the Sampler page (/sampler); scrub handler takes this drag
      canvas.setPointerCapture(e.pointerId);
      selecting = true;
      startX = e.clientX;
      ghostEl = document.createElement('div');
      ghostEl.className = 'wave-sample-region wave-sample-region-ghost';
      wrap.appendChild(ghostEl);
    });
    canvas.addEventListener('pointermove', (e) => {
      if (!selecting || !ghostEl) return;
      const rect = canvas.getBoundingClientRect();
      const x1 = Math.max(0, Math.min(rect.width, startX - rect.left));
      const x2 = Math.max(0, Math.min(rect.width, e.clientX - rect.left));
      ghostEl.style.left = Math.min(x1, x2) + 'px';
      ghostEl.style.width = Math.max(1, Math.abs(x2 - x1)) + 'px';
    });
    const endSelect = (e) => {
      if (!selecting) return;
      selecting = false;
      const rect = canvas.getBoundingClientRect();
      const stemDur = (stemBuffers[stem] && stemBuffers[stem].duration) || LOOP_DUR;
      const xStart = Math.max(0, Math.min(rect.width, startX - rect.left));
      const xEnd = Math.max(0, Math.min(rect.width, e.clientX - rect.left));
      if (ghostEl) { ghostEl.remove(); ghostEl = null; }
      const secPerPx = stemDur / rect.width;
      // FIX: only suppress the trailing click when a region was actually
      // created. Previously this was set unconditionally, which silently
      // broke plain click-to-seek any time a shift-drag/sample-mode drag
      // was too small to register as a chop.
      const region = addStemSampleRegion(stem, xStart * secPerPx, xEnd * secPerPx);
      if (region) canvas._suppressClick = true;
      try { canvas.releasePointerCapture(e.pointerId); } catch (err) {}
    };
    canvas.addEventListener('pointerup', endSelect);
    canvas.addEventListener('pointercancel', endSelect);
  });

  const waveformRows = document.getElementById('waveformRows');
  const screenStemList = document.getElementById('screenStemList');
  const screenTitle = document.getElementById('screenTitle');
  document.querySelectorAll('.screen-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.screen-tab').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      const view = tab.dataset.view;
      if (waveformRows) waveformRows.style.display = view === 'waves' ? 'flex' : 'none';
      if (screenStemList) screenStemList.style.display = view === 'stems' ? 'block' : 'none';
      const sampleLib = document.getElementById('sampleLibList');
      if (sampleLib) { sampleLib.style.display = view === 'samples' ? 'flex' : 'none'; if (view === 'samples' && window.__renderLibrary) window.__renderLibrary(); }
      const browseBar = document.getElementById('screenBrowse');
      if (browseBar) browseBar.style.display = view === 'stems' ? 'flex' : 'none';
      if (screenTitle) screenTitle.textContent = view === 'waves' ? 'STEM WAVEFORMS' : (view === 'samples' ? 'SAMPLE LIBRARY' : 'MY STEMS');
    });
  });

  const browseKnob = document.getElementById('browseKnob');
  const browseReadout = document.getElementById('browseReadout');

  function showStemsView() {
    const stemsTab = document.querySelector('.screen-tab[data-view="stems"]');
    if (stemsTab && !stemsTab.classList.contains('active')) stemsTab.click();
  }

  function browseRows() {
    return Array.from(document.querySelectorAll('#screenStemList .screen-row'))
      .filter(r => r.style.display !== 'none');
  }

  function updateBrowseReadout() {
    if (!browseReadout) return;
    const rows = browseRows();
    const sel = rows.findIndex(r => r.classList.contains('selected'));
    browseReadout.textContent = (sel >= 0 && rows.length)
      ? (sel + 1) + '/' + rows.length
      : 'SCROLL';
  }

  function moveSelection(dir) {
    const rows = browseRows();
    if (!rows.length) return;
    showStemsView();
    let idx = rows.findIndex(r => r.classList.contains('selected'));
    idx = idx < 0 ? 0 : idx + dir;
    idx = Math.min(rows.length - 1, Math.max(0, idx));
    rows.forEach(r => r.classList.remove('selected'));
    rows[idx].classList.add('selected');
    rows[idx].scrollIntoView({ block: 'nearest' });
    updateBrowseReadout();
  }

  if (browseKnob) {
    setupEncoder(browseKnob, {
      onStep: dir => moveSelection(dir),
      onClick: () => {
        const sel = document.querySelector('#screenStemList .screen-row.selected');
        if (sel) sel.querySelector('.assign-btn')?.click();
        else moveSelection(1);
      }
    });
  }
  window.__updateBrowseReadout = updateBrowseReadout;

  const STEM_GROUPS = [
    { key: 'all',    label: 'ALL STEMS', accent: '#3CFDE0' },
    { key: 'vocals', label: 'VOCALS',    accent: '#ff5540' },
    { key: 'drums',  label: 'DRUMS',     accent: '#ffa022' },
    { key: 'bass',   label: 'BASS',      accent: '#2fe08a' },
    { key: 'guitar', label: 'GUITAR',    accent: '#9b6dff' },
    { key: 'other',  label: 'OTHER',     accent: '#3ab6ff' }
  ];
  let groupIdx = 0;
  let searchTerm = '';

  function applyBrowseFilter() {
    const group = STEM_GROUPS[groupIdx];
    const rows = Array.from(document.querySelectorAll('#screenStemList .screen-row'));
    let shown = 0;
    rows.forEach(row => {
      const type = row.dataset.stemType || '';
      const name = (row.dataset.trackName || '').toLowerCase();
      const okGroup = group.key === 'all' || type === group.key;
      const okSearch = !searchTerm || name.includes(searchTerm);
      const visible = okGroup && okSearch;
      row.style.display = visible ? '' : 'none';
      if (visible) shown++;
      if (!visible) row.classList.remove('selected');
    });

    const nameEl = document.getElementById('grpName');
    const countEl = document.getElementById('grpCount');
    if (nameEl) { nameEl.textContent = group.label; nameEl.style.setProperty('--grp-accent', group.accent); }
    if (countEl) countEl.textContent = shown + (searchTerm ? ' FOUND' : '');

    if (!document.querySelector('#screenStemList .screen-row.selected')) {
      const first = rows.find(r => r.style.display !== 'none');
      if (first) first.classList.add('selected');
    }
    updateBrowseReadout();
  }

  function stepGroup(dir) {
    groupIdx = (groupIdx + dir + STEM_GROUPS.length) % STEM_GROUPS.length;
    applyBrowseFilter();
  }

  document.getElementById('grpPrev')?.addEventListener('click', () => stepGroup(-1));
  document.getElementById('grpNext')?.addEventListener('click', () => stepGroup(1));

  const stemSearch = document.getElementById('stemSearch');
  stemSearch?.addEventListener('input', e => {
    searchTerm = e.target.value.trim().toLowerCase();
    applyBrowseFilter();
  });
  stemSearch?.addEventListener('keydown', e => {
    if (e.key === 'Escape') { e.target.value = ''; searchTerm = ''; applyBrowseFilter(); e.target.blur(); }
  });
  window.__applyBrowseFilter = applyBrowseFilter;

  document.querySelectorAll('.channel').forEach(channel => {
    const stem = channel.dataset.stem;
    const ensure = () => {
      if (!stemNodes[stem]) {
        const eqDef = EQ_DEFAULTS[stem] || {};
        stemNodes[stem] = { volPct: 78, trimDb: 0, eqLowDb: eqDef.low || 0, eqMidDb: eqDef.mid || 0, eqHighDb: eqDef.high || 0, muted: false, solo: false };
      }
      return stemNodes[stem];
    };

    const slot = channel.querySelector('.fader-slot');
    const cap = channel.querySelector('.fader-cap');
    const muteBtn = channel.querySelector('.mute-btn');
    const cueBtn = channel.querySelector('.cue-btn');
    const gainKnob = channel.querySelector('.knob[data-role="gain"]');

    const fader = setupFader(slot, cap, {
      initial: 78,
      onChange: pct => {
        const n = ensure(); n.volPct = pct;
        updateAllChannelGains();
      }
    });

    if (gainKnob) {
      setupKnob(gainKnob, {
        min: -12, max: 12, initial: 0,
        onChange: db => {
          const n = ensure(); n.trimDb = db;
          if (n.trimNode) n.trimNode.gain.value = dbToGain(db);
        }
      });
    }

    channel.querySelectorAll('.knob-xs').forEach(k => {
      const band = k.dataset.eq;
      const eqDef = EQ_DEFAULTS[stem] || {};
      const initVal = eqDef[band] || 0;
      setupKnob(k, {
        min: -12, max: 12, initial: initVal,
        onChange: db => {
          const n = ensure();
          if (band === 'high') { n.eqHighDb = db; if (n.eqHigh) n.eqHigh.gain.value = db; }
          if (band === 'mid') { n.eqMidDb = db; if (n.eqMid) n.eqMid.gain.value = db; }
          if (band === 'low') { n.eqLowDb = db; if (n.eqLow) n.eqLow.gain.value = db; }
        }
      });
    });

    const statusLed = channel.querySelector('.status-led');

    muteBtn.addEventListener('click', () => {
      const active = muteBtn.classList.toggle('active');
      const n = ensure();
      n.muted = active;
      updateAllChannelGains();
      if (statusLed) statusLed.classList.toggle('muted', active);
    });

    if (cueBtn) {
      cueBtn.addEventListener('click', () => {
        const active = cueBtn.classList.toggle('active');
        const n = ensure();
        n.solo = active;
        updateAllChannelGains();
      });
    }
  });

  const tempoKnob = document.getElementById('tempoKnob');
  const tempoReadout = document.getElementById('tempoReadout');
  if (tempoKnob) {
    setupKnob(tempoKnob, {
      min: 60, max: 180, initial: BASE_BPM,
      onChange: bpm => {
        const rounded = Math.round(bpm);
        tempoReadout.textContent = rounded + ' BPM';
        const lcdBpm = document.getElementById('lcdBpm');
        if (lcdBpm) lcdBpm.textContent = rounded.toFixed(1);
        const posNow = currentPlaybackTime();
        tempoRatio = rounded / BASE_BPM;
        if (transportState === 'playing' && audioCtx) {
          masterOffset = posNow;
          playStartCtxTime = audioCtx.currentTime;
          Object.entries(activeSources).forEach(([name, src]) => {
            if (src) try { src.playbackRate.value = tempoRatio * (stemAutoStretch[name] || 1); } catch (e) {}
          });
        }
        applyKeyShift();
      }
    });
  }

  const keyKnob = document.getElementById('keyKnob');
  const keyReadout = document.getElementById('keyReadout');
  if (keyKnob) {
    setupKnob(keyKnob, {
      min: -12, max: 12, initial: 0,
      onChange: semis => {
        keySemitones = Math.round(semis);
        keyReadout.textContent = keyLabel(keySemitones);
        const lcdKey = document.getElementById('lcdKey');
        if (lcdKey) {
          const m = keyLabel(keySemitones).match(/\(([^)]+)\)/);
          lcdKey.textContent = m ? m[1] : keyLabel(keySemitones);
        }
        applyKeyShift();
      }
    });
  }

  const keyLockBtn = document.getElementById('keyLockBtn');
  if (keyLockBtn) {
    keyLockBtn.classList.toggle('active', keyLockOn);
    keyLockBtn.addEventListener('click', () => {
      keyLockOn = !keyLockOn;
      keyLockBtn.classList.toggle('active', keyLockOn);
      applyKeyShift();
    });
  }

  const masterVolKnob = document.getElementById('masterVolKnob');
  const masterVolReadout = document.getElementById('masterVolReadout');
  if (masterVolKnob) {
    setupKnob(masterVolKnob, {
      min: 0, max: 100, initial: 80,
      onChange: pct => {
        const rounded = Math.round(pct);
        masterVolReadout.textContent = rounded + '%';
        masterVolPct = rounded;
        if (masterGain) masterGain.gain.value = rounded / 100;
      }
    });
  }

  const cueOutBtn = document.getElementById('cueOutBtn');
  const cueOutStatus = document.getElementById('cueOutStatus');
  async function pickCueOutputDevice() {
    const cueEl = document.getElementById('cueMonitorAudio');
    if (!cueEl || !('setSinkId' in HTMLMediaElement.prototype)) {
      if (cueOutStatus) cueOutStatus.textContent = 'Not supported here';
      return;
    }
    try {
      await ensureEngineReady();
      let deviceId = null;
      if (navigator.mediaDevices && navigator.mediaDevices.selectAudioOutput) {
        const device = await navigator.mediaDevices.selectAudioOutput();
        deviceId = device.deviceId;
      } else {
        await navigator.mediaDevices.getUserMedia({ audio: true });
        const devices = await navigator.mediaDevices.enumerateDevices();
        const outputs = devices.filter(d => d.kind === 'audiooutput');
        if (!outputs.length) throw new Error('no output devices found');
        deviceId = outputs[0].deviceId;
      }
      await cueEl.setSinkId(deviceId);
      if (cueOutStatus) cueOutStatus.textContent = 'Cue \u2192 headphones';
      if (cueOutBtn) cueOutBtn.classList.add('active');
    } catch (e) {
      console.error('Cue output device selection failed', e);
      if (cueOutStatus) cueOutStatus.textContent = 'Selection failed';
    }
  }
  if (cueOutBtn) cueOutBtn.addEventListener('click', pickCueOutputDevice);
});

