/* Profile tab: Telegram identity, usage stats, storage status, default group. */
(function () {
  'use strict';
  const { S, $, esc, icon } = PM;
  const P = (PM.mods.profile = {});
  let root;
  const name = (u) => [u.first_name, u.last_name].filter(Boolean).join(' ') || (u.username ? '@' + u.username : 'Telegram user');
  P.name = name;
  const fmt = (n) => Number(n || 0).toLocaleString();

  function render() {
    const u = S.user; if (!root || !u) return;
    const def = S.chats.find((c) => c.is_default), cloud = S.storage === 'supabase';
    root.innerHTML =
      '<div class="card hero" style="--i:0"><div class="ring">' + PM.avatar(name(u), u.id, { photo: u.photo_url }) + '</div>' +
        '<h2>' + esc(name(u)) + (u.is_premium ? '<span class="prem" title="Telegram Premium">' + icon('badge-check') + '</span>' : '') + '</h2>' +
        '<div class="un">' + (u.username ? '@' + esc(u.username) : 'No username') + '</div></div>' +
      '<div class="stats">' +
        '<div class="stat" style="--i:1">' + icon('send') + '<b>' + fmt(u.posts_created) + '</b><span>Posts sent</span></div>' +
        '<div class="stat" style="--i:2">' + icon('check') + '<b>' + fmt(u.deliveries) + '</b><span>Deliveries</span></div>' +
        '<div class="stat" style="--i:3">' + icon('users-round') + '<b>' + S.chats.length + '</b><span>Groups</span></div>' +
        '<div class="stat" style="--i:4">' + icon('bookmark') + '<b>' + fmt(u.saved) + '</b><span>Saved posts</span></div></div>' +
      '<div class="card" style="--i:5"><div class="card-h">' + icon('info') + '<span>Account</span></div>' +
        '<div class="kv"><span>Default group</span><b>' + (def ? esc(def.title) : 'None yet') + '</b></div>' +
        '<div class="kv"><span>Telegram ID</span><b>' + u.id + '</b></div>' +
        '<div class="kv"><span>Plan</span><b>' + (u.is_premium ? 'Telegram Premium' : 'Standard') + '</b></div>' +
        '<div class="kv"><span>Sync</span><b><span class="pill' + (cloud ? '' : ' warn') + '">' + icon(cloud ? 'cloud-check' : 'cloud-off') + (cloud ? 'Cloud' : 'Temporary') + '</span></b></div>' +
        (cloud ? '' : '<p class="hint" style="margin:8px 0 0">Cloud storage isn\'t connected, so drafts and groups reset when the server restarts.</p>') + '</div>' +
      '<div class="actions" style="margin-top:4px"><button class="btn soft" data-act="goGroupsTab">' + icon('users-round') + 'Manage groups</button><button class="btn soft" data-act="closeApp">' + icon('x') + 'Close</button></div>';
  }
  P.init = () => { root = $('#view-profile'); render(); };
  PM.on('chats', render); PM.on('saved', render);
  PM.on('stats', render);
  PM.on('tab', (t) => { if (t === 'profile') render(); });
  PM.A.goGroupsTab = () => PM.go('groups');
})();
