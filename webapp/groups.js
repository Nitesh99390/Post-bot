/* Groups tab: linked groups/channels, one default, any number selected, add flow. */
(function () {
  'use strict';
  const { S, $, $$, esc, icon, toast } = PM;
  const G = (PM.mods.groups = {});
  let root, firstPaint = true, selTimer = null, selBusy = false, selDirty = false, pollTimer = null, addSheet = null;

  const typeName = (t) => (t === 'channel' ? 'Channel' : t === 'supergroup' ? 'Supergroup' : 'Group');
  const find = (id) => S.chats.find((c) => c.chat_id === id);
  G.selected = () => S.chats.filter((c) => c.selected && c.can_post);
  G.ids = () => G.selected().map((c) => c.chat_id);
  G.setChats = (list) => { S.chats = Array.isArray(list) ? list : []; PM.emit('chats'); };

  /* ---------- render ---------- */
  function sub(c) {
    if (!c.can_post) return '<span class="warn">Bot can\'t post here. Check admin rights</span>';
    return '<span>' + esc(c.username ? '@' + c.username : typeName(c.type)) + (c.username ? ' · ' + typeName(c.type) : '') + '</span>';
  }
  function rowHtml(c, i) {
    return '<div class="row' + (c.selected && c.can_post ? ' sel' : '') + (c.can_post ? '' : ' off') + '" role="button" tabindex="0" data-act="toggleChat" data-id="' + c.chat_id + '" style="--i:' + Math.min(i, 10) + '">' +
      PM.avatar(c.title, c.chat_id) +
      '<div class="grow"><b><em>' + esc(c.title) + '</em>' + (c.is_default ? '<span class="tag def">Default</span>' : '') + '</b>' + sub(c) + '</div>' +
      '<div class="check">' + icon('check') + '</div>' +
      '<button class="more" data-act="chatMenu" data-id="' + c.chat_id + '" aria-label="Options for ' + esc(c.title) + '">' + icon('chevron-right') + '</button></div>';
  }
  function render() {
    if (!root) return;
    const list = S.chats, n = G.selected().length;
    let h = '<div class="sec-title"><h1>Groups</h1><div style="display:flex;gap:6px">' +
      '<button class="icon-btn" data-act="refreshChats" id="refreshBtn" aria-label="Refresh">' + icon('refresh-cw') + '</button>' +
      '<button class="icon-btn" data-act="addChat" aria-label="Add group" style="background:var(--chip);color:var(--a1)">' + icon('plus') + '</button></div></div>';
    if (!list.length) {
      h += '<div class="empty-state"><div class="empty-art">' + icon('users-round') + '</div><h2>No groups yet</h2>' +
        '<p>Add the bot as an admin to any group or channel. It will show up here on its own.</p>' +
        '<button class="btn primary block" data-act="addChat">' + icon('plus') + 'Add group or channel</button></div>';
    } else {
      h += '<div class="hint" style="margin:-4px 2px 12px" id="selHint"></div>' +
        '<div class="quick"><button class="chip" data-act="selAll">All</button><button class="chip" data-act="selDefault">Default only</button><button class="chip" data-act="selNone">None</button></div>' +
        '<div id="chatList">' + list.map(rowHtml).join('') + '</div>';
    }
    root.className = 'view' + (root.classList.contains('on') ? ' on' : '') + (firstPaint ? '' : ' noanim');
    root.innerHTML = h;
    firstPaint = false;
    hint();
  }
  function hint() {
    const el = $('#selHint', root); if (!el) return;
    const n = G.selected().length, total = S.chats.length;
    el.innerHTML = n ? '<b style="color:var(--tx)">' + n + '</b> of ' + total + ' selected. Your post goes to these.' : 'Tap a group to select where your post goes.';
  }
  function paintSel() { // in-place, so rows don't re-animate
    $$('#chatList .row', root).forEach((el) => {
      const c = find(+el.dataset.id); if (!c) return;
      el.classList.toggle('sel', !!(c.selected && c.can_post));
    });
    hint(); PM.emit('chats');
  }

  /* ---------- selection sync (latest wins, one request at a time) ---------- */
  function queueSel() { selDirty = true; clearTimeout(selTimer); selTimer = setTimeout(pushSel, 350); }
  async function pushSel() {
    if (selBusy) return; selBusy = true;
    try {
      while (selDirty) {
        selDirty = false;
        const ids = S.chats.filter((c) => c.selected).map((c) => c.chat_id);
        try { await PM.api('PUT', '/api/chats/selection', { chat_ids: ids }, { retries: 2 }); }
        catch (e) {
          if (e.network) { selDirty = true; await PM.sleep(2000); continue; }
          toast(e.message, 'err'); await G.reload(true); return;
        }
      }
    } finally { selBusy = false; }
  }
  G.flush = async () => { clearTimeout(selTimer); if (selDirty) await pushSel(); while (selBusy) await PM.sleep(30); };
  document.addEventListener('visibilitychange', () => { if (document.hidden && selDirty) G.flush(); });

  PM.A.toggleChat = (el) => {
    const c = find(+el.dataset.id); if (!c) return;
    if (!c.can_post && !c.selected) { PM.haptic('warning'); return toast('Make the bot an admin there first', 'warn'); }
    c.selected = !c.selected; PM.haptic('select'); paintSel(); queueSel();
  };
  const setAll = (fn) => { S.chats.forEach((c) => { c.selected = fn(c); }); PM.haptic('light'); paintSel(); queueSel(); };
  PM.A.selAll = () => setAll((c) => c.can_post);
  PM.A.selNone = () => setAll(() => false);
  PM.A.selDefault = () => { const d = S.chats.find((c) => c.is_default && c.can_post); if (!d) return toast('No default group with posting rights', 'warn'); setAll((c) => c === d); };

  /* ---------- reload / refresh ---------- */
  G.reload = async function (quiet) {
    try {
      const r = await PM.api('GET', '/api/chats');
      if (selDirty || selBusy) return;
      G.setChats(r.chats); render();
    } catch (e) { if (!quiet) toast(e.message, 'err'); }
  };
  PM.A.refreshChats = async () => {
    const b = $('#refreshBtn'); if (b) b.firstElementChild.style.animation = 'spin .8s linear infinite';
    try {
      await G.flush();
      const r = await PM.api('POST', '/api/chats/refresh', {}, { timeout: 45000 });
      G.setChats(r.chats); render(); toast('Groups updated', 'ok', 1500);
    } finally { const b2 = $('#refreshBtn'); if (b2) b2.firstElementChild.style.animation = ''; }
  };

  /* ---------- per-chat menu ---------- */
  PM.A.chatMenu = (el) => {
    const c = find(+el.dataset.id); if (!c) return;
    const link = c.username ? 'https://t.me/' + c.username : '';
    const sh = PM.sheet({
      body: '<div style="display:flex;gap:12px;align-items:center;margin-bottom:6px">' + PM.avatar(c.title, c.chat_id) +
        '<div style="min-width:0"><h2 style="margin:0;font-size:20px">' + esc(c.title) + '</h2><div class="hint">' + typeName(c.type) + (c.username ? ' · @' + esc(c.username) : '') + '</div></div></div>' +
        (c.can_post ? '' : '<p class="err-text" style="margin:8px 0 0">The bot can\'t post here. Give it the "Post messages" right, then tap Refresh.</p>') +
        '<div class="menu-list">' +
        (c.is_default ? '<div class="pill" style="justify-self:start">' + icon('star') + 'This is your default group</div>' :
          '<button class="btn soft" data-act="makeDefault" data-id="' + c.chat_id + '">' + icon('star') + 'Make default</button>') +
        (link ? '<button class="btn soft" data-act="openUrl" data-url="' + esc(link) + '">' + icon('external-link') + 'Open chat</button>' : '') +
        '<button class="btn bad" data-act="askRemove" data-id="' + c.chat_id + '">' + icon('trash-2') + 'Remove from list</button></div>',
    });
    G._menu = sh;
  };
  PM.A.makeDefault = async (el) => {
    const id = +el.dataset.id;
    if (G._menu) G._menu.close();
    await G.flush();
    const r = await PM.api('PUT', '/api/chats/default', { chat_id: id });
    G.setChats(r.chats); render(); PM.haptic('success'); toast('Default group updated', 'ok', 1800);
  };
  PM.A.askRemove = (el) => {
    const c = find(+el.dataset.id); if (!c || !G._menu) return;
    G._menu.setBody('<h2>Remove "' + esc(c.title) + '"?</h2><p>It only leaves this list. The bot stays in the chat and you can add it back any time.</p>');
    G._menu.setFooter('<button class="btn soft" data-act="closeSheet">Cancel</button><button class="btn bad" data-act="doRemove" data-id="' + c.chat_id + '">Remove</button>', true);
  };
  PM.A.doRemove = async (el) => {
    const id = +el.dataset.id;
    el.disabled = true;
    await G.flush();
    const r = await PM.api('DELETE', '/api/chats/' + id);
    if (G._menu) G._menu.close();
    G.setChats(r.chats); render(); toast('Removed', 'ok', 1500);
  };

  /* ---------- add flow ---------- */
  const RIGHTS = 'post_messages+edit_messages+delete_messages';
  function deepLink(kind) {
    return 'https://t.me/' + S.bot + (kind === 'channel' ? '?startchannel=pm&admin=' : '?startgroup=pm&admin=') + RIGHTS;
  }
  PM.A.addChat = () => {
    const known = new Set(S.chats.map((c) => c.chat_id));
    addSheet = PM.sheet({
      body: '<h2>Add a group or channel</h2><p>The bot posts for you, so it needs to be an admin there.</p>' +
        '<ol class="steps"><li><span>Tap a button below and <b>choose your chat</b></span></li><li><span>Confirm <b>admin rights</b> for the bot (Post messages)</span></li><li><span>Come back here. It <b>appears automatically</b></span></li></ol>' +
        (S.bot ? '<div class="actions" style="margin-top:16px"><button class="btn primary" data-act="openUrl" data-url="' + esc(deepLink('group')) + '">' + icon('users-round') + 'Group</button>' +
          '<button class="btn primary" data-act="openUrl" data-url="' + esc(deepLink('channel')) + '">' + icon('megaphone') + 'Channel</button></div>' : '') +
        '<div class="divider">or add by username</div>' +
        '<div class="field-row"><input class="input" id="refIn" placeholder="@channel or t.me/link" autocapitalize="off" autocomplete="off" inputmode="url"><button class="btn soft" data-act="addByRef" id="refBtn">Add</button></div>' +
        '<div class="err-text" id="refErr" style="margin-top:8px"></div>' +
        '<div class="hint" style="margin-top:10px"><span class="pulse-dot"></span> Waiting for the bot to be added…</div>',
      footer: '<button class="btn ghost" data-act="closeSheet">Done</button>',
      onClose: () => { clearInterval(pollTimer); pollTimer = null; addSheet = null; },
    });
    clearInterval(pollTimer);
    pollTimer = setInterval(async () => {
      if (document.hidden) return;
      try {
        const r = await PM.api('GET', '/api/chats', undefined, { retries: 0 });
        const fresh = r.chats.filter((c) => !known.has(c.chat_id));
        if (fresh.length) {
          fresh.forEach((c) => known.add(c.chat_id));
          if (!selDirty && !selBusy) { G.setChats(r.chats); render(); }
          PM.haptic('success'); toast('Added ' + fresh[0].title + (fresh.length > 1 ? ' +' + (fresh.length - 1) : ''), 'ok');
          if (addSheet) addSheet.close();
        }
      } catch (_) {}
    }, 2500);
  };
  PM.A.addByRef = async (el) => {
    const inp = $('#refIn'), err = $('#refErr'); if (!inp) return;
    const ref = inp.value.trim();
    err.textContent = '';
    if (!ref) { err.textContent = 'Enter @username, a t.me link or the chat id.'; return PM.haptic('error'); }
    el.disabled = true;
    try {
      await G.flush();
      const r = await PM.api('POST', '/api/chats', { ref }, { timeout: 30000 });
      G.setChats(r.chats); render();
      const c = find(r.chat_id);
      PM.haptic('success'); toast(r.result === 'exists' ? 'Already in your list' : 'Added ' + (c ? c.title : 'chat'), 'ok');
      if (addSheet) addSheet.close();
    } catch (e) { err.textContent = e.message; PM.haptic('error'); }
    finally { el.disabled = false; }
  };

  /* ---------- lifecycle ---------- */
  G.init = () => { root = $('#view-groups'); render(); };
  PM.on('tab', (t) => { if (t === 'groups') G.reload(true); });
  document.addEventListener('visibilitychange', () => { if (!document.hidden && S.tab === 'groups') G.reload(true); });
})();
