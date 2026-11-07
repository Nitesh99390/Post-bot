/* Compose tab: editor, attachment, buttons, preview and the draft sync engine. */
(function () {
  'use strict';
  const { S, $, $$, esc, icon, toast } = PM;
  const D = (PM.mods.draft = {});

  /* ---------- Telegram-safe HTML (mirror of the server sanitizer) ---------- */
  const TAGS = { B: 'b', STRONG: 'b', I: 'i', EM: 'i', U: 'u', INS: 'u', S: 's', STRIKE: 's', DEL: 's', CODE: 'code', PRE: 'pre', 'TG-SPOILER': 'tg-spoiler', BLOCKQUOTE: 'blockquote', A: 'a' };
  const BLOCK = new Set(['DIV', 'P', 'LI', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6']);
  const x = (t) => t.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  PM.tgClean = function (html) {
    const doc = new DOMParser().parseFromString('<body>' + (html || '') + '</body>', 'text/html');
    let out = '', plain = ''; const open = [];
    const nl = () => { if (plain && !plain.endsWith('\n')) { out += '\n'; plain += '\n'; } };
    (function walk(n) {
      if (n.nodeType === 3) { const t = n.nodeValue.replace(/\u00a0/g, ' '); out += x(t); plain += t; return; }
      if (n.nodeType !== 1) return;
      const tag = n.tagName;
      if (tag === 'BR') { out += '\n'; plain += '\n'; return; }
      if (BLOCK.has(tag)) nl();
      let name = TAGS[tag], href = '';
      if (name === 'a') { href = n.getAttribute('href') || ''; if (!/^https?:\/\//i.test(href)) name = null; }
      if (name && open.includes(name)) name = null;
      if ((open.includes('pre') || open.includes('code')) && !(name === 'code' && open.includes('pre') && !open.includes('code'))) name = null;
      if (name) { out += name === 'a' ? '<a href="' + esc(href) + '">' : '<' + name + '>'; open.push(name); }
      n.childNodes.forEach(walk);
      if (name) { out += '</' + name + '>'; open.pop(); }
      if (BLOCK.has(tag)) nl();
    })(doc.body);
    for (let prev = null; prev !== out;) { prev = out; out = out.replace(/<(b|i|u|s|code|pre|tg-spoiler|blockquote)><\/\1>|<a href="[^"]*"><\/a>/g, ''); }
    return { html: out.trim(), plain: plain.trim() };
  };

  /* ---------- draft sync engine ---------- */
  let dirty = false, timer = null, inflight = null, failures = 0, lastGood = [];
  const lsKey = () => 'pm_pending_' + (S.user ? S.user.id : 0);
  const saveLocal = () => { try { localStorage.setItem(lsKey(), JSON.stringify({ text: S.draft.text, buttons: S.draft.buttons, link_preview: S.draft.link_preview })); } catch (_) {} };
  const clearLocal = () => { try { localStorage.removeItem(lsKey()); } catch (_) {} };
  D.pending = () => dirty || !!inflight;
  D.touch = () => {
    dirty = true; saveLocal(); PM.setSync('saving');
    clearTimeout(timer); timer = setTimeout(D.flush, 550);
  };
  D.adopt = (draft) => { // replace local draft with the server's (clear / load saved)
    dirty = false; clearTimeout(timer); clearLocal();
    S.draft = Object.assign({}, S.draft, draft);
    lastGood = (S.draft.buttons || []).map((b) => Object.assign({}, b));
    PM.setSync('saved');
  };
  D.recover = () => { // unsynced edits from a previous session win over the server copy
    try {
      const raw = localStorage.getItem(lsKey()); if (!raw) return;
      const p = JSON.parse(raw);
      S.draft.text = p.text || ''; S.draft.buttons = Array.isArray(p.buttons) ? p.buttons : [];
      S.draft.link_preview = p.link_preview !== false;
      dirty = true; D.flush();
    } catch (_) { clearLocal(); }
  };
  D.flush = function () {
    clearTimeout(timer);
    if (!inflight) inflight = run().finally(() => { inflight = null; });
    return inflight;
  };
  async function run() {
    while (dirty) {
      dirty = false;
      const snap = { text: S.draft.text, buttons: S.draft.buttons.map((b) => Object.assign({}, b)), link_preview: S.draft.link_preview };
      try {
        const r = await PM.api('PUT', '/api/draft', snap, { retries: 2 });
        Object.assign(S.draft, { chars: r.draft.chars, splits: r.draft.splits, empty: r.draft.empty });
        lastGood = snap.buttons; failures = 0;
        if (!dirty) { clearLocal(); PM.setSync('saved'); }
        PM.emit('draft-meta');
      } catch (e) {
        if (e.status === 401) return false;
        if (e.network || e.status >= 500 || e.status === 429) {
          dirty = true; failures++;
          PM.setSync(e.network ? 'offline' : 'error');
          clearTimeout(timer); timer = setTimeout(D.flush, Math.min(1000 * Math.pow(2, failures), 10000));
          return false;
        }
        // The server refused this content (e.g. bad link). Keep the text, undo the buttons.
        if (e.code === 'buttons') { S.draft.buttons = lastGood.map((b) => Object.assign({}, b)); renderButtons(); renderPreview(); }
        toast(e.message, 'err', 4200);
        if (!dirty) { PM.setSync('error', 'Not saved'); saveLocal(); }
        return false;
      }
    }
    return true;
  }
  PM.on('online', () => { if (dirty) D.flush(); });
  document.addEventListener('visibilitychange', () => { if (document.hidden && dirty) D.flush(); });
  window.addEventListener('pagehide', () => { if (dirty) D.flush(); });

  /* ---------- helpers ---------- */
  const COLORS = ['blue', 'green', 'red', 'plain'];
  const CNAME = { blue: 'Blue', green: 'Green', red: 'Red', plain: 'Plain' };
  const MEDIA = { photo: ['image', 'Photo'], animation: ['film', 'GIF'], video: ['film', 'Video'], audio: ['music', 'Audio'], voice: ['music', 'Voice'], document: ['file', 'File'], sticker: ['image', 'Sticker'], video_note: ['film', 'Video note'] };
  const fmtLabel = (u) => String(u || '').replace(/^https?:\/\/(www\.)?/, '').replace(/\/$/, '');
  function normLink(raw) {
    const v = String(raw || '').trim();
    if (/^@[A-Za-z0-9_]{4,32}$/.test(v)) return 'https://t.me/' + v.slice(1);
    if (/\s/.test(v) || !v) return null;
    const u = /^https?:\/\//i.test(v) ? v : 'https://' + v;
    try { const p = new URL(u); return /^https?:$/.test(p.protocol) && p.hostname.includes('.') && !p.username ? p.href.replace(/\/$/, p.pathname === '/' && !p.search && !p.hash ? '' : '/') : null; } catch (_) { return null; }
  }

  /* ---------- skeleton ---------- */
  let editor, fileInput, uploading = null, formColor = 'blue', formOpen = false, savedRange = null;
  function build() {
    $('#view-compose').innerHTML =
      '<div class="card" style="--i:0"><div class="card-h">' + icon('square-pen') + '<span>Message</span><span class="sp"></span></div>' +
        '<div class="tools" id="tools">' +
          '<button class="tool" data-fmt="bold" aria-label="Bold">' + icon('bold') + '</button>' +
          '<button class="tool" data-fmt="italic" aria-label="Italic">' + icon('italic') + '</button>' +
          '<button class="tool" data-fmt="underline" aria-label="Underline">' + icon('underline') + '</button>' +
          '<button class="tool" data-fmt="strikeThrough" aria-label="Strikethrough">' + icon('strikethrough') + '</button>' +
          '<button class="tool" data-wrap="code" aria-label="Code">' + icon('code') + '</button>' +
          '<button class="tool" data-wrap="tg-spoiler" aria-label="Spoiler">' + icon('eye-off') + '</button>' +
          '<button class="tool" data-wrap="blockquote" aria-label="Quote">' + icon('quote') + '</button>' +
          '<button class="tool" data-act="linkSel" aria-label="Link">' + icon('link') + '</button>' +
        '</div>' +
        '<div class="editor" id="editor" contenteditable="true" role="textbox" aria-multiline="true" data-ph="Write your post here…" spellcheck="true"></div>' +
        '<div class="count" id="count"></div>' +
        '<div id="attachBox"></div>' +
      '</div>' +
      '<div class="card" style="--i:1"><div class="card-h">' + icon('link') + '<span>Buttons</span><span class="sp"></span><span id="btnCount" class="hint"></span></div>' +
        '<div id="btnList"></div><div id="btnForm"></div></div>' +
      '<div class="card" style="--i:2"><div class="switch-row"><div class="t">Link preview<span>Show a card for the first link in your text</span></div>' +
        '<button class="sw" id="swPrev" role="switch" aria-label="Link preview" data-act="togglePreview"></button></div></div>' +
      '<div class="card" style="--i:3"><div class="card-h">' + icon('send') + '<span>Preview</span><span class="sp"></span>' +
        '<button class="icon-btn danger" data-act="clearDraft" aria-label="Clear draft">' + icon('trash-2') + '</button></div>' +
        '<div class="bubble-wrap" id="bubble"></div></div>' +
      '<input type="file" id="file" hidden>';
    editor = $('#editor'); fileInput = $('#file');
    editor.addEventListener('input', onInput);
    editor.addEventListener('paste', (e) => {
      e.preventDefault();
      const t = (e.clipboardData || window.clipboardData).getData('text/plain');
      document.execCommand('insertText', false, t);
    });
    editor.addEventListener('drop', (e) => e.preventDefault());
    $('#tools').addEventListener('pointerdown', (e) => { if (e.target.closest('.tool')) e.preventDefault(); });
    $('#tools').addEventListener('click', (e) => {
      const b = e.target.closest('.tool'); if (!b) return;
      PM.haptic('light');
      if (b.dataset.fmt) { editor.focus(); document.execCommand(b.dataset.fmt, false, null); onInput(); }
      else if (b.dataset.wrap) wrap(b.dataset.wrap);
    });
    document.addEventListener('selectionchange', toolState);
    fileInput.addEventListener('change', onFile);
    $('#bubble').addEventListener('click', (e) => { if (e.target.closest('a')) e.preventDefault(); });
  }

  function toolState() {
    if (!editor || document.activeElement !== editor) return;
    $$('.tool[data-fmt]').forEach((b) => { let on = false; try { on = document.queryCommandState(b.dataset.fmt); } catch (_) {} b.classList.toggle('on', on); });
  }

  function onInput() {
    const c = PM.tgClean(editor.innerHTML);
    S.draft.text = c.html; S.draft._plain = c.plain.length;
    renderCount(); renderPreview(); PM.emit('draft-meta');
    D.touch();
  }

  function wrap(tag, attrs, range) {
    const sel = getSelection();
    let r = range || (sel.rangeCount ? sel.getRangeAt(0) : null);
    if (!r || !editor.contains(r.commonAncestorContainer)) { toast('Select some text first', 'info'); return; }
    if (r.collapsed) { toast('Select some text first', 'info'); return; }
    const el = document.createElement(tag);
    Object.keys(attrs || {}).forEach((k) => el.setAttribute(k, attrs[k]));
    el.appendChild(r.extractContents()); r.insertNode(el);
    sel.removeAllRanges(); const nr = document.createRange(); nr.selectNodeContents(el); sel.addRange(nr);
    onInput();
  }

  PM.A.linkSel = () => {
    const sel = getSelection();
    savedRange = sel.rangeCount && editor.contains(sel.getRangeAt(0).commonAncestorContainer) ? sel.getRangeAt(0).cloneRange() : null;
    if (!savedRange || savedRange.collapsed) { toast('Select the text to link first', 'info'); return; }
    const sh = PM.sheet({
      body: '<h2>Add link</h2><p>The selected text will open this address.</p><input class="input" id="lnk" inputmode="url" autocapitalize="off" autocomplete="off" placeholder="https://example.com or @channel"><div class="err-text" id="lnkErr" style="margin-top:8px"></div>',
      footer: '<button class="btn primary block" data-act="applyLink">Apply link</button>',
    });
    PM.A.applyLink = () => {
      const url = normLink($('#lnk').value);
      if (!url) { $('#lnkErr').textContent = 'Enter a valid link, like example.com or @channel.'; PM.haptic('error'); return; }
      sh.close(); editor.focus();
      wrap('a', { href: url }, savedRange);
    };
    setTimeout(() => { const i = $('#lnk'); if (i) i.focus(); }, 380);
  };

  /* ---------- count / sync of editor with state ---------- */
  function renderCount() {
    const d = S.draft, n = d._plain != null ? d._plain : (d.chars || 0);
    const max = S.limits.text, cap = S.limits.caption;
    let cls = '', hint = '';
    if (n > max) { cls = 'bad'; hint = 'Too long for Telegram'; }
    else if (d.media_type && n > cap) { cls = 'warn'; hint = 'Sent as 2 messages (caption limit ' + cap + ')'; }
    else if (n > max * 0.9) cls = 'warn';
    $('#count').innerHTML = '<span class="' + (cls === 'bad' ? 'err-text' : '') + '">' + esc(hint) + '</span><span><b class="' + cls + '">' + n + '</b> / ' + max + '</span>';
  }

  /* ---------- attachment ---------- */
  function renderAttach() {
    const d = S.draft, box = $('#attachBox'); if (!box) return;
    if (uploading) {
      box.innerHTML = '<div class="attach"><div class="attach-ic">' + icon('loader-circle', 'spin-i') + '</div><div class="attach-t"><b>Uploading…</b><span>' + esc(uploading.name) + '</span><div class="progress"><i style="width:' + Math.round(uploading.p * 100) + '%"></i></div></div></div>';
      const ic = $('.spin-i', box); if (ic) ic.style.animation = 'spin .9s linear infinite';
      return;
    }
    if (d.media_type) {
      const m = MEDIA[d.media_type] || MEDIA.document;
      const thumb = d.media_type === 'photo' && S.photoUrl ? '<img src="' + esc(S.photoUrl) + '" alt="">' : icon(m[0]);
      box.innerHTML = '<div class="attach"><div class="attach-ic">' + thumb + '</div><div class="attach-t"><b>' + esc(d.media_name || m[1]) + '</b><span>' + m[1] + ' attached</span></div>' +
        '<button class="icon-btn" data-act="pickFile" aria-label="Replace">' + icon('refresh-cw') + '</button>' +
        '<button class="icon-btn danger" data-act="removeMedia" aria-label="Remove">' + icon('x') + '</button></div>';
    } else {
      box.innerHTML = '<button class="drop" data-act="pickFile">' + icon('paperclip') + '<span>Attach photo, video or file</span></button>';
    }
  }
  PM.A.pickFile = () => { if (!uploading) fileInput.click(); };
  async function onFile() {
    const f = fileInput.files && fileInput.files[0]; fileInput.value = '';
    if (!f) return;
    const max = S.limits.upload_mb * 1024 * 1024;
    if (!f.size) return toast('That file is empty.', 'err');
    if (f.size > max) return toast('Files can be up to ' + S.limits.upload_mb + ' MB.', 'err');
    uploading = { name: f.name, p: 0 }; renderAttach(); PM.emit('draft-meta');
    PM.setSync('saving', 'Uploading');
    try {
      await D.flush();
      const r = await PM.upload(f, (p) => { uploading.p = p; const i = $('#attachBox .progress i'); if (i) i.style.width = Math.round(p * 100) + '%'; });
      Object.assign(S.draft, { media_type: r.draft.media_type, media_name: r.draft.media_name, splits: r.draft.splits, empty: false });
      uploading = null; PM.setSync(D.pending() ? 'saving' : 'saved');
      await loadPhoto(); toast('Attached', 'ok', 1800);
    } catch (e) {
      uploading = null; PM.setSync(D.pending() ? 'saving' : (e.network ? 'offline' : 'saved'));
      toast(e.message, 'err', 4500);
    }
    renderAttach(); renderCount(); renderPreview(); PM.emit('draft-meta');
  }
  PM.A.removeMedia = async () => {
    const r = await PM.api('DELETE', '/api/media', undefined, { retries: 1 });
    Object.assign(S.draft, { media_type: null, media_name: '', splits: r.draft.splits, empty: r.draft.empty });
    freePhoto(); renderAttach(); renderCount(); renderPreview(); PM.emit('draft-meta');
  };
  function freePhoto() { if (S.photoUrl) URL.revokeObjectURL(S.photoUrl); S.photoUrl = null; }
  async function loadPhoto() {
    freePhoto();
    if (S.draft.media_type !== 'photo') return;
    try {
      const res = await fetch('/api/media', { headers: { 'X-Init-Data': PM.tg ? PM.tg.initData : '' }, cache: 'no-store' });
      if (res.ok) S.photoUrl = URL.createObjectURL(await res.blob());
    } catch (_) {}
  }

  /* ---------- buttons ---------- */
  function renderButtons() {
    const list = $('#btnList'); if (!list) return;
    const bs = S.draft.buttons, max = S.limits.buttons;
    $('#btnCount').textContent = bs.length + ' / ' + max;
    list.innerHTML = bs.map((b, i) =>
      '<div class="btn-row"><button class="dot c-' + b.color + '" data-act="cycleColor" data-i="' + i + '" aria-label="Colour: ' + CNAME[b.color] + '"></button>' +
      '<div class="t"><b>' + esc(b.text) + '</b><span>' + esc(fmtLabel(b.url)) + '</span></div>' +
      '<button class="icon-btn danger" data-act="delButton" data-i="' + i + '" aria-label="Remove">' + icon('trash-2') + '</button></div>').join('');
    const f = $('#btnForm');
    if (bs.length >= max) { f.innerHTML = '<div class="hint">Button limit reached.</div>'; return; }
    if (!formOpen) { f.innerHTML = '<button class="drop" data-act="openForm">' + icon('plus') + '<span>Add link button</span></button>'; return; }
    if (!$('#bLabel')) {
      f.innerHTML = '<div class="add-btn"><input class="input" id="bLabel" maxlength="64" placeholder="Button text, e.g. Join channel" autocomplete="off">' +
        '<input class="input" id="bUrl" inputmode="url" autocapitalize="off" autocomplete="off" placeholder="Link: https://… or @channel">' +
        '<div class="chips" id="bColors">' + COLORS.map((c) => '<button class="chip' + (c === formColor ? ' on' : '') + '" data-act="pickColor" data-c="' + c + '"><i class="c-' + c + '"></i>' + CNAME[c] + '</button>').join('') + '</div>' +
        '<div class="err-text" id="bErr"></div>' +
        '<div class="actions"><button class="btn soft" data-act="closeForm">Cancel</button><button class="btn primary" data-act="addButton">Add</button></div></div>';
    }
  }
  PM.A.openForm = () => { formOpen = true; renderButtons(); setTimeout(() => { const i = $('#bLabel'); if (i) i.focus(); }, 60); };
  PM.A.closeForm = () => { formOpen = false; renderButtons(); };
  PM.A.pickColor = (el) => { formColor = el.dataset.c; $$('#bColors .chip').forEach((c) => c.classList.toggle('on', c.dataset.c === formColor)); PM.haptic('select'); };
  PM.A.addButton = () => {
    const text = $('#bLabel').value.replace(/\s+/g, ' ').trim(), url = normLink($('#bUrl').value), err = $('#bErr');
    if (!text) { err.textContent = 'Give the button a name.'; PM.haptic('error'); return; }
    if (!url) { err.textContent = 'Enter a valid link, like example.com or @channel.'; PM.haptic('error'); return; }
    if (S.draft.buttons.length >= S.limits.buttons) return;
    S.draft.buttons.push({ text, url, color: formColor });
    formOpen = false; PM.haptic('success'); D.touch(); renderButtons(); renderPreview(); PM.emit('draft-meta');
  };
  PM.A.delButton = (el) => { S.draft.buttons.splice(+el.dataset.i, 1); PM.haptic('light'); D.touch(); renderButtons(); renderPreview(); PM.emit('draft-meta'); };
  PM.A.cycleColor = (el) => {
    const b = S.draft.buttons[+el.dataset.i]; if (!b) return;
    b.color = COLORS[(COLORS.indexOf(b.color) + 1) % COLORS.length];
    PM.haptic('select'); D.touch(); renderButtons(); renderPreview();
  };
  PM.A.togglePreview = () => { S.draft.link_preview = !S.draft.link_preview; PM.haptic('select'); D.touch(); $('#swPrev').classList.toggle('on', S.draft.link_preview); };

  /* ---------- preview ---------- */
  const BTN_BG = { blue: '#3390ec', green: '#2fb344', red: '#e5484d', plain: 'rgba(120,130,160,.45)' };
  function renderPreview() {
    const d = S.draft, el = $('#bubble'); if (!el) return;
    const html = PM.tgClean(d.text).html;
    let media = '';
    if (d.media_type) {
      const m = MEDIA[d.media_type] || MEDIA.document;
      media = '<div class="media">' + (d.media_type === 'photo' && S.photoUrl ? '<img src="' + esc(S.photoUrl) + '" alt="">' : icon(m[0])) + '</div>';
    }
    const empty = !html && !d.media_type;
    el.innerHTML = '<div class="bubble">' + media + (html ? html : (d.media_type ? '' : '<span class="empty">Your post will appear here</span>')) + '</div>' +
      (d.buttons.length ? '<div class="pbtns">' + d.buttons.map((b) => '<span class="pbtn" style="background:' + BTN_BG[b.color] + '">' + esc(b.text) + '</span>').join('') + '</div>' : '');
    el.style.opacity = empty ? '.6' : '1';
  }

  PM.A.clearDraft = () => {
    if (S.draft.empty && !S.draft.text && !S.draft.media_type && !S.draft.buttons.length) return toast('Nothing to clear', 'info', 1600);
    const sh = PM.sheet({
      body: '<h2>Clear this draft?</h2><p>The text, attachment and buttons will be removed. Saved posts are not affected.</p>',
      footer: '<button class="btn bad" data-act="clearYes">Clear draft</button><button class="btn soft" data-act="closeSheet">Keep</button>', two: true,
    });
    PM.A.clearYes = async () => { sh.close(); await D.clear(); toast('Draft cleared', 'ok', 1600); };
  };
  D.clear = async function () {
    const r = await PM.api('DELETE', '/api/draft', undefined, { retries: 2 });
    D.adopt({ text: '', buttons: [], media_type: null, media_name: '', empty: true, chars: 0, splits: false });
    freePhoto(); D.paint(); return r;
  };

  /* ---------- public paint ---------- */
  D.paint = function () {
    const d = S.draft;
    if (document.activeElement !== editor || !editor.textContent) editor.innerHTML = PM.tgClean(d.text).html.replace(/\n/g, '\n');
    d._plain = PM.tgClean(d.text).plain.length;
    $('#swPrev').classList.toggle('on', d.link_preview !== false);
    renderCount(); renderAttach(); renderButtons(); renderPreview(); PM.emit('draft-meta');
  };
  D.setText = (html) => { editor.innerHTML = PM.tgClean(html).html; };
  D.init = async function () {
    build();
    D.adopt(S.draft);
    D.paint();
    if (S.draft.media_type === 'photo') loadPhoto().then(() => { renderAttach(); renderPreview(); });
    D.recover();
    if (dirty) { editor.innerHTML = PM.tgClean(S.draft.text).html; D.paint(); }
  };
  D.isEmpty = () => { const d = S.draft; return !(d.text && d.text.trim()) && !d.media_type && !(d.buttons && d.buttons.length); };
  D.over = () => (S.draft._plain != null ? S.draft._plain : S.draft.chars || 0) > S.limits.text;
  D.busyUpload = () => !!uploading;
  D.reloadPhoto = async () => { await loadPhoto(); renderAttach(); renderPreview(); };
})();
