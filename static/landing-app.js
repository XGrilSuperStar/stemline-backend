/* ===== STEMLINE SAMPLER: one pad per stem + sample library ===== */
(function () {
  const COLORS = { vocals:'#ff5540', drums:'#ffa022', bass:'#2fe08a', guitar:'#9b6dff', other:'#3ab6ff' };
  const PAD_KEY = 'stemline_pad_assign';
  const PAD_PAD = 2; // seconds of extra audio kept each side for retrimming
  let lib = [];
  let mixes = [];
  let mixBusy = false;
  let mixAudio = null, mixAudioId = null;
  const playing = {}; // padStem -> {src}
  let libPlaying = null;

  /* ---------- storage ---------- */
  let dbp = null;
  function db() {
    if (dbp) return dbp;
    dbp = new Promise((res, rej) => {
      try {
        const rq = indexedDB.open('stemline_samples', 2);
        rq.onupgradeneeded = () => {
          const d = rq.result;
          if (!d.objectStoreNames.contains('samples')) d.createObjectStore('samples', { keyPath: 'id' });
          if (!d.objectStoreNames.contains('mixes')) d.createObjectStore('mixes', { keyPath: 'id' });
        };
        rq.onsuccess = () => res(rq.result);
        rq.onerror = () => rej(rq.error);
      } catch (e) { rej(e); }
    });
    return dbp;
  }
  async function idbPut(item) { try { const d = await db(); d.transaction('samples','readwrite').objectStore('samples').put(item); } catch (e) { console.warn('save failed', e); } }
  async function idbDel(id) { try { const d = await db(); d.transaction('samples','readwrite').objectStore('samples').delete(id); } catch (e) {} }
  async function idbAll() {
    try { const d = await db(); return await new Promise((res, rej) => { const r = d.transaction('samples').objectStore('samples').getAll(); r.onsuccess = () => res(r.result || []); r.onerror = () => rej(r.error); }); }
    catch (e) { return []; }
  }
  async function mixPut(item) { try { const d = await db(); d.transaction('mixes','readwrite').objectStore('mixes').put(item); } catch (e) { console.warn('mix save failed', e); } }
  async function mixDel(id) { try { const d = await db(); d.transaction('mixes','readwrite').objectStore('mixes').delete(id); } catch (e) {} }
  async function mixAll() {
    try { const d = await db(); return await new Promise((res, rej) => { const r = d.transaction('mixes').objectStore('mixes').getAll(); r.onsuccess = () => res(r.result || []); r.onerror = () => rej(r.error); }); }
    catch (e) { return []; }
  }
  function getAssign() { try { return JSON.parse(localStorage.getItem(PAD_KEY)) || {}; } catch (e) { return {}; } }
  function setAssign(a) { try { localStorage.setItem(PAD_KEY, JSON.stringify(a)); } catch (e) {} }

  /* ---------- helpers ---------- */
  function toast(msg) {
    let t = document.getElementById('samplerToast');
    if (!t) { t = document.createElement('div'); t.id = 'samplerToast'; document.body.appendChild(t); }
    t.textContent = msg; t.classList.add('show');
    clearTimeout(t._t); t._t = setTimeout(() => t.classList.remove('show'), 2200);
  }
  function cueReady() { const b = document.getElementById('cueOutBtn'); return !!(b && b.classList.contains('active')); }
  function songPlaying() { try { return !!isPlaying; } catch (e) { return false; } }

  async function playItem(item, dest, onStart, onEnd, padStem) {
    if (dest === 'cue' && !cueReady()) { toast('Pick CUE OUT (headphones) first'); return null; }
    let audition = false;
    if (dest === 'main-safe') { // library audition: headphones if set, else straight to main (layers over the song if it's playing)
      audition = true;
      dest = cueReady() ? 'cue' : 'main';
    }
    try { await ensureEngineReady(); } catch (e) {}
    if (!audioCtx) return null;
    const sr = item.sr, len = item.data[0].length;
    const buf = audioCtx.createBuffer(item.data.length, len, sr);
    item.data.forEach((ch, i) => buf.copyToChannel(ch, i));
    const src = audioCtx.createBufferSource();
    src.buffer = buf;
    const g = audioCtx.createGain(); g.gain.value = 0.95;
    src.connect(g);
    if (dest === 'cue') { if (!cueBus) return null; g.connect(cueBus); }
    else {
      if (audition) {
        // library preview: straight to master so channel mute / solo / fader can never silence it
        g.connect(masterGain);
      } else {
        // pad fire: plug in BEFORE the channel fader so volume / mute / solo control the sample
        const n = stemNodes[padStem || item.stem];
        g.connect(n && n.gainNode ? n.gainNode : (n && n.analyser ? n.analyser : masterGain));
      }
    }
    const dur = Math.max(0.02, item.outT - item.inT);
    src.onended = () => { try { g.disconnect(); } catch (e) {} if (onEnd) onEnd(); };
    src.start(0, item.inT, dur);
    if (onStart) onStart();
    return { src, g };
  }

  function sliceFromBuffer(stem, start, end) {
    const buf = stemBuffers[stem];
    if (!buf) return null;
    const s0 = Math.max(0, start - PAD_PAD), s1 = Math.min(buf.duration, end + PAD_PAD);
    const i0 = Math.floor(s0 * buf.sampleRate), i1 = Math.floor(s1 * buf.sampleRate);
    const data = [];
    for (let c = 0; c < buf.numberOfChannels; c++) data.push(buf.getChannelData(c).slice(i0, i1));
    return { sr: buf.sampleRate, data, inT: start - s0, outT: end - s0 };
  }

  /* ---------- pads ---------- */
  function padEl(stem) { return document.querySelector('.sampler-pad[data-pad="' + stem + '"]'); }
  function itemById(id) { return lib.find(x => x.id === id); }

  function refreshPads() {
    const a = getAssign();
    Object.keys(COLORS).forEach(stem => {
      const p = padEl(stem); if (!p) return;
      const it = a[stem] && itemById(a[stem]);
      p.classList.toggle('has-sample', !!it);
      p.title = it ? (it.name + ' - click to fire, right-click to clear') : 'Empty pad - right-click a waveform region, Save sample';
      const lab = p.querySelector('span:not(.pad-label)'); if (lab) lab.textContent = it ? it.name.slice(0, 6) : '';
    });
  }

  async function firePad(stem) {
    const a = getAssign(); const it = a[stem] && itemById(a[stem]);
    const p = padEl(stem);
    // Always give a quick visible flash on click, even on an empty pad,
    // so clicking never looks like nothing happened.
    if (p) {
      p.classList.add('flash');
      setTimeout(() => p.classList.remove('flash'), 180);
    }
    if (!it) { toast('Empty pad: cut a region, right-click, Save sample'); return; }
    const hp = document.querySelector('.pad-hp[data-hp="' + stem + '"]');
    const dest = hp && hp.classList.contains('on') ? 'cue' : 'main';
    if (playing[stem]) { try { playing[stem].src.stop(); } catch (e) {} }
    const h = await playItem(it, dest, () => p.classList.add('lit'), () => { if (playing[stem] === h) { delete playing[stem]; p.classList.remove('lit'); } }, stem);
    if (h) playing[stem] = h;
  }

  const sampleHelpBtn = document.getElementById('sampleHelpBtn');
  const sampleHelpPop = document.getElementById('sampleHelpPop');
  const sampleHelpClose = document.getElementById('sampleHelpClose');
  if (sampleHelpBtn && sampleHelpPop) {
    sampleHelpBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      sampleHelpPop.style.display = sampleHelpPop.style.display === 'none' ? 'block' : 'none';
    });
  }
  if (sampleHelpClose && sampleHelpPop) {
    sampleHelpClose.addEventListener('click', () => { sampleHelpPop.style.display = 'none'; });
  }
  document.addEventListener('click', (e) => {
    if (sampleHelpPop && sampleHelpPop.style.display === 'block' && !sampleHelpPop.contains(e.target) && e.target !== sampleHelpBtn) {
      sampleHelpPop.style.display = 'none';
    }
  });

  function wirePads() {
    Object.keys(COLORS).forEach(stem => {
      const p = padEl(stem); if (!p) return;
      p.addEventListener('click', () => firePad(stem));
      p.addEventListener('contextmenu', (e) => {
        e.preventDefault();
        const a = getAssign(); if (!a[stem]) return;
        delete a[stem]; setAssign(a); refreshPads(); toast('Pad cleared');
      });
      const hp = document.querySelector('.pad-hp[data-hp="' + stem + '"]');
      if (hp) hp.addEventListener('click', () => {
        if (!hp.classList.contains('on') && !cueReady()) {
          toast('Pick CUE OUT (headphones) first');
          hp.classList.add('flash');
          setTimeout(() => hp.classList.remove('flash'), 180);
          return;
        }
        hp.classList.toggle('on');
      });
    });
  }

  /* ---------- save menu (from waveform region right-click) ---------- */
  function closeMenu() { const m = document.getElementById('samplerMenu'); if (m) m.remove(); }
  window.__showSampleMenu = function (stem, region, ev) {
    closeMenu();
    const m = document.createElement('div'); m.id = 'samplerMenu';
    m.style.left = Math.min(ev.clientX, innerWidth - 150) + 'px';
    m.style.top = Math.min(ev.clientY, innerHeight - 110) + 'px';
    m.style.setProperty('--pc', COLORS[stem] || '#fff');
    const mk = (label, fn) => { const b = document.createElement('button'); b.type = 'button'; b.textContent = label; b.onclick = () => { closeMenu(); fn(); }; m.appendChild(b); };
    mk('Save sample', () => saveRegion(stem, region));
    mk('Delete region', () => removeStemSampleRegion(stem, region.id));
    document.body.appendChild(m);
    setTimeout(() => document.addEventListener('pointerdown', function h(e) { if (!m.contains(e.target)) { closeMenu(); document.removeEventListener('pointerdown', h); } }), 0);
  };
  window.__previewRegion = function (stem, region) {
    const s = sliceFromBuffer(stem, region.start, region.end);
    if (!s) return;
    playItem({ stem, sr: s.sr, data: s.data, inT: s.inT, outT: s.outT }, 'main-safe');
  };

  async function saveRegion(stem, region) {
    const s = sliceFromBuffer(stem, region.start, region.end);
    if (!s) { toast('Nothing to save'); return; }
    const name = (window.prompt('Name this sample:', region.label || 'Sample') || '').trim();
    if (!name) return;
    const item = { id: 's' + Date.now() + Math.floor(Math.random() * 1000), stem, name, sr: s.sr, data: s.data, inT: s.inT, outT: s.outT };
    lib.push(item); await idbPut(item);
    const a = getAssign(); a[stem] = item.id; setAssign(a);
    refreshPads(); renderLibrary();
    toast('Saved to ' + stem + ' pad');
  }

  /* ---------- save mix (render current mix -> MP3, kept in library) ---------- */
  async function renderMixBuffer() {
    const real = hasRealSong();
    const anySolo = Object.values(stemNodes).some(n => n.solo);
    const plans = [];
    let outDur = 0;
    Object.keys(stemBuffers).forEach(name => {
      const n = stemNodes[name], buffer = stemBuffers[name];
      if (!n || !buffer || (real && !currentStemMeta[name])) return;
      if (n.muted || (anySolo && !n.solo)) return;
      const marker = (stemMarkers[name] || []).find(m => m.active);
      const eff = Math.max(0, (marker ? marker.time : 0) + (stemNudge[name] || 0));
      if (eff >= buffer.duration) return;
      const rate = tempoRatio * (stemAutoStretch[name] || 1);
      const shift = keySemitones + (keyLockOn ? -tempoInducedSemitonesFor(name) : 0);
      plans.push({ n, buffer, eff, rate, shift });
      outDur = Math.max(outDur, (buffer.duration - eff) / rate);
    });
    if (!plans.length) return null;

    const sr = audioCtx.sampleRate;
    const build = (ctx, pitch) => {
      const master = ctx.createGain(); master.gain.value = masterVolPct / 100;
      const busComp = ctx.createDynamicsCompressor();
      busComp.threshold.value = -14; busComp.knee.value = 6; busComp.ratio.value = 2;
      busComp.attack.value = 0.03; busComp.release.value = 0.25;
      master.connect(busComp); busComp.connect(ctx.destination);
      plans.forEach(p => {
        const n = p.n;
        const src = ctx.createBufferSource(); src.buffer = p.buffer; src.playbackRate.value = p.rate;
        const trim = ctx.createGain(); trim.gain.value = dbToGain(n.trimDb);
        const eqL = ctx.createBiquadFilter(); eqL.type = 'lowshelf'; eqL.frequency.value = 320; eqL.gain.value = n.eqLowDb;
        const eqM = ctx.createBiquadFilter(); eqM.type = 'peaking'; eqM.frequency.value = 1000; eqM.Q.value = 1; eqM.gain.value = n.eqMidDb;
        const eqH = ctx.createBiquadFilter(); eqH.type = 'highshelf'; eqH.frequency.value = 3200; eqH.gain.value = n.eqHighDb;
        const comp = ctx.createDynamicsCompressor();
        comp.threshold.value = -24; comp.knee.value = 6; comp.ratio.value = 3; comp.attack.value = 0.01; comp.release.value = 0.2;
        const g = ctx.createGain(); g.gain.value = n.volPct / 100;
        src.connect(trim); trim.connect(eqL); eqL.connect(eqM); eqM.connect(eqH);
        if (pitch && Math.abs(p.shift) > 0.25) {
          const ps = new Tone.PitchShift({ pitch: p.shift, windowSize: 0.18 });
          Tone.connect(eqH, ps); Tone.connect(ps, comp);
        } else {
          eqH.connect(comp);
        }
        comp.connect(g); g.connect(master);
        src.start(0, p.eff);
      });
    };

    const needsPitch = plans.some(p => Math.abs(p.shift) > 0.25);
    const seconds = outDur + 0.5;
    if (needsPitch && window.Tone && Tone.Offline) {
      try {
        const tb = await Tone.Offline(() => { build(Tone.getContext().rawContext, true); }, seconds, 2, sr);
        return { buffer: tb.get ? tb.get() : tb, pitchSkipped: false };
      } catch (e) { console.warn('Key-shifted render failed, rendering without key shift', e); }
    }
    const oc = new OfflineAudioContext(2, Math.ceil(seconds * sr), sr);
    build(oc, false);
    return { buffer: await oc.startRendering(), pitchSkipped: needsPitch };
  }

  async function loadLame() {
    if (window.lamejs) return;
    await new Promise((res, rej) => {
      const s = document.createElement('script');
      s.src = 'https://cdnjs.cloudflare.com/ajax/libs/lamejs/1.2.1/lame.min.js';
      s.onload = res; s.onerror = () => rej(new Error('MP3 encoder failed to load'));
      document.head.appendChild(s);
    });
  }

  async function encodeMp3(buf) {
    await loadLame();
    const L = buf.getChannelData(0), R = buf.numberOfChannels > 1 ? buf.getChannelData(1) : L;
    const enc = new lamejs.Mp3Encoder(2, buf.sampleRate, 192);
    const toI16 = (f) => { const o = new Int16Array(f.length); for (let i = 0; i < f.length; i++) { const s = Math.max(-1, Math.min(1, f[i])); o[i] = s < 0 ? s * 32768 : s * 32767; } return o; };
    const parts = [], block = 1152;
    for (let i = 0, k = 0; i < L.length; i += block, k++) {
      const out = enc.encodeBuffer(toI16(L.subarray(i, i + block)), toI16(R.subarray(i, i + block)));
      if (out.length) parts.push(new Uint8Array(out));
      if (k % 200 === 0) await new Promise(r => setTimeout(r, 0));
    }
    const end = enc.flush(); if (end.length) parts.push(new Uint8Array(end));
    return new Blob(parts, { type: 'audio/mpeg' });
  }

  function downloadMix(item) {
    const url = URL.createObjectURL(item.blob);
    const a = document.createElement('a');
    a.href = url; a.download = (item.name.replace(/[\\/:*?"<>|]+/g, '').trim() || 'mix') + '.mp3';
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 4000);
  }

  /* ---------- transport download button: premium-only, mix -> MP3 -> your computer ---------- */
  async function planStatus() {
    const tok = window.getToken && window.getToken();
    if (!tok) return { loggedIn: false, premium: false };
    try {
      const res = await fetch(window.API_BASE + '/api/v1/me?token=' + encodeURIComponent(tok));
      if (!res.ok) return null;
      const d = await res.json();
      return { loggedIn: true, premium: !!d.is_premium };
    } catch (e) { return null; }
  }

  async function downloadMixNow() {
    if (mixBusy) return;
    const btn = document.getElementById('downloadMixBtn');
    if (!audioCtx || !hasRealSong()) { toast('Load a song first'); return; }
    const plan = await planStatus();
    if (!plan) { toast("Couldn't check your plan - try again"); return; }
    if (!plan.premium) {
      toast(plan.loggedIn ? 'Downloading to your computer is a Premium feature' : 'Sign up to unlock downloads');
      const up = document.getElementById('navUpgradeBtn'); if (up) up.click();
      return;
    }
    const name = (window.prompt('Name your download:', 'My Mix') || '').trim();
    if (!name) return;
    mixBusy = true; if (btn) btn.classList.add('active'); renderLibrary(); toast('Rendering your mix...');
    try {
      const r = await renderMixBuffer();
      if (!r) { toast('Nothing audible to save (all channels muted?)'); return; }
      const blob = await encodeMp3(r.buffer);
      downloadMix({ name, blob });
      toast(r.pitchSkipped ? 'Downloaded (key shift not applied)' : 'Downloaded to your computer');
    } catch (e) {
      console.warn('download mix failed', e); toast('Could not download mix');
    } finally { mixBusy = false; if (btn) btn.classList.remove('active'); renderLibrary(); }
  }

  function toggleMixPlay(item) {
    if (mixAudio) { mixAudio.pause(); URL.revokeObjectURL(mixAudio.src); mixAudio = null; }
    if (mixAudioId === item.id) { mixAudioId = null; renderLibrary(); return; }
    if (songPlaying() && typeof pausePreview === 'function') pausePreview(); // don't refuse - just pause the song so the mix can be heard
    mixAudio = new Audio(URL.createObjectURL(item.blob)); mixAudioId = item.id;
    mixAudio.onended = () => { mixAudioId = null; mixAudio = null; renderLibrary(); };
    mixAudio.play().catch(() => {});
    renderLibrary();
  }

  /* ---------- library ---------- */
  function drawWave(canvas, item) {
    const w = canvas.clientWidth || 300, h = canvas.clientHeight || 54;
    canvas.width = w * (devicePixelRatio || 1); canvas.height = h * (devicePixelRatio || 1);
    const c = canvas.getContext('2d'); c.scale(devicePixelRatio || 1, devicePixelRatio || 1);
    c.clearRect(0, 0, w, h);
    const d = item.data[0], n = d.length, col = COLORS[item.stem] || '#fff';
    c.fillStyle = col; c.globalAlpha = 0.85;
    for (let x = 0; x < w; x++) {
      const a = Math.floor(x / w * n), b = Math.max(a + 1, Math.floor((x + 1) / w * n));
      let mx = 0; for (let i = a; i < b; i += Math.max(1, ((b - a) / 8) | 0)) { const v = Math.abs(d[i]); if (v > mx) mx = v; }
      const hh = Math.max(1, mx * h * 0.95); c.fillRect(x, (h - hh) / 2, 1, hh);
    }
    c.globalAlpha = 1;
    const total = n / item.sr, x0 = item.inT / total * w, x1 = item.outT / total * w;
    c.fillStyle = 'rgba(0,0,0,0.62)'; c.fillRect(0, 0, x0, h); c.fillRect(x1, 0, w - x1, h);
    c.fillStyle = col; c.fillRect(x0 - 1, 0, 3, h); c.fillRect(x1 - 1, 0, 3, h);
  }

  function renderLibrary() {
    const root = document.getElementById('sampleLibList'); if (!root) return;
    root.innerHTML = '';
    mixes.slice().sort((x, y) => y.created - x.created).forEach(item => {
      const row = document.createElement('div'); row.className = 'lib-item mix-item';
      row.style.setProperty('--pc', '#3CFDE0');
      const top = document.createElement('div'); top.className = 'lib-top'; top.style.marginBottom = '0';
      const dot = document.createElement('span'); dot.className = 'lib-dot';
      const nm = document.createElement('span'); nm.className = 'lib-name mono'; nm.textContent = item.name; nm.title = 'Click to rename';
      nm.onclick = async () => { const v = (prompt('Rename mix:', item.name) || '').trim(); if (v) { item.name = v; await mixPut(item); renderLibrary(); } };
      const tag = document.createElement('span'); tag.className = 'lib-stem mono';
      const m = Math.floor(item.dur / 60), s = Math.floor(item.dur % 60);
      tag.textContent = 'mix ' + m + ':' + String(s).padStart(2, '0');
      const play = document.createElement('button'); play.type = 'button'; play.textContent = mixAudioId === item.id ? '■' : '▶'; play.title = 'Listen';
      play.onclick = () => toggleMixPlay(item);
      const dl = document.createElement('button'); dl.type = 'button'; dl.textContent = 'DOWNLOAD'; dl.className = 'on'; dl.title = 'Save this mix to your device as an MP3';
      dl.onclick = () => downloadMix(item);
      const del = document.createElement('button'); del.type = 'button'; del.textContent = '✕'; del.title = 'Delete';
      del.onclick = async () => {
        if (!confirm('Delete "' + item.name + '"?')) return;
        if (mixAudioId === item.id && mixAudio) { mixAudio.pause(); mixAudio = null; mixAudioId = null; }
        mixes = mixes.filter(x => x !== item); await mixDel(item.id); renderLibrary();
      };
      top.append(dot, nm, tag, play, dl, del);
      row.appendChild(top); root.appendChild(row);
    });
    if (!lib.length) {
      const e = document.createElement('div'); e.className = 'lib-empty mono';
      e.textContent = 'No samples yet. Cut a region on a waveform, right-click it, Save sample.';
      root.appendChild(e); return;
    }
    const a = getAssign();
    const TYPE_ORDER = ['vocals', 'drums', 'bass', 'guitar', 'other'];
    const sortedLib = lib.slice().sort((x, y) => {
      const ix = TYPE_ORDER.indexOf(x.stem), iy = TYPE_ORDER.indexOf(y.stem);
      return (ix < 0 ? 99 : ix) - (iy < 0 ? 99 : iy);
    });
    let lastType = null;
    sortedLib.forEach(item => {
      if (item.stem !== lastType) {
        lastType = item.stem;
        const gh = document.createElement('div'); gh.className = 'lib-group-head';
        gh.style.setProperty('--pc', COLORS[item.stem] || '#fff');
        gh.textContent = String(item.stem).toUpperCase() + ' SAMPLES';
        root.appendChild(gh);
      }
      const row = document.createElement('div'); row.className = 'lib-item';
      row.style.setProperty('--pc', COLORS[item.stem] || '#fff');
      const top = document.createElement('div'); top.className = 'lib-top';
      const dot = document.createElement('span'); dot.className = 'lib-dot';
      const nm = document.createElement('span'); nm.className = 'lib-name mono'; nm.textContent = item.name; nm.title = 'Click to rename';
      nm.onclick = async () => { const v = (prompt('Rename sample:', item.name) || '').trim(); if (v) { item.name = v; await idbPut(item); renderLibrary(); refreshPads(); } };
      const st = document.createElement('span'); st.className = 'lib-stem mono'; st.textContent = item.stem;
      const play = document.createElement('button'); play.type = 'button'; play.textContent = '▶'; play.title = 'Listen (headphones)';
      play.onclick = async () => {
        // click again while this sample is playing = stop it
        if (libPlaying) {
          const same = libPlaying.item === item;
          try { libPlaying.src.stop(); } catch (e) {}
          libPlaying = null;
          if (same) return;
        }
        const h = await playItem(item, 'main-safe', null, () => { if (libPlaying === h) libPlaying = null; });
        if (h) { h.item = item; libPlaying = h; }
      };
      const hp = document.createElement('button'); hp.type = 'button'; hp.textContent = '🎧'; hp.className = 'lib-hp';
      hp.title = 'Listen in headphones only - the room never hears it (pick CUE OUT first)';
      hp.onclick = async () => {
        if (libPlaying) { try { libPlaying.src.stop(); } catch (e) {} libPlaying = null; }
        const h = await playItem(item, 'cue', null, () => { if (libPlaying === h) libPlaying = null; });
        libPlaying = h;
      };
      // Load this sample onto ANY channel's pad (no waveform on the main board - editing lives on the sampler page)
      const onChans = Object.keys(COLORS).filter(k => a[k] === item.id);
      const nice = (k) => String(k).toUpperCase();
      const asg = document.createElement('select'); asg.className = 'lib-load' + (onChans.length ? ' on' : '');
      asg.title = 'Load this sample onto a channel pad';
      const ph = document.createElement('option'); ph.value = ''; ph.textContent = onChans.length ? ('ON: ' + onChans.map(nice).join(', ')) : 'LOAD TO...';
      asg.appendChild(ph);
      Object.keys(COLORS).forEach(k => { const o = document.createElement('option'); o.value = k; o.textContent = nice(k); asg.appendChild(o); });
      if (onChans.length) { const un = document.createElement('option'); un.value = '__none'; un.textContent = 'UNLOAD'; asg.appendChild(un); }
      asg.onchange = () => {
        const k = asg.value; if (!k) return;
        const x = getAssign();
        // a sample lives on ONE pad: take it off any other pad first
        Object.keys(x).forEach(c => { if (x[c] === item.id) delete x[c]; });
        if (k !== '__none') x[k] = item.id;
        setAssign(x); refreshPads(); renderLibrary();
        toast(k === '__none' ? 'Unloaded from pads' : 'Loaded onto ' + nice(k) + ' pad');
      };
      const dur = document.createElement('span'); dur.className = 'lib-stem mono'; dur.textContent = (item.outT - item.inT).toFixed(1) + 's';
      const dl = document.createElement('button'); dl.type = 'button'; dl.textContent = 'DOWNLOAD'; dl.title = 'Save this sample to your device as an MP3 (Premium)';
      dl.onclick = () => downloadSampleNow(item, dl);
      const del = document.createElement('button'); del.type = 'button'; del.textContent = '✕'; del.title = 'Delete';
      del.onclick = async () => {
        if (!confirm('Delete "' + item.name + '"?')) return;
        lib = lib.filter(x => x !== item); await idbDel(item.id);
        const x = getAssign(); Object.keys(x).forEach(k => { if (x[k] === item.id) delete x[k]; }); setAssign(x);
        refreshPads(); renderLibrary();
      };
      top.append(dot, nm, st, dur, play, hp, asg, dl, del);
      row.append(top); root.appendChild(row);
    });
  }
  window.__renderLibrary = renderLibrary;

  // Spacebar hook: stop anything the library is auditioning (sample, stem
  // preview, saved mix). Returns true if something was playing, so the
  // spacebar handler stops that first instead of also toggling the song.
  window.__stopSamples = function () {
    let any = false;
    Object.keys(playing).forEach(k => {
      try { playing[k].src.stop(); } catch (e) {}
      const p = padEl(k); if (p) p.classList.remove('lit');
      delete playing[k]; any = true;
    });
    if (libPlaying) { try { libPlaying.src.stop(); } catch (e) {} libPlaying = null; any = true; }
    return any;
  };
  window.__stopAuditions = function () {
    let any = false;
    if (window.__stopSamples()) any = true;
    if (libPlaying) { try { libPlaying.src.stop(); } catch (e) {} libPlaying = null; any = true; }
    if (libStemPlaying) { stopLibStem(); any = true; }
    if (mixAudio) {
      try { mixAudio.pause(); URL.revokeObjectURL(mixAudio.src); } catch (e) {}
      mixAudio = null; mixAudioId = null; renderLibrary(); any = true;
    }
    return any;
  };

  /* ---------- library stems: preview + chop to sample ---------- */
  const libStemCache = new Map();
  let libStemPlaying = null; // { h, btn }
  async function fetchLibStemItem(stemId, chan) {
    const key = stemId + ':' + chan;
    if (libStemCache.has(key)) return libStemCache.get(key);
    await ensureEngineReady();
    const url = window.API_BASE + '/api/v1/my-stems/' + encodeURIComponent(stemId) + '/download/' + encodeURIComponent(chan) + '?token=' + encodeURIComponent(getToken());
    const res = await fetch(url);
    if (!res.ok) throw new Error('Server returned ' + res.status);
    const ab = await audioCtx.decodeAudioData(await res.arrayBuffer());
    const data = [];
    for (let c = 0; c < ab.numberOfChannels; c++) data.push(ab.getChannelData(c));
    const item = { stem: chan, sr: ab.sampleRate, data, inT: 0, outT: ab.duration };
    libStemCache.set(key, item);
    return item;
  }
  function stopLibStem() {
    if (!libStemPlaying) return;
    try { libStemPlaying.h.src.stop(); } catch (e) {}
    libStemPlaying.btn.classList.remove('active'); libStemPlaying.btn.innerHTML = '&#9654;';
    libStemPlaying = null;
  }
  window.__libPreviewStem = async function (stemId, chan, btn) {
    if (libStemPlaying && libStemPlaying.btn === btn) { stopLibStem(); return; }
    stopLibStem();
    btn.innerHTML = '...';
    try {
      const item = await fetchLibStemItem(stemId, chan);
      const h = await playItem(item, 'main-safe', null, () => { if (libStemPlaying && libStemPlaying.h === h) { libStemPlaying.btn.classList.remove('active'); libStemPlaying.btn.innerHTML = '&#9654;'; libStemPlaying = null; } });
      if (!h) { btn.innerHTML = '&#9654;'; return; }
      libStemPlaying = { h, btn };
      btn.classList.add('active'); btn.innerHTML = '&#9632;';
    } catch (e) { console.warn('preview failed', e); btn.innerHTML = '&#9654;'; toast('Could not play that stem'); }
  };

  window.__openStemChop = async function (stemId, chan, songName) {
    stopLibStem();
    let full;
    try { full = await fetchLibStemItem(stemId, chan); } catch (e) { toast('Could not load that stem'); return; }
    const item = { stem: chan, sr: full.sr, data: full.data, inT: 0, outT: Math.min(full.outT, 4) };
    const total = full.data[0].length / full.sr;
    const m = document.createElement('div'); m.id = 'stemChopModal';
    const label = chan.toUpperCase();
    m.innerHTML = '<div class="chop-box"><div class="chop-title"></div><canvas></canvas>' +
      '<div class="chop-row"><button type="button" class="prev">&#9654; PREVIEW</button><input type="text" class="nm" maxlength="60"><button type="button" class="primary save">SAVE SAMPLE</button><button type="button" class="close">CLOSE</button></div></div>';
    m.querySelector('.chop-title').textContent = 'CHOP ' + label + ' - ' + songName + ' (drag the edges)';
    const cv = m.querySelector('canvas'), nm = m.querySelector('.nm');
    nm.value = songName + ' ' + label + ' sample';
    document.body.appendChild(m);
    let h = null;
    const redraw = () => drawWave(cv, item);
    redraw();
    const close = () => { if (h) { try { h.src.stop(); } catch (e) {} } m.remove(); };
    m.querySelector('.close').onclick = close;
    m.addEventListener('pointerdown', (e) => { if (e.target === m) close(); });
    m.querySelector('.prev').onclick = async () => {
      if (h) { try { h.src.stop(); } catch (e) {} h = null; }
      h = await playItem(item, 'main-safe', null, () => { h = null; });
    };
    cv.addEventListener('pointerdown', (e) => {
      const r = cv.getBoundingClientRect();
      const x = e.clientX - r.left, x0 = item.inT / total * r.width, x1 = item.outT / total * r.width;
      const which = Math.abs(x - x0) <= Math.abs(x - x1) ? 'in' : 'out';
      cv.setPointerCapture(e.pointerId);
      const move = (ev) => {
        const t = Math.min(total, Math.max(0, (ev.clientX - r.left) / r.width * total));
        if (which === 'in') item.inT = Math.min(t, item.outT - 0.03); else item.outT = Math.max(t, item.inT + 0.03);
        redraw();
      };
      const up = () => { cv.removeEventListener('pointermove', move); cv.removeEventListener('pointerup', up); cv.removeEventListener('pointercancel', up); };
      cv.addEventListener('pointermove', move); cv.addEventListener('pointerup', up); cv.addEventListener('pointercancel', up);
      move(e);
    });
    m.querySelector('.save').onclick = async () => {
      const name = nm.value.trim(); if (!name) return;
      const s0 = Math.max(0, item.inT - PAD_PAD), s1 = Math.min(total, item.outT + PAD_PAD);
      const i0 = Math.floor(s0 * full.sr), i1 = Math.floor(s1 * full.sr);
      const data = full.data.map(ch => ch.slice(i0, i1));
      const saved = { id: 's' + Date.now() + Math.floor(Math.random() * 1000), stem: chan, name, sr: full.sr, data, inT: item.inT - s0, outT: item.outT - s0 };
      lib.push(saved); await idbPut(saved);
      renderLibrary(); refreshPads();
      toast('Saved to ' + label + ' samples');
      close();
    };
  };

  /* ---------- init ---------- */
  document.addEventListener('DOMContentLoaded', init);
  if (document.readyState !== 'loading') init();
  let inited = false;
  async function init() {
    if (inited) return; inited = true;
    wirePads();
    const dlBtn = document.getElementById('downloadMixBtn');
    if (dlBtn) dlBtn.addEventListener('click', downloadMixNow);
    lib = await idbAll();
    // synth channel was removed: move any old synth samples over to Other
    for (const it of lib) { if (it.stem === 'piano') { it.stem = 'other'; idbPut(it); } }
    mixes = await mixAll();
    refreshPads(); renderLibrary();
  }
})();
