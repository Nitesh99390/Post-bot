/* Boot, navigation, send bar and the send/progress flow. */
(function () {
  'use strict';
  const { S, tg, $, $$, esc, icon, toast } = PM;
  const TABS = [['compose', 'square-pen', 'Compose'], ['groups', 'users-round', 'Groups'], ['saved', 'bookmark', 'Saved'], ['profile', 'user-round', 'Profile']];
  const typeName = (t) => (t === 'channel' ? 'Channel' : t === 'supergroup' ? 'Supergroup' : 'Group');
  const G = () => PM.mods.groups, D = () => PM.mods.draft;

  /* ---------- theme + safe area ---------- */
  function applyTheme() {
    const dark = tg && tg.colorScheme ? tg.colorScheme === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
    document.documentElement.dataset.theme = dark ? 'dark' : 'light';
    const bg = dark ? '#0a0c13' : '#f3f5fb';
    const m = $('meta[name=theme-color]'); if (m) m.content = bg;
    try { if (tg) { tg.setHeaderColor(bg); tg.setBackgroundColor(bg); tg.setBottomBarColor && tg.setBottomBarColor(bg); } } catch (_) {}
  }
  function applyInsets() {
    if (!tg) return;
    const a = tg.safeAreaInset || {}, b = tg.contentSafeAreaInset || {};
    const st = document.documentElement.style;
    st.setProperty('--top', ((a.top || 0) + (b.top || 0)) + 'px');
    st.setProperty('--bottom', ((a.bottom || 0) + (b.bottom || 0)) + 'px');
  }

  /* ---------- navigation ---------- */
  function buildNav() {
    $$('#nav button').forEach((b, i) => {
      const t = TABS[i]; b.innerHTML = icon(t[1]) + '<span>' + t[2] + '</span>'; b.setAttribute('aria-label', t[2]);
      b.addEventListener('click', () => PM.go(t[0]));
    });
  }
  PM.go = function (tab) {
    const idx = TABS.findIndex((t) => t[0] === tab); if (idx < 0) return;
    const changed = S.tab !== tab; S.tab = tab;
    $$('.view').forEach((v) => v.classList.toggle('on', v.dataset.view === tab));
    $$('#nav button').forEach((b, i) => { b.classList.toggle('on', i === idx); b.setAttribute('aria-current', i === idx ? 'page' : 'false'); });
    $('#navDot').style.transform = 'translateX(' + idx * 100 + '%)';
    const title = $('#topTitle');
    if (changed) { title.textContent = TABS[idx][2]; title.classList.remove('swap'); void title.offsetWidth; title.classList.add('swap'); PM.haptic('select'); }
    try { if (tg && tg.BackButton) (tab === 'compose' ? tg.BackButton.hide() : tg.BackButton.show()); } catch (_) {}
    paintBar();
    if (changed) PM.emit('tab', tab);
  };

  /* ---------- send bar ---------- */
  let barHtml = '';
  function ready() {
    const d = D(); if (!d) return { ok: false };
    if (d.busyUpload()) return { ok: false, why: 'Wait for the upload to finish' };
    if (d.isEmpty()) return { ok: false, why: 'Write something or attach a file first' };
    if (d.over()) return { ok: false, why: 'Your text is too long for Telegram' };
    if (!S.chats.length) return { ok: false, why: 'Add a group or channel first', tab: 'groups' };
    if (!G().selected().length) return { ok: false, why: 'Pick where to send. Open the Groups tab', tab: 'groups' };
    return { ok: true };
  }
  function paintBar() {
    const bar = $('#sendbar'), show = S.tab === 'compose' || S.tab === 'groups';
    $$('#view-compose,#view-groups').forEach((v) => v.classList.add('has-bar'));
    const sel = G().selected(), r = ready();
    let t;
    if (!S.chats.length) t = ['No groups yet', 'Tap to add one'];
    else if (!sel.length) t = ['Choose where to send', 'Tap to pick groups'];
    else if (sel.length === 1) t = [sel[0].title, typeName(sel[0].type)];
    else t = [PM.plural(sel.length, 'chat', 'chats'), sel.slice(0, 2).map((c) => c.title).join(', ') + (sel.length > 2 ? '…' : '')];
    const html = '<div class="sendbar-in"><button class="targets' + (sel.length ? '' : ' empty') + '" data-act="goGroups" aria-label="Choose groups">' +
      '<div class="stack">' + (sel.length ? sel.slice(0, 3).map((c) => PM.avatar(c.title, c.chat_id, { cls: 'sm' })).join('') : '<div class="av sm" style="background:var(--s3);color:var(--mut)">' + icon('users-round') + '</div>') + '</div>' +
      '<div class="tt"><b>' + esc(t[0]) + '</b><span>' + esc(t[1]) + '</span></div></button>' +
      '<button class="btn primary" data-act="send" aria-disabled="' + (!r.ok) + '">' + icon('send') + 'Send</button></div>';
    if (html !== barHtml) { bar.innerHTML = html; barHtml = html; }
    bar.classList.toggle('on', show);
    bar.inert = !show;
  }
  PM.A.goGroups = () => PM.go('groups');
  PM.on('chats', paintBar); PM.on('draft-meta', paintBar);

  /* ---------- send flow ---------- */
  let sending = false, reqId = null, reqKey = '', counted = new Set(), progress = null;
  const ICON = { queued: 'clock', sending: 'loader-circle', ok: 'check', failed: 'x', partial: 'triangle-alert', unconfirmed: 'circle-alert' };
  const LABEL = { queued: 'Waiting…', sending: 'Sending…', ok: 'Delivered', failed: 'Failed', partial: 'Partly sent', unconfirmed: 'Not confirmed' };

  PM.A.send = async () => {
    if (sending) return;
    const r = ready();
    if (!r.ok) { PM.haptic('warning'); toast(r.why, 'warn'); if (r.tab) PM.go(r.tab); return; }
    sending = true;
    try {
      await D().flush(); await G().flush();
      if (D().pending()) { PM.haptic('error'); return toast('Your draft is still syncing. Try again in a moment.', 'warn'); }
      const targets = G().selected();
      confirmSheet(targets);
    } finally { sending = false; }
  };

  function plainPreview() { const t = PM.tgClean(S.draft.text || '').plain.replace(/\s+/g, ' '); return t.length > 120 ? t.slice(0, 120) + '…' : t; }
  function confirmSheet(targets) {
    const ids = targets.map((c) => c.chat_id);
    const sh = PM.sheet({
      body: '<h2>Send to ' + PM.plural(targets.length, 'chat', 'chats') + '?</h2><p>' + (plainPreview() ? esc(plainPreview()) : 'Your ' + esc(S.draft.media_type || 'post')) + '</p>' +
        '<div style="display:grid;gap:8px;max-height:34vh;overflow:auto">' + targets.map((c) =>
          '<div class="res" style="animation:none">' + PM.avatar(c.title, c.chat_id, { cls: 'sm' }) + '<div class="grow"><b>' + esc(c.title) + '</b><span>' + typeName(c.type) + '</span></div></div>').join('') + '</div>',
      footer: '<button class="btn soft" data-act="closeSheet">Cancel</button><button class="btn primary" data-act="confirmSend">' + icon('send') + 'Send now</button>', two: true,
    });
    PM.A.confirmSend = async (el) => {
      el.disabled = true;
      const key = ids.join(',') + '|' + (S.draft.text || '').length;
      if (!reqId || reqKey !== key) { reqId = PM.uuid(); reqKey = key; } // reuse on retry so the server can dedupe
      try {
        const r = await PM.api('POST', '/api/send', { request_id: reqId, chat_ids: ids }, { retries: 2, timeout: 30000 });
        reqId = null; sh.close(true); showProgress(r.job);
      } catch (e) {
        el.disabled = false;
        if (e.code === 'busy') { sh.close(true); return resumeActive(true); }
        PM.haptic('error');
        if (!e.network) reqId = null;
        toast(e.message, 'err', 4200);
      }
    };
  }

  async function resumeActive(announce) {
    try {
      const r = await PM.api('GET', '/api/send/active');
      if (r.job && !r.job.done) { if (announce) toast('Your previous send is still running', 'info'); showProgress(r.job); }
      else if (announce) toast('Try again in a moment', 'info');
    } catch (_) {}
  }

  function ring(f) {
    const C = 2 * Math.PI * 26;
    return '<svg class="ringp" viewBox="0 0 60 60"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#7c5cff"/><stop offset="1" stop-color="#22d3ee"/></linearGradient></defs>' +
      '<circle class="bgc" cx="30" cy="30" r="26"/><circle class="fg" cx="30" cy="30" r="26" stroke-dasharray="' + C.toFixed(2) + '" stroke-dashoffset="' + (C * (1 - f)).toFixed(2) + '"/></svg>';
  }
  function resRow(r, i) {
    return '<div class="res" data-r="' + r.chat_id + '" style="--i:' + Math.min(i, 10) + '">' + PM.avatar(r.title, r.chat_id, { cls: 'sm' }) +
      '<div class="grow"><b>' + esc(r.title) + '</b><span></span></div><div class="link"></div><div class="st"></div></div>';
  }
  function paintResults(j) {
    const root = progress && progress.el; if (!root) return;
    const finished = j.results.filter((r) => !['queued', 'sending'].includes(r.status)).length;
    const f = j.total ? finished / j.total : 0;
    const sum = $('.summary', root);
    sum.innerHTML = ring(f) + '<div><div class="big">' + (j.done ? j.ok : finished) + '<span style="font-size:18px;color:var(--mut)"> / ' + j.total + '</span></div><div class="hint">' +
      (!j.done ? 'Sending…' : j.failed || j.unconfirmed ? j.ok + ' delivered, ' + (j.failed + j.unconfirmed) + ' need attention' : 'All delivered') + '</div></div>';
    j.results.forEach((r) => {
      const el = $('[data-r="' + r.chat_id + '"]', root); if (!el) return;
      if (el.dataset.s === r.status && el.dataset.e === (r.error || '')) return;
      el.dataset.s = r.status; el.dataset.e = r.error || '';
      const st = $('.st', el); st.className = 'st ' + r.status; st.innerHTML = icon(ICON[r.status] || 'clock');
      const sp = $('.grow span', el);
      sp.className = r.status === 'failed' || r.status === 'partial' ? 'e' : r.status === 'unconfirmed' ? 'w' : '';
      sp.textContent = r.error || LABEL[r.status] || '';
      $('.link', el).innerHTML = r.url ? '<button class="icon-btn" data-act="openUrl" data-url="' + esc(r.url) + '" aria-label="Open message">' + icon('external-link') + '</button>' : '';
    });
  }

  function showProgress(job) {
    if (progress) progress.close(true);
    const sh = PM.sheet({
      dismissable: false,
      body: '<h2>' + (job.done ? 'Done' : 'Sending your post') + '</h2><p id="pgSub"></p><div class="summary"></div><div id="pgList" style="max-height:40vh;overflow:auto">' + job.results.map(resRow).join('') + '</div>',
      onClose: () => { if (progress === sh) progress = null; },
    });
    progress = sh;
    let misses = 0, finished = false, lastRetry = null;
    const apply = (j) => {
      paintResults(j);
      const h = $('h2', sh.body); if (h) h.textContent = j.done ? (j.failed || j.unconfirmed ? 'Finished with issues' : 'Posted!') : 'Sending your post';
      const sub = $('#pgSub', sh.body);
      if (sub) sub.textContent = j.done ? (j.unconfirmed ? 'Some chats could not be confirmed. Check them before sending again, to avoid duplicates.' : j.failed ? 'You can retry the ones that failed.' : 'Your post is live in every selected chat.') : 'Keep this open or close the app. Sending continues.';
    };
    apply(job);
    const finish = (j) => {
      if (finished) return; finished = true; sh.dismissable = true;
      if (!counted.has(j.id)) {
        counted.add(j.id);
        const delivered = j.results.filter((r) => r.status === 'ok' || r.status === 'partial').length;
        if (delivered && S.user) { S.user.posts_created += 1; S.user.deliveries += delivered; PM.emit('stats'); }
      }
      const retryIds = j.results.filter((r) => r.status === 'failed').map((r) => r.chat_id);
      lastRetry = retryIds;
      PM.A.retryFailed = async (el) => {
        el.disabled = true;
        try { const r = await PM.api('POST', '/api/send', { request_id: PM.uuid(), chat_ids: retryIds }, { retries: 0, timeout: 30000 }); sh.close(true); showProgress(r.job); }
        catch (e) { el.disabled = false; toast(e.message, 'err'); }
      };
      PM.A.newPost = async (el) => { el.disabled = true; try { sh.close(); await D().clear(); PM.go('compose'); } catch (e) { el.disabled = false; toast(e.message, 'err'); } };
      const allOk = !j.failed && !j.unconfirmed;
      sh.setFooter(
        (retryIds.length ? '<button class="btn primary" data-act="retryFailed">' + icon('rotate-ccw') + 'Retry ' + retryIds.length + ' failed</button>' : allOk ? '<button class="btn primary" data-act="newPost">' + icon('sparkles') + 'New post</button>' : '') +
        '<button class="btn soft" data-act="closeSheet">Close</button>', false);
      if (allOk) { PM.confetti(); PM.haptic('success'); } else PM.haptic('warning');
    };
    if (job.done) return finish(job);
    (async function poll() {
      while (!finished && progress === sh) {
        await PM.sleep(job.total > 6 ? 1000 : 700);
        try {
          const r = await PM.api('GET', '/api/send/' + job.id, undefined, { retries: 1 });
          misses = 0; apply(r.job); if (r.job.done) return finish(r.job);
        } catch (e) {
          if (e.status === 404) { sh.dismissable = true; sh.setFooter('<button class="btn soft" data-act="closeSheet">Close</button>', false); const sub = $('#pgSub', sh.body); if (sub) sub.textContent = 'Lost track of this send. Check your chats before sending again.'; return; }
          if (++misses > 40) { sh.dismissable = true; sh.setFooter('<button class="btn soft" data-act="closeSheet">Close</button>', false); return; }
        }
      }
    })();
  }

  /* ---------- keyboard: hide bars while typing ---------- */
  document.addEventListener('focusin', (e) => { if (e.target.matches('input,textarea,[contenteditable=true]')) document.body.classList.add('kb'); });
  document.addEventListener('focusout', () => setTimeout(() => { const a = document.activeElement; if (!a || !a.matches('input,textarea,[contenteditable=true]')) document.body.classList.remove('kb'); }, 120));

  /* ---------- top avatar ---------- */
  function paintUser() {
    const u = S.user, b = $('#topUser'); if (!u || !b) return;
    b.innerHTML = PM.avatar(PM.mods.profile.name(u), u.id, { photo: u.photo_url });
    b.onclick = () => PM.go('profile');
  }

  /* ---------- boot ---------- */
  async function boot() {
    try { if (tg) { tg.ready(); tg.expand(); tg.disableVerticalSwipes && tg.disableVerticalSwipes(); } } catch (_) {}
    applyTheme(); applyInsets();
    if (tg && tg.onEvent) {
      tg.onEvent('themeChanged', applyTheme);
      ['safeAreaChanged', 'contentSafeAreaChanged'].forEach((e) => tg.onEvent(e, applyInsets));
      tg.onEvent('backButtonClicked', () => { if (PM.sheetOpen()) PM.closeSheet(); else PM.go('compose'); });
    }
    buildNav(); PM.setSync('saved');
    if (!PM.hasAuth()) return PM.fatal('Open from Telegram', 'This app works inside Telegram. Open it from the bot\'s menu button.', { act: 'closeApp', label: 'Close' });
    let st;
    try { st = await PM.api('GET', '/api/state', undefined, { retries: 4 }); }
    catch (e) { if (e.status === 401) return; return PM.fatal('Can\'t connect', e.message || 'Check your connection and try again.', { act: 'reload', label: 'Try again' }); }
    S.user = st.user; S.chats = st.chats; S.draft = Object.assign(S.draft, st.draft); S.bot = st.bot; S.storage = st.storage; S.limits = st.limits;
    paintUser();
    D().init(); G().init(); PM.mods.saved.init(); PM.mods.profile.init();
    PM.go('compose'); paintBar();
    $('#app').hidden = false;
    requestAnimationFrame(() => { $('#boot').classList.add('out'); setTimeout(() => $('#boot').remove(), 600); });
    resumeActive(false);
    PM.mods.saved.load(true);
  }
  boot().catch((e) => { console.error(e); PM.fatal('Something went wrong', 'Please reopen the app.', { act: 'reload', label: 'Reload' }); });
})();
