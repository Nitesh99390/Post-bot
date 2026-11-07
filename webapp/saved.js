/* Saved tab: keep reusable posts, load one back into the editor, delete. */
(function () {
  'use strict';
  const { S, $, esc, icon, toast } = PM;
  const V = (PM.mods.saved = {});
  let root, loading = false, firstPaint = true;
  const MEDIA = { photo: 'image', animation: 'film', video: 'film', audio: 'music', voice: 'music', document: 'file' };

  function ago(iso) {
    const t = Date.parse(iso); if (!t) return '';
    const m = Math.max(0, Math.round((Date.now() - t) / 60000));
    if (m < 1) return 'just now'; if (m < 60) return m + ' min ago';
    if (m < 1440) return Math.round(m / 60) + ' h ago';
    return Math.round(m / 1440) + ' d ago';
  }
  function card(p, i) {
    return '<div class="card saved-card" style="--i:' + Math.min(i, 8) + '">' +
      '<div class="attach-ic">' + icon(MEDIA[p.media_type] || 'type') + '</div>' +
      '<div class="grow"><b>' + esc(p.name) + '</b><p>' + (p.preview ? esc(p.preview) : '<i>No text</i>') + '</p>' +
      '<div class="meta"><span>' + p.chars + ' chars</span>' + (p.buttons ? '<span>' + PM.plural(p.buttons, 'button', 'buttons') + '</span>' : '') + (p.media_type ? '<span>' + esc(p.media_type) + '</span>' : '') + '<span>' + esc(ago(p.updated_at)) + '</span></div></div>' +
      '<div style="display:grid;gap:4px"><button class="icon-btn" data-act="loadSaved" data-id="' + p.id + '" aria-label="Open in editor" style="background:var(--chip);color:var(--a1)">' + icon('folder-open') + '</button>' +
      '<button class="icon-btn danger" data-act="askDelSaved" data-id="' + p.id + '" aria-label="Delete">' + icon('trash-2') + '</button></div></div>';
  }
  function render() {
    if (!root) return;
    const list = S.saved;
    let h = '<div class="sec-title"><h1>Saved</h1><button class="icon-btn" data-act="saveDraft" aria-label="Save current draft" style="background:var(--chip);color:var(--a1)">' + icon('save') + '</button></div>';
    if (list == null) h += '<div class="skel"></div><div class="skel"></div><div class="skel"></div>';
    else if (!list.length) {
      h += '<div class="empty-state"><div class="empty-art">' + icon('bookmark') + '</div><h2>Nothing saved</h2><p>Save a post you use often, then reuse it in one tap.</p>' +
        '<button class="btn primary block" data-act="saveDraft">' + icon('save') + 'Save current draft</button></div>';
    } else h += '<div class="hint" style="margin:-4px 2px 12px">' + list.length + ' / ' + S.limits.saved + ' saved</div>' + list.map(card).join('');
    root.innerHTML = h; firstPaint = false;
  }
  V.load = async function (quiet) {
    if (loading) return; loading = true;
    try { const r = await PM.api('GET', '/api/posts'); S.saved = r.posts; if (S.user) S.user.saved = r.posts.length; render(); PM.emit('saved'); }
    catch (e) { if (!quiet) toast(e.message, 'err'); if (S.saved == null) { S.saved = []; render(); } }
    finally { loading = false; }
  };

  PM.A.saveDraft = async () => {
    const d = PM.mods.draft;
    if (d.isEmpty()) { PM.haptic('warning'); return toast('Write something first', 'warn'); }
    const sh = PM.sheet({
      body: '<h2>Save this post</h2><p>Give it a name so you can find it later.</p><input class="input" id="saveName" maxlength="60" placeholder="e.g. Weekly update" autocomplete="off">',
      footer: '<button class="btn soft" data-act="closeSheet">Cancel</button><button class="btn primary" data-act="saveYes">Save</button>', two: true,
    });
    setTimeout(() => { const i = $('#saveName'); if (i) i.focus(); }, 380);
    PM.A.saveYes = async (el) => {
      el.disabled = true;
      try {
        if (d.pending()) await d.flush();
        if (d.pending()) throw new Error('Your draft is still syncing. Try again in a moment.');
        const r = await PM.api('POST', '/api/posts', { name: ($('#saveName').value || '').trim() });
        S.saved = r.posts; if (S.user) S.user.saved = r.posts.length; sh.close(); render(); PM.emit('saved');
        toast(r.updated ? 'Saved post updated' : 'Saved', 'ok', 1800);
      } catch (e) { el.disabled = false; toast(e.message, 'err'); }
    };
  };

  PM.A.loadSaved = async (el) => {
    const id = +el.dataset.id, d = PM.mods.draft;
    const go = async () => {
      const r = await PM.api('POST', '/api/posts/' + id + '/load', {});
      d.adopt(r.draft); d.setText(r.draft.text); d.paint();
      if (r.draft.media_type === 'photo') d.reloadPhoto();
      PM.haptic('success'); toast('Opened in editor', 'ok', 1500); PM.go('compose');
    };
    if (d.pending()) await d.flush();
    if (!d.isEmpty()) {
      const sh = PM.sheet({
        body: '<h2>Replace your draft?</h2><p>Your current draft will be replaced by this saved post. Save it first if you want to keep it.</p>',
        footer: '<button class="btn soft" data-act="closeSheet">Cancel</button><button class="btn primary" data-act="loadYes">Replace</button>', two: true,
      });
      PM.A.loadYes = async (b) => { b.disabled = true; try { await go(); sh.close(); } catch (e) { b.disabled = false; toast(e.message, 'err'); } };
    } else await go();
  };

  PM.A.askDelSaved = (el) => {
    const id = +el.dataset.id, p = (S.saved || []).find((x) => x.id === id); if (!p) return;
    const sh = PM.sheet({
      body: '<h2>Delete "' + esc(p.name) + '"?</h2><p>This can\'t be undone.</p>',
      footer: '<button class="btn soft" data-act="closeSheet">Cancel</button><button class="btn bad" data-act="delSavedYes">Delete</button>', two: true,
    });
    PM.A.delSavedYes = async (b) => {
      b.disabled = true;
      try { const r = await PM.api('DELETE', '/api/posts/' + id); S.saved = r.posts; if (S.user) S.user.saved = r.posts.length; sh.close(); render(); PM.emit('saved'); toast('Deleted', 'ok', 1400); }
      catch (e) { b.disabled = false; toast(e.message, 'err'); }
    };
  };

  V.init = () => { root = $('#view-saved'); render(); };
  PM.on('tab', (t) => { if (t === 'saved') V.load(S.saved != null); });
})();
