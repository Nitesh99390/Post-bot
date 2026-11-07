/* Post Maker Mini App: shared core (state, API client with retries, UI helpers). */
(function () {
  'use strict';
  const tg = (window.Telegram && window.Telegram.WebApp) || null;
  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const icon = (n, c) => window.icon(n, c);

  const PM = (window.PM = { tg, $, $$, esc, sleep, icon, A: {}, S: {
    user: null, chats: [], draft: { text: '', buttons: [], link_preview: true, media_type: null, media_name: '' },
    bot: '', storage: '', limits: { text: 4000, caption: 1024, buttons: 10, chats: 100, saved: 30, upload_mb: 30 },
    tab: 'compose', saved: null, online: navigator.onLine !== false,
  }, mods: {} });
  const S = PM.S;

  /* ---------- tiny event bus ---------- */
  const bus = {};
  PM.on = (e, f) => ((bus[e] = bus[e] || []).push(f), f);
  PM.emit = (e, d) => (bus[e] || []).slice().forEach((f) => { try { f(d); } catch (x) { console.error(e, x); } });

  /* ---------- haptics ---------- */
  PM.haptic = (k) => {
    try {
      const h = tg && tg.HapticFeedback; if (!h) return;
      if (k === 'success' || k === 'error' || k === 'warning') h.notificationOccurred(k);
      else if (k === 'select') h.selectionChanged();
      else h.impactOccurred(k || 'light');
    } catch (_) {}
  };

  /* ---------- sync chip ---------- */
  const SYNC = {
    saved: ['cloud-check', 'Synced'], saving: ['loader-circle', 'Saving'],
    error: ['triangle-alert', 'Retrying'], offline: ['cloud-off', 'Offline'],
  };
  let syncState = 'saved';
  PM.setSync = (s, label) => {
    syncState = s;
    const el = $('#sync'); if (!el) return;
    const d = SYNC[s] || SYNC.saved;
    el.dataset.s = s;
    el.innerHTML = icon(d[0]) + '<span>' + esc(label || d[1]) + '</span>';
    try {
      if (tg && tg.isVersionAtLeast && tg.isVersionAtLeast('6.2')) {
        if (s === 'saving' || s === 'error' || s === 'offline') tg.enableClosingConfirmation();
        else tg.disableClosingConfirmation();
      }
    } catch (_) {}
  };
  PM.syncState = () => syncState;

  /* ---------- errors ---------- */
  class ApiErr extends Error {
    constructor(status, code, message, network) { super(message); this.status = status; this.code = code; this.network = !!network; }
  }
  PM.ApiErr = ApiErr;

  PM.fatal = (title, msg, btn) => {
    const b = $('#blocker'); if (!b) return;
    b.hidden = false;
    b.innerHTML = '<div class="empty-art">' + icon('shield-check') + '</div><h2>' + esc(title) + '</h2><p>' + esc(msg) + '</p>' +
      (btn ? '<button class="btn primary" data-act="' + btn.act + '">' + esc(btn.label) + '</button>' : '');
    const boot = $('#boot'); if (boot) boot.classList.add('out');
  };
  PM.A.reload = () => location.reload();
  PM.A.closeApp = () => { if (tg) tg.close(); };

  /* ---------- API ---------- */
  const initData = () => (tg ? tg.initData || '' : '');
  PM.hasAuth = () => !!initData();
  PM.api = async function (method, path, body, opt) {
    opt = opt || {};
    const retries = opt.retries != null ? opt.retries : (method === 'GET' ? 3 : 0);
    let attempt = 0;
    for (;;) {
      const ctl = new AbortController();
      const timer = setTimeout(() => ctl.abort(), opt.timeout || 20000);
      try {
        const headers = { 'X-Init-Data': initData() };
        if (body !== undefined) headers['Content-Type'] = 'application/json';
        const res = await fetch(path, {
          method, headers, signal: ctl.signal, cache: 'no-store', keepalive: !!opt.keepalive,
          body: body !== undefined ? JSON.stringify(body) : undefined,
        });
        clearTimeout(timer);
        let data = null; try { data = await res.json(); } catch (_) {}
        if (res.ok && data && data.ok) { PM.setOnline(true); return data; }
        const err = new ApiErr(res.status, (data && data.error) || 'http', (data && data.message) || 'Request failed', false);
        if ([429, 502, 503, 504].includes(res.status) && attempt < retries) {
          attempt++;
          await sleep(Math.max((Number(res.headers.get('Retry-After')) || 0) * 1000, 400 * Math.pow(2, attempt)));
          continue;
        }
        if (res.status === 401) PM.fatal(err.code === 'expired' ? 'Session expired' : 'Open from Telegram', err.message, { act: 'closeApp', label: 'Close' });
        throw err;
      } catch (e) {
        clearTimeout(timer);
        if (e instanceof ApiErr) throw e;
        PM.setOnline(false);
        if (attempt < retries) { attempt++; await sleep(400 * Math.pow(2, attempt)); continue; }
        throw new ApiErr(0, 'network', 'No connection. Your changes are kept and will sync.', true);
      }
    }
  };

  PM.upload = function (file, onProgress) {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open('POST', '/api/media');
      xhr.setRequestHeader('X-Init-Data', initData());
      xhr.setRequestHeader('X-File-Name', encodeURIComponent(file.name || 'file'));
      xhr.setRequestHeader('Content-Type', file.type || 'application/octet-stream');
      xhr.timeout = 5 * 60 * 1000;
      xhr.upload.onprogress = (e) => { if (e.lengthComputable && onProgress) onProgress(e.loaded / e.total); };
      xhr.onload = () => {
        let d = null; try { d = JSON.parse(xhr.responseText); } catch (_) {}
        if (xhr.status >= 200 && xhr.status < 300 && d && d.ok) return resolve(d);
        reject(new ApiErr(xhr.status, (d && d.error) || 'http', (d && d.message) || 'Upload failed. Try again.', false));
      };
      xhr.onerror = xhr.ontimeout = () => reject(new ApiErr(0, 'network', 'Upload interrupted. Check your connection and retry.', true));
      xhr.send(file);
    });
  };

  PM.setOnline = (on) => {
    if (S.online === on) return;
    S.online = on;
    if (!on) PM.setSync('offline');
    else { PM.setSync(PM.mods.draft && PM.mods.draft.pending() ? 'saving' : 'saved'); PM.emit('online'); }
  };
  window.addEventListener('offline', () => PM.setOnline(false));
  window.addEventListener('online', () => PM.setOnline(true));

  /* ---------- avatars ---------- */
  const PAL = [['#7c5cff', '#3b82f6'], ['#ec4899', '#f97316'], ['#10b981', '#06b6d4'], ['#f59e0b', '#ef4444'], ['#8b5cf6', '#ec4899'], ['#0ea5e9', '#6366f1'], ['#14b8a6', '#84cc16'], ['#f43f5e', '#a855f7']];
  PM.initials = (name) => {
    const w = String(name || '?').replace(/[^\p{L}\p{N} ]/gu, '').trim().split(/\s+/).filter(Boolean);
    return ((w[0] ? Array.from(w[0])[0] : '?') + (w[1] ? Array.from(w[1])[0] : '')).toUpperCase();
  };
  PM.avatar = (name, id, o) => {
    o = o || {};
    const p = PAL[Math.abs(Number(id) || 0) % PAL.length];
    const bg = 'background:linear-gradient(135deg,' + p[0] + ',' + p[1] + ')';
    const ini = esc(PM.initials(name));
    const img = o.photo ? '<img src="' + esc(o.photo) + '" alt="" referrerpolicy="no-referrer" data-ini="' + ini + '">' : ini;
    return '<div class="av ' + (o.cls || '') + '" style="' + bg + '">' + img + '</div>';
  };
  document.addEventListener('error', (e) => {
    const t = e.target;
    if (t && t.tagName === 'IMG' && t.dataset && t.dataset.ini != null) t.replaceWith(document.createTextNode(t.dataset.ini));
  }, true);

  /* ---------- toasts ---------- */
  PM.toast = (msg, kind, ms) => {
    kind = kind || 'info';
    const ic = { ok: 'circle-check', err: 'circle-x', warn: 'triangle-alert', info: 'info' }[kind];
    const box = $('#toasts'); if (!box) return;
    while (box.children.length > 2) box.firstChild.remove();
    const el = document.createElement('div');
    el.className = 'toast ' + kind;
    el.innerHTML = icon(ic) + '<span>' + esc(msg) + '</span>';
    box.appendChild(el);
    if (kind === 'ok') PM.haptic('success'); else if (kind === 'err') PM.haptic('error');
    setTimeout(() => { el.classList.add('out'); setTimeout(() => el.remove(), 320); }, ms || 3000);
  };

  /* ---------- bottom sheet ---------- */
  let cur = null;
  PM.sheet = function (o) {
    if (cur) cur.close(true);
    const root = $('#sheetRoot');
    const scrim = document.createElement('div'); scrim.className = 'scrim';
    const el = document.createElement('div'); el.className = 'sheet'; el.setAttribute('role', 'dialog'); el.setAttribute('aria-modal', 'true');
    el.innerHTML = '<div class="grab"></div><div class="sheet-b"></div><div class="sheet-f"></div>';
    root.append(scrim, el);
    const body = $('.sheet-b', el), foot = $('.sheet-f', el);
    body.innerHTML = o.body || ''; foot.innerHTML = o.footer || ''; foot.hidden = !o.footer;
    foot.className = 'sheet-f' + (o.two ? ' two' : '');
    let closed = false;
    const api = {
      el, body, foot, dismissable: o.dismissable !== false,
      setBody(h) { body.innerHTML = h; },
      setFooter(h, two) { foot.innerHTML = h; foot.hidden = !h; foot.className = 'sheet-f' + (two ? ' two' : ''); },
      close(instant) {
        if (closed) return; closed = true; if (cur === api) cur = null;
        scrim.classList.remove('on'); el.classList.remove('on');
        setTimeout(() => { scrim.remove(); el.remove(); }, instant ? 0 : 420);
        if (o.onClose) o.onClose();
        PM.emit('sheet');
      },
    };
    cur = api;
    requestAnimationFrame(() => requestAnimationFrame(() => { scrim.classList.add('on'); el.classList.add('on'); }));
    scrim.addEventListener('click', () => api.dismissable && api.close());
    const grab = $('.grab', el); let y0 = null, dy = 0, t0 = 0;
    grab.addEventListener('pointerdown', (e) => { y0 = e.clientY; dy = 0; t0 = Date.now(); el.classList.add('drag'); grab.setPointerCapture(e.pointerId); });
    grab.addEventListener('pointermove', (e) => { if (y0 == null) return; dy = Math.max(0, e.clientY - y0); el.style.transform = 'translateY(' + dy + 'px)'; });
    const end = () => {
      if (y0 == null) return; y0 = null; el.classList.remove('drag'); el.style.transform = '';
      if (api.dismissable && (dy > 110 || (dy > 40 && Date.now() - t0 < 220))) api.close();
    };
    grab.addEventListener('pointerup', end); grab.addEventListener('pointercancel', end);
    PM.emit('sheet');
    return api;
  };
  PM.sheetOpen = () => !!cur;
  PM.closeSheet = () => cur && cur.dismissable && cur.close();
  PM.A.closeSheet = () => { if (cur) cur.close(); };
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') PM.closeSheet(); });

  /* ---------- confetti ---------- */
  PM.confetti = () => {
    if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const c = $('#fx'); if (!c) return;
    const dpr = window.devicePixelRatio || 1;
    c.width = innerWidth * dpr; c.height = innerHeight * dpr;
    const g = c.getContext('2d'); g.scale(dpr, dpr);
    const cols = ['#7c5cff', '#3b82f6', '#22d3ee', '#22c55e', '#f5b301', '#ec4899'];
    const P = Array.from({ length: 90 }, () => ({
      x: innerWidth / 2, y: innerHeight * 0.62, vx: (Math.random() - 0.5) * 15, vy: -Math.random() * 15 - 5,
      s: Math.random() * 7 + 4, r: Math.random() * 6, vr: (Math.random() - 0.5) * 0.4, c: cols[(Math.random() * cols.length) | 0],
    }));
    let f = 0;
    (function tick() {
      g.clearRect(0, 0, innerWidth, innerHeight);
      P.forEach((p) => {
        p.vy += 0.38; p.vx *= 0.99; p.x += p.vx; p.y += p.vy; p.r += p.vr;
        g.save(); g.translate(p.x, p.y); g.rotate(p.r); g.globalAlpha = Math.max(0, 1 - f / 95);
        g.fillStyle = p.c; g.fillRect(-p.s / 2, -p.s / 4, p.s, p.s / 2); g.restore();
      });
      if (++f < 100) requestAnimationFrame(tick); else g.clearRect(0, 0, innerWidth, innerHeight);
    })();
  };

  /* ---------- global click delegation ---------- */
  document.addEventListener('click', (e) => {
    const t = e.target.closest('[data-act]'); if (!t || t.disabled) return;
    const fn = PM.A[t.dataset.act]; if (!fn) return;
    e.preventDefault();
    Promise.resolve().then(() => fn(t, e)).catch((err) => {
      console.error(err);
      PM.toast((err && err.message) || 'Something went wrong. Try again.', 'err');
    });
  });

  PM.openLink = (url) => {
    try { if (tg && /^https:\/\/t\.me\//.test(url)) return tg.openTelegramLink(url); if (tg) return tg.openLink(url); } catch (_) {}
    window.open(url, '_blank', 'noopener');
  };
  PM.A.openUrl = (el) => PM.openLink(el.dataset.url);

  PM.uuid = () => (crypto.randomUUID ? crypto.randomUUID() : 'r' + Date.now().toString(36) + Math.random().toString(36).slice(2, 12));
  PM.plural = (n, a, b) => n + ' ' + (n === 1 ? a : b);
})();
