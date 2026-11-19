(function () {
  const API_BASE = window.location.origin;  // same server that serves this page
  window.API_BASE = API_BASE;

  const navAccountBtn = document.getElementById('navAccountBtn');
  const navAuthButtons = document.getElementById('navAuthButtons');
  const navAccountGroup = document.getElementById('navAccountGroup');
  const navLoginBtn = document.getElementById('navLoginBtn');
  const navSignupBtn = document.getElementById('navSignupBtn');
  const navMyStemsBtn = document.getElementById('navMyStemsBtn');
  const navUpgradeBtn = document.getElementById('navUpgradeBtn');
  const pricingOverlay = document.getElementById('pricingOverlay');
  const pricingModal = document.getElementById('pricingModal');
  const pricingCloseBtn = document.getElementById('pricingCloseBtn');
  const pricingMonthlyBtn = document.getElementById('pricingMonthlyBtn');
  const pricingAnnualBtn = document.getElementById('pricingAnnualBtn');
  const pricingError = document.getElementById('pricingError');
  const authModal = document.getElementById('authModal');
  const authModalClose = document.getElementById('authModalClose');
  const authModalTitle = document.getElementById('authModalTitle');
  const authForm = document.getElementById('authForm');
  const authEmail = document.getElementById('authEmail');
  const authUsername = document.getElementById('authUsername');
  const authTermsWrap = document.getElementById('authTermsWrap');
  const authPasswordHint = document.getElementById('authPasswordHint');
  const authTermsCheck = document.getElementById('authTermsCheck');
  const authPassword = document.getElementById('authPassword');
  const authPasswordToggle = document.getElementById('authPasswordToggle');
  const authSubmitBtn = document.getElementById('authSubmitBtn');
  const authError = document.getElementById('authError');
  const authToggleText = document.getElementById('authToggleText');
  const authToggleLink = document.getElementById('authToggleLink');

  const dropZone = document.getElementById('dropZone');
  const dropZoneLabel = document.getElementById('dropZoneLabel');
  const fileInput = document.getElementById('fileInput');
  const uploadStatus = document.getElementById('uploadStatus');

  let authMode = 'login';
  let pendingFile = null;

  function getToken() {
    return localStorage.getItem('soundlounge101_token');
  }
  window.getToken = getToken;
  function getEmail() {
    return localStorage.getItem('soundlounge101_email');
  }
  function setSession(token, email) {
    localStorage.setItem('soundlounge101_token', token);
    localStorage.setItem('soundlounge101_email', email);
  }
  function clearSession() {
    localStorage.removeItem('soundlounge101_token');
    localStorage.removeItem('soundlounge101_email');
  }
  function refreshAccountButton() {
    const email = getEmail();
    if (email) {
      navAuthButtons.style.display = 'none';
      navAccountGroup.style.display = 'flex';
      navAccountBtn.textContent = email.split('@')[0] + ' — log out';
    } else {
      navAuthButtons.style.display = 'flex';
      navAccountGroup.style.display = 'none';
    }
    const pricingSec = document.getElementById('pricing');
    if (pricingSec) pricingSec.style.display = email ? 'none' : '';
    refreshAdSlot();
  }
  const adSlot = document.getElementById('adSlot');
  function setAdSlot(show) {
    adSlot.style.display = show ? 'block' : 'none';
    adSlot.style.visibility = show ? 'visible' : 'hidden';
  }
  async function refreshAdSlot() {
    if (!getToken()) {
      setAdSlot(true);
      navUpgradeBtn.style.display = '';
      return;
    }
    try {
      const res = await fetch(API_BASE + '/api/v1/me?token=' + encodeURIComponent(getToken()));
      const data = await res.json();
      setAdSlot(!!data.show_ads);
      navUpgradeBtn.style.display = data.is_premium ? 'none' : '';
    } catch (err) {
      setAdSlot(true);
      navUpgradeBtn.style.display = '';
    }
  }
  refreshAccountButton();
  loadScreenStems();

  navLoginBtn.addEventListener('click', () => openAuthModal('login'));
  navSignupBtn.addEventListener('click', () => openAuthModal('signup'));
  navAccountBtn.addEventListener('click', () => {
    clearSession();
    refreshAccountButton();
  loadScreenStems();
  });

  function openPricingModal() {
    pricingError.style.display = 'none';
    pricingOverlay.style.display = 'block';
    pricingModal.style.display = 'block';
  }
  function closePricingModal() {
    pricingOverlay.style.display = 'none';
    pricingModal.style.display = 'none';
  }
  navUpgradeBtn.addEventListener('click', () => {
    if (!getToken()) { openAuthModal('signup'); return; }
    openPricingModal();
  });
  pricingCloseBtn.addEventListener('click', closePricingModal);
  pricingOverlay.addEventListener('click', closePricingModal);

  async function startCheckout(plan) {
    pricingError.style.display = 'none';
    try {
      const res = await fetch(API_BASE + '/api/v1/payments/create-checkout?token=' + encodeURIComponent(getToken()), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ plan })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Checkout failed.');
      window.location.href = data.checkout_url;
    } catch (err) {
      pricingError.textContent = err.message || 'Something went wrong.';
      pricingError.style.display = 'block';
    }
  }
  pricingMonthlyBtn.addEventListener('click', () => startCheckout('monthly'));
  pricingAnnualBtn.addEventListener('click', () => startCheckout('annual'));

  // Pricing section buttons: logged in -> straight to card payment; logged out -> signup
  function sectionCheckout(plan) {
    if (!getToken()) { openAuthModal('signup'); return; }
    startCheckout(plan);
  }
  document.getElementById('sectionMonthlyBtn').addEventListener('click', () => sectionCheckout('monthly'));
  document.getElementById('sectionAnnualBtn').addEventListener('click', () => sectionCheckout('annual'));

  (function handleSubscribedRedirect() {
    const params = new URLSearchParams(window.location.search);
    const sub = params.get('subscribed');
    if (sub === 'success') {
      alert('You\'re premium now — unlimited splits unlocked.');
      refreshAdSlot();
    } else if (sub === 'cancelled') {
      alert('Checkout cancelled — no charge made.');
    }
    if (sub) {
      params.delete('subscribed');
      const newUrl = window.location.pathname + (params.toString() ? '?' + params.toString() : '');
      window.history.replaceState({}, '', newUrl);
    }
  })();

  function openAuthModal(mode) {
    authMode = mode;
    authError.style.display = 'none';
    authForm.reset();
    authForm.style.display = 'block';
    authForgotWrap.style.display = 'block';
    forgotPasswordForm.style.display = 'none';
    resetPasswordForm.style.display = 'none';
    if (mode === 'signup') {
      authModalTitle.textContent = 'Create your account';
      authSubmitBtn.textContent = 'Sign up';
      authToggleText.textContent = 'Already have an account?';
      authToggleLink.textContent = 'Log in';
      authUsername.style.display = 'block';
      authUsername.required = true;
      authTermsWrap.style.display = 'flex';
      authTermsCheck.required = true;
      authPasswordHint.style.display = 'block';
    } else {
      authModalTitle.textContent = 'Log in';
      authSubmitBtn.textContent = 'Log in';
      authToggleText.textContent = "Don't have an account?";
      authToggleLink.textContent = 'Sign up';
      authUsername.style.display = 'none';
      authUsername.required = false;
      authTermsWrap.style.display = 'none';
      authTermsCheck.required = false;
      authPasswordHint.style.display = 'none';
    }
    authModal.style.display = 'flex';
  }
  function closeAuthModal() {
    authModal.style.display = 'none';
    pendingFile = null;
  }
  authModalClose.addEventListener('click', closeAuthModal);
  authModal.addEventListener('click', (e) => { if (e.target === authModal) closeAuthModal(); });
  authToggleLink.addEventListener('click', (e) => {
    e.preventDefault();
    openAuthModal(authMode === 'login' ? 'signup' : 'login');
  });

  authPasswordToggle.addEventListener('click', () => {
    const showing = authPassword.type === 'text';
    authPassword.type = showing ? 'password' : 'text';
    authPasswordToggle.textContent = showing ? 'SHOW' : 'HIDE';
  });
  (function () {
    const rt = document.getElementById('resetPasswordToggle'), rp = document.getElementById('resetNewPassword');
    if (!rt || !rp) return;
    rt.addEventListener('click', () => {
      const showing = rp.type === 'text';
      rp.type = showing ? 'password' : 'text';
      rt.textContent = showing ? 'SHOW' : 'HIDE';
      rt.setAttribute('aria-label', showing ? 'Show password' : 'Hide password');
    });
  })();

  const authForgotWrap = document.getElementById('authForgotWrap');
  const authForgotLink = document.getElementById('authForgotLink');
  const forgotPasswordForm = document.getElementById('forgotPasswordForm');
  const forgotEmail = document.getElementById('forgotEmail');
  const forgotSubmitBtn = document.getElementById('forgotSubmitBtn');
  const forgotBackLink = document.getElementById('forgotBackLink');
  const resetPasswordForm = document.getElementById('resetPasswordForm');
  const resetNewPassword = document.getElementById('resetNewPassword');
  const resetSubmitBtn = document.getElementById('resetSubmitBtn');

  function showLoginView() {
    authModalTitle.textContent = authMode === 'signup' ? 'Create your account' : 'Log in';
    authForm.style.display = 'block';
    authForgotWrap.style.display = 'block';
    forgotPasswordForm.style.display = 'none';
    resetPasswordForm.style.display = 'none';
    authError.style.display = 'none';
  }

  authForgotLink.addEventListener('click', (e) => {
    e.preventDefault();
    authModalTitle.textContent = 'Reset your password';
    authForm.style.display = 'none';
    authForgotWrap.style.display = 'none';
    forgotPasswordForm.style.display = 'block';
    authError.style.display = 'none';
  });

  forgotBackLink.addEventListener('click', (e) => {
    e.preventDefault();
    showLoginView();
  });

  forgotSubmitBtn.addEventListener('click', async () => {
    const email = forgotEmail.value.trim();
    if (!email) { return; }
    forgotSubmitBtn.disabled = true;
    forgotSubmitBtn.textContent = 'Sending\u2026';
    try {
      const res = await fetch(API_BASE + '/api/v1/forgot-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email })
      });
      await res.json();
      authError.style.display = 'block';
      authError.style.color = 'var(--chrome-dim)';
      authError.textContent = 'If that email is registered, a reset link has been sent to it.';
    } catch (err) {
      authError.style.display = 'block';
      authError.style.color = 'var(--clip-red)';
      authError.textContent = 'Something went wrong. Try again.';
    } finally {
      forgotSubmitBtn.disabled = false;
      forgotSubmitBtn.textContent = 'Send reset link';
    }
  });

  resetSubmitBtn.addEventListener('click', async () => {
    const params = new URLSearchParams(window.location.search);
    const token = params.get('token');
    const newPassword = resetNewPassword.value;
    const pwOk = newPassword.length >= 8 && /[A-Z]/.test(newPassword) && /[0-9]/.test(newPassword) && /[^A-Za-z0-9]/.test(newPassword);
    if (!pwOk) {
      authError.style.display = 'block';
      authError.style.color = 'var(--clip-red)';
      authError.textContent = 'Password must be at least 8 characters, with 1 capital letter, 1 number, and 1 symbol.';
      return;
    }
    resetSubmitBtn.disabled = true;
    resetSubmitBtn.textContent = 'Updating\u2026';
    try {
      const res = await fetch(API_BASE + '/api/v1/reset-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token, new_password: newPassword })
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(typeof data.detail === 'string' ? data.detail : 'Invalid or expired reset link.');
      }
      authMode = 'login';
      resetPasswordForm.style.display = 'none';
      showLoginView();
      authError.style.display = 'block';
      authError.style.color = 'var(--chrome-dim)';
      authError.textContent = 'Password updated. You can now log in.';
    } catch (err) {
      authError.style.display = 'block';
      authError.style.color = 'var(--clip-red)';
      authError.textContent = err.message;
    } finally {
      resetSubmitBtn.disabled = false;
      resetSubmitBtn.textContent = 'Set new password';
    }
  });

  (function checkForResetToken() {
    const params = new URLSearchParams(window.location.search);
    const token = params.get('token');
    if (window.location.pathname === '/reset-password' && token) {
      authMode = 'login';
      authModal.style.display = 'flex';
      authModalTitle.textContent = 'Set a new password';
      authForm.style.display = 'none';
      authForgotWrap.style.display = 'none';
      forgotPasswordForm.style.display = 'none';
      resetPasswordForm.style.display = 'block';
    }
  })();

  authForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    authError.style.display = 'none';
    if (authMode === 'signup') {
      const pw = authPassword.value;
      const pwOk = pw.length >= 8 && /[A-Z]/.test(pw) && /[0-9]/.test(pw) && /[^A-Za-z0-9]/.test(pw);
      if (!pwOk) {
        authError.textContent = 'Password must be at least 8 characters, with 1 capital letter, 1 number, and 1 symbol.';
        authError.style.display = 'block';
        return;
      }
    }
    if (authMode === 'signup' && !authTermsCheck.checked) {
      authError.textContent = 'Please agree to the Terms of Service to continue.';
      authError.style.display = 'block';
      return;
    }
    authSubmitBtn.disabled = true;
    authSubmitBtn.textContent = authMode === 'signup' ? 'Signing up…' : 'Logging in…';
    try {
      const endpoint = authMode === 'signup' ? '/api/v1/signup' : '/api/v1/login';
      const payload = authMode === 'signup'
        ? { email: authEmail.value, username: authUsername.value, password: authPassword.value }
        : { email: authEmail.value, password: authPassword.value };
      const res = await fetch(API_BASE + endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (!res.ok) {
        let message = 'Something went wrong. Try again.';
        if (Array.isArray(data.detail)) {
          message = data.detail.map(e => e.msg || JSON.stringify(e)).join(', ');
        } else if (typeof data.detail === 'string') {
          message = data.detail;
        }
        throw new Error(message);
      }
      setSession(data.token, data.email);
      refreshAccountButton();
  loadScreenStems();
      closeAuthModal();
      if (pendingFile) {
        const fileToUpload = pendingFile;
        pendingFile = null;
        startUpload(fileToUpload);
      }
    } catch (err) {
      authError.textContent = err.message;
      authError.style.display = 'block';
    } finally {
      authSubmitBtn.disabled = false;
      authSubmitBtn.textContent = authMode === 'signup' ? 'Sign up' : 'Log in';
    }
  });

  dropZone.addEventListener('click', () => fileInput.click());
  dropZone.addEventListener('dragover', (e) => { e.preventDefault(); dropZone.style.borderColor = 'var(--vu-amber)'; });
  dropZone.addEventListener('dragleave', () => { dropZone.style.borderColor = ''; });
  dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.style.borderColor = '';
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileChosen(e.dataTransfer.files[0]);
    }
  });
  fileInput.addEventListener('change', () => {
    if (fileInput.files && fileInput.files[0]) {
      handleFileChosen(fileInput.files[0]);
    }
  });

  function handleFileChosen(file) {
    const allowed = ['.mp3', '.wav', '.m4a', '.flac'];
    const ext = '.' + file.name.split('.').pop().toLowerCase();
    if (!allowed.includes(ext)) {
      showStatus('Unsupported file type. Use MP3, WAV, M4A, or FLAC.', true);
      return;
    }
    if (!getToken()) {
      pendingFile = file;
      openAuthModal('signup');
      return;
    }
    startUpload(file);
  }

  function showStatus(text, isError) {
    uploadStatus.style.display = 'block';
    uploadStatus.innerHTML = text;
    uploadStatus.style.color = isError ? 'var(--clip-red)' : 'rgba(237,227,206,0.55)';
  }

  let splitTimerId = null;
  function startSplitLoader() {
    const startedAt = Date.now();
    uploadStatus.style.display = 'block';
    uploadStatus.style.color = 'rgba(237,227,206,0.55)';
    const render = () => {
      const secs = Math.floor((Date.now() - startedAt) / 1000);
      uploadStatus.innerHTML =
        '<div class="split-loader"><div class="ring"></div><div class="split-text">' +
        'Splitting your track — this can take a few minutes… <span class="elapsed">' + secs + 's</span>' +
        '</div></div>' +
        '<div class="split-segs">' + '<div class="seg"></div>'.repeat(6) + '</div>';
    };
    render();
    splitTimerId = setInterval(render, 1000);
  }
  function stopSplitLoader() {
    if (splitTimerId) { clearInterval(splitTimerId); splitTimerId = null; }
  }

  async function pollSplitStatus(stemId) {
    const token = encodeURIComponent(getToken());
    while (true) {
      await new Promise(r => setTimeout(r, 4000));
      const res = await fetch(API_BASE + '/api/v1/split/status/' + stemId + '?token=' + token);
      if (!res.ok) {
        if (res.status === 401) throw new Error('Your session expired. Please log in again.');
        continue;
      }
      const data = await res.json();
      if (data.status === 'done') return data;
      if (data.status === 'error') throw new Error(data.error || 'Split failed.');
    }
  }

  function probeDuration(file) {
    return new Promise(resolve => {
      let done = false;
      const finish = (v) => { if (!done) { done = true; resolve(v); } };
      try {
        const a = new Audio();
        const url = URL.createObjectURL(file);
        a.preload = 'metadata';
        a.onloadedmetadata = () => { URL.revokeObjectURL(url); finish(isFinite(a.duration) ? a.duration : null); };
        a.onerror = () => { URL.revokeObjectURL(url); finish(null); };
        a.src = url;
        setTimeout(() => finish(null), 4000);
      } catch (e) { finish(null); }
    });
  }

  function fmtDuration(sec) {
    const s = Math.round(sec);
    return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0');
  }

  async function startUpload(file) {
    const clientDur = await probeDuration(file);
    const fileInfo = file.name + ' — ' + (file.size / 1048576).toFixed(1) + ' MB' + (clientDur ? ' — ' + fmtDuration(clientDur) : '');
    dropZoneLabel.textContent = 'Uploading ' + file.name + '…';
    showStatus('Uploading ' + fileInfo + '…', false);
    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('client_size', String(file.size));
      if (clientDur) formData.append('client_duration', String(clientDur));
      formData.append('stems', '6');
      setTimeout(() => {
        dropZoneLabel.textContent = 'Splitting ' + file.name + '…';
        startSplitLoader();
      }, 600);
      const res = await fetch(API_BASE + '/api/v1/split?token=' + encodeURIComponent(getToken()), {
        method: 'POST',
        body: formData
      });
      const kickoff = await res.json();
      if (!res.ok) {
        stopSplitLoader();
        if (res.status === 401) {
          clearSession();
          refreshAccountButton();
  loadScreenStems();
          throw new Error('Your session expired. Please log in again.');
        }
        throw new Error(kickoff.detail || 'Upload failed.');
      }

      const data = await pollSplitStatus(kickoff.stem_id);
      stopSplitLoader();
      dropZoneLabel.innerHTML = 'Drop an MP3 or WAV here, or <strong>click to browse</strong>';
      const dlUrl = API_BASE + '/api/v1/my-stems/' + data.stem_id + '/download?token=' + encodeURIComponent(getToken());
      uploadStatus.innerHTML = 'Loading stems into the mixer…';
      if (typeof window.__reloadLibraries === 'function') window.__reloadLibraries();
      if (typeof loadScreenStems === 'function') loadScreenStems();

      if (typeof window.__loadBackendStemToChannel === 'function') {
        const trackLabel = data.track_name || file.name;
        const channelsToLoad = CHANNEL_LIST;
        const results = await Promise.all(
          channelsToLoad.map(chan => window.__loadBackendStemToChannel(chan, data.stem_id, trackLabel))
        );
        const loadedCount = results.filter(Boolean).length;
        const previewLabelEl = document.getElementById('previewLabel');
        if (previewLabelEl && loadedCount > 0) previewLabelEl.textContent = trackLabel;
        uploadStatus.innerHTML = loadedCount === channelsToLoad.length
          ? 'Done! ' + fileInfo + ' — stems loaded into the mixer. <a href="' + dlUrl + '" style="color:var(--vu-amber);">Download</a>'
          : 'Done, but only ' + loadedCount + '/' + channelsToLoad.length + ' stems loaded. <a href="' + dlUrl + '" style="color:var(--vu-amber);">Download</a>';
      } else {
        uploadStatus.innerHTML = 'Done! <a href="' + dlUrl + '" style="color:var(--vu-amber);">Download your stems</a>';
      }
    } catch (err) {
      stopSplitLoader();
      dropZoneLabel.innerHTML = 'Drop an MP3 or WAV here, or <strong>click to browse</strong>';
      showStatus(err.message, true);
    }
  }

  const myStemsOverlay = document.getElementById('myStemsOverlay');
  const myStemsPanel = document.getElementById('myStemsPanel');
  const myStemsClose = document.getElementById('myStemsClose');
  const myStemsList = document.getElementById('myStemsList');

  function closeMyStems() {
    myStemsOverlay.style.display = 'none';
    myStemsPanel.style.display = 'none';
  }
  myStemsOverlay.addEventListener('click', closeMyStems);
  myStemsClose.addEventListener('click', closeMyStems);

  function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  const CHANNEL_LIST = ['vocals', 'drums', 'bass', 'guitar', 'other'];
  const channelAssignments = {};
  const STEM_ROW_META = {
    vocals: { label: 'VOCALS', accent: '#ff5540' },
    drums:  { label: 'DRUMS',  accent: '#ffa022' },
    bass:   { label: 'BASS',   accent: '#2fe08a' },
    guitar: { label: 'GUITAR', accent: '#9b6dff' },
    other:  { label: 'OTHER',  accent: '#3ab6ff' }
  };

  window.__refreshMyStems = () => loadScreenStems();

  async function loadScreenStems() {
    const listEl = document.getElementById('screenStemList');
    const countEl = document.getElementById('screenCount');
    if (!listEl) return;

    if (!getToken()) {
      listEl.innerHTML = '<div class="screen-empty">Log in to browse your saved stems here.</div>';
      if (countEl) countEl.textContent = '(0)';
      return;
    }

    try {
      const res = await fetch(API_BASE + '/api/v1/my-stems?token=' + encodeURIComponent(getToken()));
      const data = await res.json();
      if (res.status === 401) {
        clearSession();
        refreshAccountButton();
        listEl.innerHTML = '<div class="screen-empty">Your session expired. Log in again to see your stems.</div>';
        if (countEl) countEl.textContent = '(0)';
        return;
      }
      if (!res.ok) throw new Error(data.detail || 'Could not load stems.');

      const groups = new Map();
      CHANNEL_LIST.forEach(c => groups.set(c, { songName: (STEM_ROW_META[c] || { label: c.toUpperCase() }).label, accent: (STEM_ROW_META[c] || {}).accent, rows: [] }));
      data.forEach(stem => {
        const k = CHANNEL_LIST.includes(stem.instrument) ? stem.instrument : 'other';
        groups.get(k).rows.push(stem);
      });
      Array.from(groups.keys()).forEach(k => { if (!groups.get(k).rows.length) groups.delete(k); });

      if (countEl) countEl.textContent = '(' + data.length + ')';

      if (!data.length) {
        listEl.innerHTML = '<div class="screen-empty">No saved stems yet — hit SAVE on a mixer channel to keep one here.</div>';
        return;
      }

      listEl.innerHTML = Array.from(groups.entries()).map(([groupKey, group]) => {
        const safeSong = escapeHtml(group.songName);
        const rowsHtml = group.rows.map(stem => {
          const chan = stem.instrument;
          const meta = STEM_ROW_META[chan] || { label: chan.toUpperCase(), accent: '#3CFDE0' };
          const safeName = escapeHtml(stem.track_name);
          return '<div class="screen-row" data-stem-id="' + stem.id + '" data-track-name="' + safeName + '" data-stem-type="' + chan + '" data-chan="' + chan + '">' +
            '<span class="stem-chan-tag" style="color:' + meta.accent + ';border-color:' + meta.accent + ';">' + meta.label + '</span>' +
            '<div class="name-wrap">' +
              '<span class="track-name" title="' + safeName + '">' + safeName + '</span>' +
              '<button type="button" class="name-delete" title="Delete this saved stem">' +
                '<svg viewBox="0 0 24 24" width="9" height="9" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2"/><path d="M19 6l-1 14a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1L5 6"/></svg>' +
              '</button>' +
            '</div>' +
            '<button type="button" class="rename-btn" title="Rename">' +
              '<svg viewBox="0 0 24 24" width="9" height="9" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>' +
            '</button>' +
            '<button type="button" class="cue-jack" title="Cue preview (headphone)">' +
              '<svg viewBox="0 0 24 24" width="9" height="9" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M4 14v-2a8 8 0 0 1 16 0v2"/><rect x="2.5" y="13" width="4" height="7" rx="1.5"/><rect x="17.5" y="13" width="4" height="7" rx="1.5"/></svg>' +
            '</button>' +
            '<button type="button" class="play-btn" title="Play this stem">&#9654;</button>' +
            '<button type="button" class="chop-btn" title="Chop a sample from this stem">&#9986;</button>' +
            '<button type="button" class="assign-btn">LOAD</button>' +
          '</div>';
        }).join('');
        return '<div class="song-folder" data-group-key="' + groupKey + '">' +
          '<div class="song-folder-head">' +
            '<button type="button" class="folder-toggle" aria-expanded="true">&#9660;</button>' +
            '<span class="folder-name type-name" style="color:' + (group.accent || '#3CFDE0') + ';" title="' + safeSong + '">' + safeSong + '</span>' +
            '<span class="folder-count">' + group.rows.length + '</span>' +
          '</div>' +
          '<div class="song-folder-body">' + rowsHtml + '</div>' +
        '</div>';
      }).join('');

      listEl.querySelectorAll('.song-folder-head').forEach(head => {
        head.addEventListener('click', () => {
          const btn = head.querySelector('.folder-toggle');
          const folder = head.closest('.song-folder');
          const body = folder.querySelector('.song-folder-body');
          const open = btn.getAttribute('aria-expanded') === 'true';
          btn.setAttribute('aria-expanded', open ? 'false' : 'true');
          btn.innerHTML = open ? '&#9658;' : '&#9660;';
          body.style.display = open ? 'none' : '';
        });
      });

      listEl.querySelectorAll('.screen-row').forEach(row => {
        const stemId = row.dataset.stemId;
        const chan = row.dataset.chan;
        let trackName = row.dataset.trackName;
        const assignBtn = row.querySelector('.assign-btn');
        const cueJack = row.querySelector('.cue-jack');
        const renameBtn = row.querySelector('.rename-btn');
        const nameDeleteBtn = row.querySelector('.name-delete');
        const nameSpan = row.querySelector('.track-name');

        if (channelAssignments[chan] === stemId) {
          assignBtn.textContent = 'LOADED';
          assignBtn.classList.add('assigned');
        }

        nameDeleteBtn.addEventListener('click', async (e) => {
          e.stopPropagation();
          if (!confirm('Delete "' + trackName + '"? This can\'t be undone.')) return;
          const allRows = listEl.querySelectorAll('.screen-row[data-stem-id="' + stemId + '"]');
          allRows.forEach(r => { r.querySelector('.name-delete').disabled = true; });
          try {
            const res = await fetch(API_BASE + '/api/v1/my-stems/' + stemId + '?token=' + encodeURIComponent(getToken()), {
              method: 'DELETE'
            });
            const resData = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(resData.detail || 'Could not delete.');
            Object.keys(channelAssignments).forEach(ch => {
              if (channelAssignments[ch] === stemId) {
                clearChannelBadge(ch);
                if (window.__restoreOriginalStem) window.__restoreOriginalStem(ch);
                delete channelAssignments[ch];
              }
            });
            allRows.forEach(r => {
              const folder = r.closest('.song-folder');
              r.remove();
              if (folder && !folder.querySelector('.screen-row')) folder.remove();
            });
            if (!listEl.querySelector('.screen-row')) {
              listEl.innerHTML = '<div class="screen-empty">No saved stems yet — hit SAVE on a mixer channel to keep one here.</div>';
            }
            if (countEl) {
              countEl.textContent = '(' + listEl.querySelectorAll('.screen-row').length + ')';
            }
            updateLcdLoaded();
          } catch (err) {
            allRows.forEach(r => { r.querySelector('.name-delete').disabled = false; });
            alert(err.message || 'Could not delete.');
          }
        });

        renameBtn.addEventListener('click', () => {
          if (row.querySelector('.rename-input')) return;
          const input = document.createElement('input');
          input.type = 'text';
          input.className = 'rename-input mono';
          input.value = trackName;
          input.style.cssText = 'flex:1;min-width:0;background:#1A1E23;color:rgba(216,220,226,0.9);border:1px solid var(--ember);border-radius:2px;font-family:inherit;font-size:0.66rem;padding:0.15rem 0.3rem;';
          nameSpan.replaceWith(input);
          input.focus();
          input.select();

          const save = async () => {
            const newName = input.value.trim();
            if (!newName || newName === trackName) {
              input.replaceWith(nameSpan);
              return;
            }
            input.disabled = true;
            try {
              const res = await fetch(API_BASE + '/api/v1/my-stems/' + stemId + '?token=' + encodeURIComponent(getToken()), {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ track_name: newName })
              });
              const resData = await res.json();
              if (!res.ok) throw new Error(resData.detail || 'Could not rename.');
              trackName = resData.track_name;
              listEl.querySelectorAll('.screen-row[data-stem-id="' + stemId + '"]').forEach(r => {
                r.dataset.trackName = trackName;
                const ns = r.querySelector('.track-name');
                ns.textContent = trackName;
                ns.title = trackName;
              });
              Object.keys(channelAssignments).forEach(ch => {
                if (channelAssignments[ch] === stemId) setChannelBadge(ch, trackName);
              });
            } catch (err) {
              nameSpan.textContent = trackName;
            } finally {
              input.replaceWith(nameSpan);
            }
          };

          input.addEventListener('blur', save);
          input.addEventListener('keydown', e => {
            if (e.key === 'Enter') input.blur();
            if (e.key === 'Escape') { input.value = trackName; input.blur(); }
          });
        });

        assignBtn.addEventListener('click', async (e) => {
          e.stopPropagation();
          if (assignBtn.disabled) return;

          if (channelAssignments[chan] === stemId) {
            delete channelAssignments[chan];
            clearChannelBadge(chan);
            if (window.__restoreOriginalStem) window.__restoreOriginalStem(chan);
            assignBtn.textContent = 'LOAD';
            assignBtn.classList.remove('assigned');
            updateLcdLoaded();
            return;
          }

          const prevStemId = channelAssignments[chan];
          if (prevStemId && prevStemId !== stemId) {
            const prevBtn = listEl.querySelector('.screen-row[data-chan="' + chan + '"][data-stem-id="' + prevStemId + '"] .assign-btn');
            if (prevBtn) { prevBtn.textContent = 'LOAD'; prevBtn.classList.remove('assigned'); }
          }

          assignBtn.disabled = true;
          assignBtn.textContent = 'LOADING…';
          const ok = window.__loadBackendStemToChannel
            ? await window.__loadBackendStemToChannel(chan, stemId, trackName)
            : false;
          assignBtn.disabled = false;
          if (ok) {
            channelAssignments[chan] = stemId;
            assignBtn.textContent = 'LOADED';
            assignBtn.classList.add('assigned');
          } else {
            assignBtn.textContent = 'LOAD';
          }
          updateLcdLoaded();
        });

        const playBtn = row.querySelector('.play-btn');
        const chopBtn = row.querySelector('.chop-btn');
        playBtn.addEventListener('click', async (e) => {
          e.stopPropagation();
          if (window.__libPreviewStem) await window.__libPreviewStem(stemId, chan, playBtn);
        });
        chopBtn.addEventListener('click', (e) => {
          e.stopPropagation();
          window.location.href = '/sampler';
        });

        cueJack.addEventListener('click', () => {
          const wasActive = cueJack.classList.contains('active');
          listEl.querySelectorAll('.cue-jack.active').forEach(j => j.classList.remove('active'));
          if (!wasActive) cueJack.classList.add('active');
        });

        row.addEventListener('click', e => {
          if (e.target.closest('button') || e.target.closest('input')) return;
          listEl.querySelectorAll('.screen-row.selected').forEach(r => r.classList.remove('selected'));
          row.classList.add('selected');
          if (window.__updateBrowseReadout) window.__updateBrowseReadout();
        });
      });

      if (window.__applyBrowseFilter) window.__applyBrowseFilter();
      else if (window.__updateBrowseReadout) window.__updateBrowseReadout();
    } catch (err) {
      listEl.innerHTML = '<div class="screen-empty" style="color:var(--clip-red);">' + escapeHtml(err.message) + '</div>';
    }
  }

  function updateLcdLoaded() {
    const el = document.getElementById('lcdLoaded');
    if (el) el.textContent = Object.keys(channelAssignments).length;
    const status = document.getElementById('lcdStatus');
    if (status) {
      const n = Object.keys(channelAssignments).length;
      status.textContent = n ? 'LOADED' : 'READY';
    }
  }

  window.__clearChannelAssignment = function (channelKey) {
    const changed = channelAssignments[channelKey] !== undefined;
    if (changed) delete channelAssignments[channelKey];
    document.querySelectorAll('.screen-row[data-chan="' + channelKey + '"] .assign-btn.assigned').forEach(btn => {
      btn.textContent = 'LOAD';
      btn.classList.remove('assigned');
    });
    if (changed) updateLcdLoaded();
    return changed;
  };

  function setChannelBadge(channelKey, trackName) {
    const channel = document.querySelector('.channel[data-stem="' + channelKey + '"]');
    if (!channel) return;
    const badge = channel.querySelector('.assigned-badge');
    if (badge) {
      badge.textContent = trackName;
      badge.classList.add('show');
    }
  }

  function clearChannelBadge(channelKey) {
    const channel = document.querySelector('.channel[data-stem="' + channelKey + '"]');
    if (!channel) return;
    const badge = channel.querySelector('.assigned-badge');
    if (badge) {
      badge.textContent = '';
      badge.classList.remove('show');
    }
  }

  navMyStemsBtn.addEventListener('click', async () => {
    myStemsOverlay.style.display = 'block';
    myStemsPanel.style.display = 'block';
    myStemsList.innerHTML = '<div style="color:var(--chrome-dim);font-size:0.8rem;">Loading…</div>';
    try {
      const res = await fetch(API_BASE + '/api/v1/my-stems?include_unsaved=true&token=' + encodeURIComponent(getToken()));
      const data = await res.json();
      if (res.status === 401) {
        clearSession();
        refreshAccountButton();
        myStemsList.innerHTML = '<div style="color:var(--chrome-dim);font-size:0.8rem;">Your session expired. Please log in again.</div>';
        return;
      }
      if (!res.ok) throw new Error(data.detail || 'Could not load your stems.');
      if (!data.length) {
        myStemsList.innerHTML = '<div style="color:var(--chrome-dim);font-size:0.8rem;">No splits yet — drop a song above to get started.</div>';
        return;
      }
      myStemsList.innerHTML = data.map(stem => {
        const date = new Date(stem.created_at).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
        const dlUrl = API_BASE + '/api/v1/my-stems/' + stem.id + '/download?token=' + encodeURIComponent(getToken());
        const origUrl = API_BASE + '/api/v1/my-stems/' + stem.id + '/download-original?token=' + encodeURIComponent(getToken());
        const isSingle = !!stem.instrument;
        const loadLabel = isSingle ? ('Load ' + stem.instrument) : 'Load into mixer';
        const stemsPanel = isSingle ? '' :
          '<div class="stems-drop-panel" style="display:none;margin-top:0.7rem;padding-top:0.7rem;border-top:1px solid var(--concrete-line);">' +
            '<div style="display:flex;flex-wrap:wrap;gap:0.6rem;margin-bottom:0.6rem;">' +
            CHANNEL_LIST.map(inst =>
              '<label style="display:flex;align-items:center;gap:0.3rem;font-size:0.72rem;color:var(--chrome-dim);cursor:pointer;">' +
              '<input type="checkbox" class="stem-pick-cb" value="' + inst + '"> ' + inst +
              '</label>'
            ).join('') +
            '</div>' +
            '<button type="button" class="save-selected-stems-btn" style="background:none;color:var(--ember);border:1px solid var(--ember);border-radius:2px;font-family:inherit;font-size:0.72rem;font-weight:600;padding:0.3rem 0.6rem;cursor:pointer;">Save Selected</button>' +
          '</div>';
        return '<div class="my-stems-row" data-stem-id="' + stem.id + '" data-track-name="' + escapeHtml(stem.track_name) + '" data-instrument="' + escapeHtml(stem.instrument || '') + '" style="border:1px solid var(--concrete-line);padding:0.9rem;margin-bottom:0.7rem;">' +
          '<div class="' + (isSingle ? '' : 'track-name-toggle') + '" style="color:var(--chrome);font-size:0.85rem;margin-bottom:0.3rem;word-break:break-word;' + (isSingle ? '' : 'cursor:pointer;') + '">' + escapeHtml(stem.track_name) + (isSingle ? '' : ' <span class="stems-drop-caret" style="color:var(--chrome-dim);font-size:0.7rem;">▾</span>') + '</div>' +
          '<div style="color:var(--chrome-dim);font-size:0.68rem;margin-bottom:0.7rem;">' + date + '</div>' +
          '<div style="display:flex;gap:0.9rem;align-items:center;">' +
          (isSingle ? ('<canvas class="preview-wave-canvas" title="Hover to preview" data-preview-url="' + dlUrl + '" width="90" height="32" style="background:var(--asphalt,#111);border:1px solid var(--concrete-line);border-radius:2px;cursor:pointer;flex-shrink:0;"></canvas>') : '') +
          '<button type="button" class="load-all-mixer-btn" style="background:var(--ember);color:#1A1005;border:none;border-radius:2px;font-family:inherit;font-size:0.72rem;font-weight:600;padding:0.35rem 0.7rem;cursor:pointer;">' + loadLabel + '</button>' +
          (!isSingle && stem.has_original ? ('<a href="' + origUrl + '" style="color:var(--chrome);font-size:0.75rem;text-decoration:none;border-bottom:1px solid var(--chrome);">Download song</a>') : '') +
          '<a href="' + dlUrl + '" style="color:var(--ember);font-size:0.75rem;text-decoration:none;border-bottom:1px solid var(--ember);">Download ' + (isSingle ? '(.wav)' : 'stems (.zip)') + '</a>' +
          '<button type="button" class="delete-stem-btn" title="Delete this stem" style="margin-left:auto;background:none;color:var(--clip-red);border:1px solid var(--clip-red);border-radius:2px;font-family:inherit;font-size:0.7rem;padding:0.3rem 0.55rem;cursor:pointer;">Delete</button>' +
          '</div>' +
          stemsPanel +
          '</div>';
      }).join('');

      myStemsList.querySelectorAll('.my-stems-row').forEach(row => {
        const panel = row.querySelector('.stems-drop-panel');
        const toggle = row.querySelector('.track-name-toggle');
        if (!panel || !toggle) return;
        toggle.addEventListener('click', () => {
          const isOpen = panel.style.display === 'block';
          panel.style.display = isOpen ? 'none' : 'block';
          const caret = toggle.querySelector('.stems-drop-caret');
          if (caret) caret.textContent = isOpen ? '▾' : '▴';
        });
      });

      myStemsList.querySelectorAll('.save-selected-stems-btn').forEach(btn => {
        btn.addEventListener('click', async () => {
          const row = btn.closest('.my-stems-row');
          const stemId = row.dataset.stemId;
          const checked = Array.from(row.querySelectorAll('.stem-pick-cb:checked')).map(cb => cb.value);
          if (!checked.length) return;
          btn.disabled = true;
          const prevText = btn.textContent;
          btn.textContent = 'Saving…';
          try {
            for (const inst of checked) {
              const res = await fetch(API_BASE + '/api/v1/my-stems/' + stemId + '/save-instrument/' + inst + '?token=' + encodeURIComponent(getToken()), {
                method: 'POST'
              });
              if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                throw new Error(err.detail || ('Failed to save ' + inst));
              }
            }
            btn.textContent = 'Saved!';
            setTimeout(() => { navMyStemsBtn.click(); }, 700);
          } catch (e) {
            btn.textContent = 'Failed';
            setTimeout(() => { btn.textContent = prevText; btn.disabled = false; }, 1500);
          }
        });
      });

      myStemsList.querySelectorAll('.load-all-mixer-btn').forEach(btn => {
        btn.addEventListener('click', async () => {
          const row = btn.closest('.my-stems-row');
          const stemId = row.dataset.stemId;
          const trackName = row.dataset.trackName;
          const instrument = row.dataset.instrument;
          if (!window.__loadBackendStemToChannel) return;
          btn.disabled = true;
          const prevText = btn.textContent;
          btn.textContent = 'Loading…';
          try {
            const targets = instrument ? [instrument] : CHANNEL_LIST;
            const results = await Promise.all(
              targets.map(chan => window.__loadBackendStemToChannel(chan, stemId, trackName))
            );
            const loadedCount = results.filter(Boolean).length;
            const previewLabelEl = document.getElementById('previewLabel');
            if (previewLabelEl && loadedCount > 0) previewLabelEl.textContent = trackName;
            btn.textContent = loadedCount === targets.length ? 'Loaded!' : ('Loaded ' + loadedCount + '/' + targets.length);
            setTimeout(() => { btn.textContent = prevText; btn.disabled = false; }, 1500);
          } catch (e) {
            btn.textContent = 'Failed';
            setTimeout(() => { btn.textContent = prevText; btn.disabled = false; }, 1500);
          }
        });
      });

      let previewAudioCtx = null;
      let previewActive = null;
      function stopPreview() {
        if (!previewActive) return;
        try { previewActive.audio.pause(); } catch(e) {}
        if (previewActive.raf) cancelAnimationFrame(previewActive.raf);
        previewActive = null;
      }
      function drawWave(canvas, buffer, progress) {
        const ctx = canvas.getContext('2d');
        const w = canvas.width, h = canvas.height;
        ctx.clearRect(0, 0, w, h);
        const data = buffer.getChannelData(0);
        const step = Math.ceil(data.length / w);
        ctx.fillStyle = 'rgba(255,138,61,0.55)';
        for (let x = 0; x < w; x++) {
          let min = 1, max = -1;
          const start = x * step;
          for (let i = 0; i < step; i++) {
            const v = data[start + i] || 0;
            if (v < min) min = v;
            if (v > max) max = v;
          }
          const y1 = (1 + min) * 0.5 * h;
          const y2 = (1 + max) * 0.5 * h;
          ctx.fillRect(x, y1, 1, Math.max(1, y2 - y1));
        }
        if (progress != null) {
          const px = Math.floor(progress * w);
          ctx.fillStyle = '#ff8a3d';
          ctx.fillRect(px, 0, 1, h);
        }
      }
      myStemsList.querySelectorAll('.preview-wave-canvas').forEach(canvas => {
        let buffer = null;
        let loading = false;
        let hovering = false;
        let liveAudio = null;
        canvas.addEventListener('mouseenter', async () => {
          stopPreview();
          hovering = true;
          const url = canvas.dataset.previewUrl;
          if (!previewAudioCtx) previewAudioCtx = new (window.AudioContext || window.webkitAudioContext)();
          if (!buffer) {
            if (loading) return;
            loading = true;
            try {
              const res = await fetch(url);
              const arrBuf = await res.arrayBuffer();
              buffer = await previewAudioCtx.decodeAudioData(arrBuf);
              drawWave(canvas, buffer, 0);
            } catch (e) {
              loading = false;
              return;
            }
            loading = false;
          }
          if (!hovering) return;
          const audio = new Audio(url);
          liveAudio = audio;
          audio.play().catch(() => {});
          previewActive = { canvas, audio, buffer };
          const tick = () => {
            if (!previewActive || previewActive.audio !== audio) return;
            drawWave(canvas, buffer, audio.duration ? audio.currentTime / audio.duration : 0);
            previewActive.raf = requestAnimationFrame(tick);
          };
          tick();
          audio.addEventListener('ended', () => { if (previewActive && previewActive.audio === audio) { drawWave(canvas, buffer, 0); stopPreview(); } liveAudio = null; });
        });
        canvas.addEventListener('mouseleave', () => {
          hovering = false;
          if (liveAudio) { try { liveAudio.pause(); } catch (e) {} liveAudio = null; }
          if (previewActive && previewActive.canvas === canvas) {
            stopPreview();
          }
          if (buffer) drawWave(canvas, buffer, 0);
        });
      });

      myStemsList.querySelectorAll('.delete-stem-btn').forEach(btn => {
        btn.addEventListener('click', async () => {
          const row = btn.closest('.my-stems-row');
          const stemId = row.dataset.stemId;
          const trackName = row.dataset.trackName;
          if (!confirm('Delete "' + trackName + '"? This can\'t be undone.')) return;
          btn.disabled = true;
          const prevText = btn.textContent;
          btn.textContent = '…';
          try {
            const res = await fetch(API_BASE + '/api/v1/my-stems/' + stemId + '?token=' + encodeURIComponent(getToken()), {
              method: 'DELETE'
            });
            const resData = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(resData.detail || 'Could not delete.');
            row.remove();
            if (!myStemsList.querySelector('.my-stems-row')) {
              myStemsList.innerHTML = '<div style="color:var(--chrome-dim);font-size:0.8rem;">No splits yet — drop a song above to get started.</div>';
            }
          } catch (e) {
            btn.textContent = 'Failed';
            setTimeout(() => { btn.textContent = prevText; btn.disabled = false; }, 1500);
          }
        });
      });
    } catch (err) {
      myStemsList.innerHTML = '<div style="color:var(--clip-red);font-size:0.8rem;">' + escapeHtml(err.message) + '</div>';
    }
  });

  (function initMixerConsole() {
    const STEM_TYPES = ['vocals', 'drums', 'bass', 'guitar', 'other'];
    const lib = {};
    STEM_TYPES.forEach(t => lib[t] = { items: [], filtered: [], selected: 0, loaded: null, query: '' });

    const chPitch = {};
    STEM_TYPES.forEach(t => chPitch[t] = 0);

    const NOTES = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B'];
    function pitchLabel(semis) {
      const idx = ((semis % 12) + 12) % 12;
      const sign = semis > 0 ? '+' : semis < 0 ? '' : '\u00B1';
      return `${sign}${semis} \u00B7 ${NOTES[idx]}`;
    }
    function esc(s) {
      return String(s == null ? '' : s)
        .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
        .replace(/"/g,'&quot;');
    }

    function applyFilter(type) {
      const st = lib[type];
      const q = st.query.trim().toLowerCase();
      st.filtered = q
        ? st.items.filter(it => (it.name || '').toLowerCase().includes(q))
        : st.items.slice();
      if (st.selected >= st.filtered.length) st.selected = Math.max(0, st.filtered.length - 1);
    }

    function renderPop(type) {
      const listEl = document.querySelector('.stem-pop-list[data-poplist="' + type + '"]');
      if (!listEl) return;
      const st = lib[type];
      applyFilter(type);

      if (!st.filtered.length) {
        listEl.innerHTML = '<div class="stem-pop-empty">' +
          (st.items.length ? 'no match' : 'no stems') + '</div>';
        return;
      }
      listEl.innerHTML = st.filtered.map((it, i) => {
        const sel = i === st.selected ? ' sel' : '';
        const loaded = st.loaded === it.id ? ' loaded' : '';
        return '<div class="stem-pop-item' + sel + loaded + '" data-idx="' + i + '" title="' +
          esc(it.name) + '">' + esc(it.name) + '</div>';
      }).join('');

      listEl.querySelectorAll('.stem-pop-item').forEach(el => {
        el.addEventListener('click', () => {
          st.selected = parseInt(el.dataset.idx, 10);
          renderPop(type);
        });
        el.addEventListener('dblclick', () => {
          st.selected = parseInt(el.dataset.idx, 10);
          loadStemToChannel(type);
        });
      });
      const selEl = listEl.querySelector('.stem-pop-item[data-idx="' + st.selected + '"]');
      if (selEl) selEl.scrollIntoView({ block: 'nearest' });
    }

    async function loadStemToChannel(type) {
      const st = lib[type];
      if (!st.filtered.length) return;
      const item = st.filtered[st.selected];
      st.loaded = item.id;
      renderPop(type);
      closePop(type);

      if (window.__loadBackendStemToChannel) {
        await window.__loadBackendStemToChannel(type, item.id, item.name);
      } else {
        const channel = document.querySelector('.channel[data-stem="' + type + '"]');
        if (channel) {
          const badge = channel.querySelector('.assigned-badge');
          if (badge) { badge.textContent = item.name; badge.classList.add('show'); }
        }
      }
      updateLoadedReadout();
    }

    function unloadStemFromChannel(type) {
      const st = lib[type];
      st.loaded = null;
      renderPop(type);

      if (window.__restoreOriginalStem) {
        window.__restoreOriginalStem(type);
      } else {
        const channel = document.querySelector('.channel[data-stem="' + type + '"]');
        if (channel) {
          const badge = channel.querySelector('.assigned-badge');
          if (badge) { badge.textContent = ''; badge.classList.remove('show'); }
        }
      }
      updateLoadedReadout();
    }
    window.__unloadStemFromChannel = unloadStemFromChannel;

    function updateLoadedReadout() {
      const n = STEM_TYPES.filter(t => lib[t].loaded !== null).length;
      const lcdLoaded = document.getElementById('lcdLoaded');
      if (lcdLoaded) lcdLoaded.textContent = n;
      const status = document.getElementById('lcdStatus');
      if (status) status.textContent = n ? 'LOADED' : 'READY';
    }

    async function renameStem(type) {
      const st = lib[type];
      if (!st.filtered.length) return;
      const item = st.filtered[st.selected];
      const next = window.prompt('Rename stem:', item.name);
      if (next == null) return;
      const name = next.trim();
      if (!name || name === item.name) return;
      item.name = name;
      renderPop(type);
      if (st.loaded === item.id) {
        const badge = document.querySelector('.channel[data-stem="' + type + '"] .assigned-badge');
        if (badge) badge.textContent = name;
      }
      if (typeof getToken === 'function' && getToken()) {
        try {
          await fetch(API_BASE + '/api/v1/stems/' + encodeURIComponent(item.id) + '/rename', {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token: getToken(), name: name })
          });
        } catch (e) { /* offline / structure-first: keep local rename */ }
      }
    }

    function positionPop(pop, anchorBtn) {
      const rect = anchorBtn.getBoundingClientRect();
      const popW = 168;
      let left = rect.left + rect.width / 2 - popW / 2;
      left = Math.max(8, Math.min(left, window.innerWidth - popW - 8));
      pop.style.left = left + 'px';
      pop.style.width = popW + 'px';
      const estHeight = 230;
      let top = rect.bottom + 6;
      if (top + estHeight > window.innerHeight - 8) {
        top = Math.max(8, rect.top - estHeight - 6);
      }
      pop.style.top = top + 'px';
    }

    function openPop(type) {
      STEM_TYPES.forEach(t => { if (t !== type) closePop(t); });
      const pop = document.querySelector('.stem-pop[data-pop="' + type + '"]');
      if (!pop) return;
      if (pop.dataset.portaled !== '1') {
        document.body.appendChild(pop);
        pop.dataset.portaled = '1';
        pop.style.position = 'fixed';
        pop.style.transform = 'none';
      }
      const anchorBtn = document.querySelector('.ch-browse[data-browse="' + type + '"]');
      if (anchorBtn) positionPop(pop, anchorBtn);
      pop.style.display = 'flex';
      renderPop(type);
      const search = pop.querySelector('.stem-pop-search');
      if (search) { search.value = lib[type].query; setTimeout(() => search.focus(), 30); }
    }
    function closePop(type) {
      const pop = document.querySelector('.stem-pop[data-pop="' + type + '"]');
      if (pop) pop.style.display = 'none';
    }
    function togglePop(type) {
      const pop = document.querySelector('.stem-pop[data-pop="' + type + '"]');
      if (pop && pop.style.display === 'flex') closePop(type); else openPop(type);
    }

    document.querySelectorAll('.ch-browse').forEach(btn => {
      btn.addEventListener('click', (e) => { e.stopPropagation(); togglePop(btn.dataset.browse); });
    });
    window.addEventListener('resize', () => {
      STEM_TYPES.forEach(t => {
        const pop = document.querySelector('.stem-pop[data-pop="' + t + '"]');
        const anchorBtn = document.querySelector('.ch-browse[data-browse="' + t + '"]');
        if (pop && anchorBtn && pop.style.display === 'flex') positionPop(pop, anchorBtn);
      });
    });

    function syncClearButtons() {
      document.querySelectorAll('.ch-clear').forEach(btn => {
        const type = btn.dataset.clear;
        const isLoaded = lib[type] && lib[type].loaded !== null;
        btn.classList.toggle('armed', !!isLoaded);
      });
    }
    document.querySelectorAll('.ch-clear').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const type = btn.dataset.clear;
        unloadStemFromChannel(type);
        if (window.__clearChannelAssignment) {
          window.__clearChannelAssignment(type);
        }
        const chEl = document.querySelector('.channel[data-stem="' + type + '"]');
        if (chEl) {
          const badge = chEl.querySelector('.assigned-badge');
          if (badge) { badge.textContent = ''; badge.classList.remove('show'); }
          const led = chEl.querySelector('.status-led');
          if (led) led.classList.remove('playing', 'on');
        }
        closePop(type);
        syncClearButtons();
      });
    });
    const _origUpdateLoadedReadout = updateLoadedReadout;
    updateLoadedReadout = function () {
      _origUpdateLoadedReadout.apply(this, arguments);
      syncClearButtons();
    };
    syncClearButtons();
    STEM_TYPES.forEach(type => {
      const pop = document.querySelector('.stem-pop[data-pop="' + type + '"]');
      if (!pop) return;
      pop.addEventListener('click', e => e.stopPropagation());

      const closeBtn = pop.querySelector('[data-popclose]');
      if (closeBtn) closeBtn.addEventListener('click', () => closePop(type));

      const search = pop.querySelector('[data-popsearch]');
      if (search) {
        search.addEventListener('input', () => {
          lib[type].query = search.value;
          lib[type].selected = 0;
          renderPop(type);
        });
        search.addEventListener('keydown', e => {
          const st = lib[type];
          if (e.key === 'ArrowDown') { e.preventDefault(); st.selected = Math.min(st.filtered.length - 1, st.selected + 1); renderPop(type); }
          else if (e.key === 'ArrowUp') { e.preventDefault(); st.selected = Math.max(0, st.selected - 1); renderPop(type); }
          else if (e.key === 'Enter') { e.preventDefault(); loadStemToChannel(type); }
          else if (e.key === 'Escape') { e.preventDefault(); closePop(type); }
        });
      }
      const up = pop.querySelector('[data-popup2]');
      if (up) up.addEventListener('click', () => { const st = lib[type]; st.selected = Math.max(0, st.selected - 1); renderPop(type); });
      const down = pop.querySelector('[data-popdown]');
      if (down) down.addEventListener('click', () => { const st = lib[type]; st.selected = Math.min(st.filtered.length - 1, st.selected + 1); renderPop(type); });
      const load = pop.querySelector('[data-popload]');
      if (load) load.addEventListener('click', () => loadStemToChannel(type));
      const eject = pop.querySelector('[data-popeject]');
      if (eject) eject.addEventListener('click', () => unloadStemFromChannel(type));
      const rename = pop.querySelector('[data-poprename]');
      if (rename) rename.addEventListener('click', () => renameStem(type));
    });
    document.addEventListener('click', () => STEM_TYPES.forEach(closePop));

    document.querySelectorAll('.channel').forEach(channel => {
      const badge = channel.querySelector('.assigned-badge');
      if (!badge) return;
      badge.style.cursor = 'pointer';
      badge.title = 'Click to remove';
      badge.addEventListener('click', (e) => {
        e.stopPropagation();
        unloadStemFromChannel(channel.dataset.stem);
      });
    });

    document.querySelectorAll('.channel').forEach(channel => {
      const type = channel.dataset.stem;
      const valEl = channel.querySelector('[data-pitch-val]');
      channel.querySelectorAll('.ch-pitch-btn').forEach(btn => {
        btn.addEventListener('click', () => {
          const dir = btn.dataset.pitch === 'up' ? 1 : -1;
          chPitch[type] = Math.max(-12, Math.min(12, chPitch[type] + dir));
          if (valEl) valEl.innerHTML = pitchLabel(chPitch[type]);
          if (typeof stemNodes !== 'undefined' && stemNodes[type] && stemNodes[type].pitchShift) {
            stemNodes[type].pitchShift.pitch = chPitch[type];
          }
        });
      });
    });

    async function loadLibraries() {
      if (typeof getToken !== 'function' || !getToken()) return;
      try {
        const res = await fetch(API_BASE + '/api/v1/my-stems?include_unsaved=true&token=' + encodeURIComponent(getToken()));
        const data = await res.json();
        if (!res.ok || !Array.isArray(data)) return;
        STEM_TYPES.forEach(t => {
          lib[t].items = data
            .filter(stem => !stem.instrument || stem.instrument === t)
            .map(stem => ({ id: stem.id, name: stem.track_name }));
          lib[t].selected = 0;
          renderPop(t);
        });
      } catch (e) { /* structure-first: silent until backend live */ }
    }

    loadLibraries();
    window.__reloadLibraries = loadLibraries;
  })();
})();
