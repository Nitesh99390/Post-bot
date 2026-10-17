'use strict';
// Inline SVGs avoid icon-library downloads and remain crisp at any display scale.
const icons = {
  link: '<path d="M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1"/><path d="M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1"/>',
  eye: '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>',
  home: '<path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1Z"/>',
  moon: '<path d="M20.9 13A9 9 0 0 1 11 3.1 9 9 0 1 0 20.9 13Z"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5 19 19M5 19l1.5-1.5M17.5 6.5 19 5"/>',
  'arrow-up': '<path d="M6 18 18 6M6 6h12v12"/>',
  send: '<path d="m22 2-7 20-4-9-9-4Z M22 2 11 13"/>',
  copy: '<rect x="8" y="8" width="13" height="13" rx="2"/><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3"/>',
  refresh: '<path d="M20 8a8 8 0 1 0 0 8M20 3v5h-5"/>',
  code: '<path d="m8 6-6 6 6 6M16 6l6 6-6 6M14 3l-4 18"/>',
  quote: '<path d="M3 21c3 0 7-1 7-8V5H4v6h3c0 4-4 5-4 5Zm11 0c3 0 7-1 7-8V5h-6v6h3c0 4-4 5-4 5Z"/>',
  zap: '<path d="M13 2 3 14h8l-1 8 10-12h-8l1-8Z"/>',
  upload: '<path d="M12 16V4m0 0-4 4m4-4 4 4M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"/>',
  columns: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M12 4v16"/>',
  'double-check': '<path d="m2 12 4 4 9-9M10 14l2 2 9-9"/>',
  grid: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  layers: '<rect x="6" y="3" width="14" height="16" rx="3"/><path d="M16 22H6a3 3 0 0 1-3-3V8M10 8h6M10 12h6"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2"/>',
  award: '<circle cx="12" cy="8" r="5"/><path d="m8 13-2 8 6-3 6 3-2-8M10 8l1.5 1.5L14 7"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  arrow: '<path d="M4 12h15m-5-5 5 5-5 5"/>',
  chevron: '<path d="m9 5 7 7-7 7"/>',
  'chevron-down': '<path d="m6 9 6 6 6-6"/>',
  image: '<rect x="3" y="3" width="18" height="18" rx="3"/><circle cx="8" cy="8" r="1.5"/><path d="m21 15-5-5L5 21"/>',
  'image-plus': '<path d="M21 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h8M21 3v6M18 6h6M3 17l5-5 4 4 4-4 5 5"/><circle cx="8" cy="8" r="1"/>',
  cloud: '<path d="M7 18a5 5 0 1 1 .7-9.95A7 7 0 0 1 21 11a3.5 3.5 0 0 1-1 7H7Z"/>',
  shield: '<path d="M12 3 3 7v5c0 5 9 9 9 9s9-4 9-9V7l-9-4Z"/><path d="m8 12 3 3 5-6"/>',
  lock: '<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3M12 14v3"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  'check-circle': '<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
  close: '<path d="m6 6 12 12M6 18 18 6"/>',
  more: '<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
  help: '<circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 0 1 5 .5c0 1.5-2.5 1.5-2.5 3M12 16h.01"/>',
  sparkles: '<path d="m12 3 2.4 6.6L21 12l-6.6 2.4L12 21l-2.4-6.6L3 12l6.6-2.4L12 3ZM20 2v4M18 4h4"/>',
  bulb: '<path d="M9 18v-2a6 6 0 1 1 6 0v2M9 18h6M10 21h4"/>',
  search: '<circle cx="10.5" cy="10.5" r="7"/><path d="m16 16 5 5"/>',
  text: '<path d="M4 5h16M12 5v15M8 20h8"/>',
  calendar: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4M17 3v4M3 11h18"/>',
};

const BUTTON_THEMES = ['violet', 'emerald', 'amber', 'rose', 'ocean', 'sunset'];
const MAX_BUTTONS = 24;
const MAX_COLS = 3;

const BUTTON_PRESETS = {
  channel: [
    { name: 'Join Official Channel', url: 'https://t.me/telegram', badge: 'VIP', color: 'violet', row: 0 },
    { name: 'Open Chat Group', url: 'https://t.me/telegram', badge: 'LIVE', color: 'emerald', row: 1 },
    { name: 'Share with Friends', url: 'https://t.me/telegram', badge: 'NEW', color: 'amber', row: 1 },
  ],
  store: [
    { name: 'Claim 50% Offer Now', url: 'https://t.me/telegram', badge: 'HOT', color: 'rose', row: 0 },
    { name: 'View Catalog', url: 'https://t.me/telegram', badge: 'PRO', color: 'ocean', row: 0 },
  ],
  social: [
    { name: 'Subscribe Now', url: 'https://t.me/telegram', badge: 'TOP', color: 'violet', row: 0 },
    { name: 'Community', url: 'https://t.me/telegram', badge: 'CHAT', color: 'emerald', row: 0 },
    { name: 'Latest Updates', url: 'https://t.me/telegram', badge: 'NEWS', color: 'amber', row: 1 },
    { name: 'Support Bot', url: 'https://t.me/telegram', badge: '24/7', color: 'rose', row: 1 },
  ],
  grid: [
    { name: 'Explore Feature 1', url: 'https://t.me/telegram', badge: 'A1', color: 'violet', row: 0 },
    { name: 'Explore Feature 2', url: 'https://t.me/telegram', badge: 'A2', color: 'emerald', row: 0 },
    { name: 'Quick Guide', url: 'https://t.me/telegram', badge: 'B1', color: 'amber', row: 1 },
    { name: 'Get Started', url: 'https://t.me/telegram', badge: 'GO', color: 'rose', row: 1 },
  ],
  support: [
    { name: 'Message Admin', url: 'https://t.me/telegram', badge: 'DM', color: 'ocean', row: 0 },
    { name: 'Read FAQ', url: 'https://t.me/telegram', badge: 'HELP', color: 'sunset', row: 0 },
  ],
};

const STARTER_TEMPLATES = [
  '<b>Big Update Available!</b>\nWe just launched something special for our community.\n\n<blockquote>Tap the buttons below to explore all features in one place.</blockquote>',
  '<b>Weekend Exclusive Drop</b>\nFresh ideas, curated resources, and instant links ready for you.\n\n<i>Save this post or share it with your channel!</i>',
  '<b>Creator Spotlight</b>\nConsistency wins every time. Here are today’s top highlights and quick links:',
];

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const icon = name => `<svg viewBox="0 0 24 24" aria-hidden="true">${icons[name] || icons.layers}</svg>`;
function hydrateIcons(root = document) {
  $$('[data-icon]', root).forEach(node => { node.innerHTML = icon(node.dataset.icon); });
}
hydrateIcons();

const tg = window.Telegram?.WebApp;
const initData = tg?.initData || '';
// Enable interactive preview mode whenever opened outside Telegram or with data-demo="true"
const demo = document.body.dataset.demo === 'true' || !initData;

const state = {
  posts: [],
  profile: null,
  leaderboard: [],
  page: 0,
  hasMore: false,
  filter: 'all',
  activePage: 'overview',
  busy: false,
  photoURL: null,
  photoCache: new Map(),
  mediaJobs: new Map(),
  ready: false,
  loading: false,
  selectedPost: null,
  submissionKey: null,
  sending: false,
  composerRows: [], // Array of arrays of button items: [[{name, url, badge, color}], ...]
  templateIndex: 0,
};

const headers = { 'X-Telegram-Init-Data': initData };
try {
  tg?.ready();
  tg?.expand();
  if (tg?.isVersionAtLeast?.('6.1')) {
    tg.setHeaderColor('#f3f4fa');
    tg.setBackgroundColor('#f3f4fa');
  }
} catch (_) { /* Older Telegram clients use safe defaults. */ }
try {
  if (initData && tg?.isVersionAtLeast?.('8.0')) tg.requestFullscreen?.();
} catch (_) { /* Expanded mode remains available on unsupported clients. */ }

function haptic() {
  try { if (tg?.isVersionAtLeast?.('6.1')) tg.HapticFeedback?.selectionChanged(); } catch (_) {}
}

const pageInfo = {
  overview: ['Your studio', 'Create. Customize buttons. Share anywhere.'],
  posts: ['Saved posts', 'Your private vault · One-tap actions inside every card.'],
  community: ['Global rank', 'Top 100 creators ranked by saved posts.'],
  profile: ['Profile', 'Your Telegram account & studio preferences.'],
};

function greetingWord() {
  const h = new Date().getHours();
  return h < 5 ? 'Good night' : h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening';
}

function navigate(page, updateHash = true) {
  if (!pageInfo[page]) page = 'overview';
  state.activePage = page;
  const [title, subtitle] = pageInfo[page];
  $('#page-title').textContent = title;
  $('#page-subtitle').textContent = subtitle;
  $('#greeting').hidden = page !== 'overview';
  $$('.page').forEach(el => { el.hidden = el.id !== `${page}-page`; });
  $$('[data-page]').forEach(el => {
    const isTarget = el.dataset.page === page;
    if (el.classList.contains('nav-item') || el.classList.contains('tab')) {
      el.classList.toggle('active', isTarget);
      if (isTarget) el.setAttribute('aria-current', 'page');
      else el.removeAttribute('aria-current');
    }
  });
  if (updateHash && location.hash !== `#${page}`) history.pushState(null, '', `#${page}`);
  window.scrollTo({ top: 0, behavior: 'auto' });
  haptic();
}

document.addEventListener('click', event => {
  // Handle card quick sub-buttons first so they don't trigger card detail modal unintentionally
  const quickCopy = event.target.closest('[data-quick-copy]');
  if (quickCopy) {
    event.stopPropagation();
    const post = state.posts.find(p => p.id === quickCopy.dataset.quickCopy);
    if (post) copyTextToClipboard(post.text, quickCopy);
    return;
  }
  const quickSend = event.target.closest('[data-quick-send]');
  if (quickSend) {
    event.stopPropagation();
    const post = state.posts.find(p => p.id === quickSend.dataset.quickSend);
    if (post) openPostDetail(post, true);
    return;
  }
  const quickRemix = event.target.closest('[data-quick-remix]');
  if (quickRemix) {
    event.stopPropagation();
    const post = state.posts.find(p => p.id === quickRemix.dataset.quickRemix);
    if (post) remixPostInStudio(post);
    return;
  }

  const presetTrigger = event.target.closest('[data-create-preset]');
  if (presetTrigger) {
    openComposer({ preset: presetTrigger.dataset.createPreset });
    return;
  }
  const modeTrigger = event.target.closest('[data-create-mode]');
  if (modeTrigger) {
    openComposer({ mode: modeTrigger.dataset.createMode });
    return;
  }
  if (event.target.closest('[data-create]')) {
    openComposer();
    return;
  }
  const nav = event.target.closest('[data-page]');
  if (nav) {
    navigate(nav.dataset.page);
    return;
  }
  if (event.target.closest('[data-help]')) {
    $('#help').showModal();
    return;
  }
  const close = event.target.closest('[data-close]');
  if (close) closeModal(close.dataset.close);
});

document.addEventListener('keydown', event => {
  const row = event.target.closest('[role="button"][data-page], [role="button"][data-create]');
  if (row && (event.key === 'Enter' || event.key === ' ')) {
    event.preventDefault();
    if (row.dataset.create !== undefined) openComposer();
    else if (row.dataset.page) navigate(row.dataset.page);
  }
});

$$('.brand').forEach(el => el.addEventListener('click', () => navigate('overview')));
window.addEventListener('hashchange', () => navigate(location.hash.slice(1), false));
navigate(location.hash.slice(1) || 'overview', false);

$('#dismiss-demo').addEventListener('click', () => { $('#demo-banner').hidden = true; });

function closeModal(id) {
  if ((id === 'composer' && state.busy) || (id === 'detail' && state.sending)) return;
  document.getElementById(id).close();
}

$$('dialog').forEach(dialog => {
  dialog.addEventListener('click', e => {
    if (e.target === dialog) {
      const r = dialog.getBoundingClientRect();
      if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) closeModal(dialog.id);
    }
  });
  dialog.addEventListener('cancel', e => {
    if ((dialog.id === 'composer' && state.busy) || (dialog.id === 'detail' && state.sending)) e.preventDefault();
  });
});

let toastTimer;
function toast(message) {
  clearTimeout(toastTimer);
  $('#toast').textContent = message;
  $('#toast').hidden = false;
  toastTimer = setTimeout(() => { $('#toast').hidden = true; }, 5000);
}

function dateLabel(value) {
  if (!value) return 'Just now';
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? 'Saved post' : d.toLocaleDateString('en-GB', { month: 'short', day: 'numeric' });
}

function initials(name) {
  return String(name || 'You').split(/\s+/).filter(Boolean).slice(0, 2).map(s => s[0]).join('').toUpperCase();
}

async function api(path, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), options.method === 'POST' ? 60000 : 25000);
  try {
    const response = await fetch(path, { ...options, headers: { ...headers, ...options.headers }, signal: controller.signal });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || `Unable to complete the request (${response.status}). Please try again.`);
    return data;
  } catch (error) {
    if (error.name === 'AbortError') throw new Error(options.method === 'POST'
      ? 'The request took too long. Check your Telegram chat before retrying; your preview may already have arrived.'
      : 'The connection is taking too long. Please try again.');
    if (error instanceof TypeError) throw new Error('You appear to be offline. Check your connection and try again.');
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}

function emptyState(title, description, create = false) {
  return `<div class="empty-state">${icon('layers')}<h3>${escapeHTML(title)}</h3><p>${escapeHTML(description)}</p>${create ? `<button class="button primary colorful-cta" data-create><span class="btn-icon-box">${icon('plus')}</span><span>Create your first post</span><span class="btn-inner-pill">Start</span></button>` : ''}</div>`;
}

function showStatus(title, message, retry = false) {
  $('#status-panel').hidden = false;
  $('#status-panel').innerHTML = `<h3>${escapeHTML(title)}</h3><p>${escapeHTML(message)}</p>${retry ? '<button class="button secondary" id="retry-load">Try again</button>' : ''}`;
  $('#retry-load')?.addEventListener('click', () => loadData(false));
}

function normalizePostRows(post) {
  if (Array.isArray(post.button_rows) && post.button_rows.length) return post.button_rows;
  const names = Array.isArray(post.button_names) ? post.button_names : [];
  return names.map((name, idx) => [{
    name,
    badge: '',
    color: BUTTON_THEMES[idx % BUTTON_THEMES.length],
  }]);
}

function renderProfile() {
  const user = state.profile;
  if (!user) return;
  const name = [user.first_name, user.last_name].filter(Boolean).join(' ') || 'Creator';
  $$('.user-name').forEach(el => { el.textContent = name; });
  $$('.user-handle').forEach(el => { el.textContent = user.username ? `@${user.username}` : 'Telegram creator'; });
  $$('.user-avatar').forEach(el => { if (!el.querySelector('img')) el.textContent = initials(name); });
  $('#greeting').textContent = `${greetingWord()}, ${user.first_name || 'creator'}`;
  $('#total-posts').textContent = user.total_posts.toLocaleString();
  $('#profile-total').textContent = user.total_posts.toLocaleString();
  $('#nav-count').textContent = user.total_posts;
  const mobCount = $('#mobile-nav-count');
  if (mobCount) {
    mobCount.textContent = user.total_posts;
    mobCount.hidden = !user.total_posts;
  }
  $('#profile-id').textContent = user.id;
}

function postCard(post) {
  const lines = post.text.split('\n').filter(Boolean);
  const title = lines[0] || 'Photo post';
  const subtitle = lines.slice(1).join(' ') || (post.has_photo ? 'High-resolution photo post saved in studio' : 'Text post saved in studio');
  const rows = normalizePostRows(post);
  const totalBtns = rows.reduce((acc, r) => acc + r.length, 0);

  const countPill = totalBtns
    ? `<span class="post-btn-count-pill">${icon('link')} ${totalBtns} ${totalBtns === 1 ? 'Button' : 'Buttons'}</span>`
    : '';

  const visual = post.has_photo
    ? `<div class="post-visual" data-open-post="${escapeHTML(post.id)}"><img class="post-image" alt="Photo attached to your post" loading="lazy" data-photo="${escapeHTML(post.id)}"><span class="post-type">${icon('image')} Photo</span>${countPill}</div>`
    : `<div class="post-visual text-art" data-open-post="${escapeHTML(post.id)}"><span class="post-type">${icon('text')} Text</span>${countPill}<span class="quote-mark">“</span><p>${escapeHTML(title)}</p></div>`;

  const previewRowsHTML = rows.slice(0, 2).map(row => {
    const cols = Math.min(row.length, MAX_COLS);
    const chips = row.slice(0, MAX_COLS).map(btn => {
      const theme = BUTTON_THEMES.includes(btn.color) ? btn.color : 'violet';
      const badgeHTML = btn.badge ? `<em>${escapeHTML(btn.badge)}</em>` : '';
      return `<div class="card-inline-chip theme-${theme}" data-open-post="${escapeHTML(post.id)}"><span>${escapeHTML(btn.name)}</span>${badgeHTML}</div>`;
    }).join('');
    return `<div class="card-btn-row" style="--cols:${cols}">${chips}</div>`;
  }).join('');

  return `<article class="post-card">
    ${visual}
    <div class="post-body">
      <div class="post-body-header" data-open-post="${escapeHTML(post.id)}">
        <h3>${escapeHTML(title)}</h3>
        <p class="post-excerpt">${escapeHTML(subtitle)}</p>
      </div>
      ${previewRowsHTML ? `<div class="card-btn-preview-rows">${previewRowsHTML}</div>` : ''}
      <div class="post-bottom">
        <span class="post-date">${icon('calendar')}${escapeHTML(dateLabel(post.created_at))}</span>
        <div class="card-quick-actions">
          <button type="button" class="card-sub-btn" data-quick-copy="${escapeHTML(post.id)}" title="Copy post text">${icon('copy')} <span>Copy</span></button>
          <button type="button" class="card-sub-btn" data-quick-remix="${escapeHTML(post.id)}" title="Remix in studio">${icon('sparkles')} <span>Remix</span></button>
          <button type="button" class="card-sub-btn primary-sub" data-quick-send="${escapeHTML(post.id)}" title="Send or share post">${icon('send')} <span>Send</span></button>
        </div>
      </div>
    </div>
  </article>`;
}

function updateFilterCounts() {
  const allCount = state.posts.length;
  const photoCount = state.posts.filter(p => p.has_photo).length;
  const textCount = state.posts.filter(p => !p.has_photo).length;
  const btnCount = state.posts.filter(p => (p.button_names?.length || 0) > 0).length;
  if ($('#count-all')) $('#count-all').textContent = allCount;
  if ($('#count-photo')) $('#count-photo').textContent = photoCount;
  if ($('#count-text')) $('#count-text').textContent = textCount;
  if ($('#count-buttons')) $('#count-buttons').textContent = btnCount;
}

function renderPosts() {
  updateFilterCounts();
  $('#recent-count').textContent = Math.min(state.posts.length, 2);
  $('#recent-posts').innerHTML = state.posts.length
    ? state.posts.slice(0, 2).map(postCard).join('')
    : emptyState('No saved posts yet', 'Create your first post with colorful multi-button rows.', state.ready);
  renderLibrary();
  loadImages($('#recent-posts'));
}

function renderLibrary() {
  const query = $('#post-search').value.toLowerCase().trim();
  $('#clear-search').hidden = !query;
  const posts = state.posts.filter(p => {
    const matchesFilter =
      state.filter === 'all' ||
      (state.filter === 'photo' && p.has_photo) ||
      (state.filter === 'text' && !p.has_photo) ||
      (state.filter === 'buttons' && (p.button_names?.length || 0) > 0);
    const matchesQuery = `${p.text} ${(p.button_names || []).join(' ')}`.toLowerCase().includes(query);
    return matchesFilter && matchesQuery;
  });

  const sortMode = $('#post-sort').value;
  posts.sort((a, b) => {
    if (sortMode === 'buttons') return (b.button_names?.length || 0) - (a.button_names?.length || 0);
    return (new Date(b.created_at).getTime() - new Date(a.created_at).getTime()) * (sortMode === 'oldest' ? -1 : 1);
  });

  $('#result-count').textContent = `${posts.length} of ${state.posts.length} loaded`;
  $('#library-posts').innerHTML = posts.length
    ? posts.map(postCard).join('')
    : emptyState(
        query || state.filter !== 'all' ? 'No matching posts' : 'No saved posts yet',
        query || state.filter !== 'all' ? 'Try another filter or clear your search query.' : 'Tap New post to get started.',
        !query && state.filter === 'all' && state.ready
      );
  $('#load-more').hidden = !state.hasMore;
  loadImages($('#library-posts'));
}

function renderLeaders() {
  const own = state.leaderboard.findIndex(user => user.is_you);
  const rankLabel = own >= 0 ? `#${own + 1}` : '—';
  $('#profile-rank').textContent = own >= 0 ? `#${own + 1}` : 'Not in top 100';
  $('#home-rank').textContent = rankLabel;
  $('#my-rank').hidden = !state.profile;
  $('#my-rank').innerHTML = `<span>Your current global rank</span><strong>${own >= 0 ? `#${own + 1}` : 'Top 100 awaits'}</strong>`;
  const palette = ['#f6e3cf', '#e9e2f5', '#dcefe6', '#fbe1e6'];
  const avatarFor = (u, i) => `<span class="avatar small" style="background:${palette[i % palette.length]}">${escapeHTML(initials(u.name))}</span>`;
  const top = state.leaderboard.slice(0, 3);
  $('#podium').hidden = top.length < 3;
  $('#podium').innerHTML = top.map((u, i) => `<div class="podium-card"><span class="podium-medal">#${i + 1}</span>${avatarFor(u, i)}<span class="podium-name">${escapeHTML(u.name)}${u.is_you ? ' · You' : ''}</span><span class="podium-score"><b>${Number(u.total_posts).toLocaleString()}</b> posts</span></div>`).join('');
  $('#leaderboard').innerHTML = state.leaderboard.length
    ? state.leaderboard.map((u, i) => `<div class="leader-row${u.is_you ? ' is-you' : ''}"><span class="rank">${String(i + 1).padStart(2, '0')}</span>${avatarFor(u, i)}<span class="leader-name">${escapeHTML(u.name)}${u.is_you ? ' · You' : ''}</span><span class="leader-score">${Number(u.total_posts).toLocaleString()}</span></div>`).join('')
    : emptyState('Be the first creator', 'Save a post to join the ranking.');
}

$$('[data-filter]').forEach(button => button.addEventListener('click', () => {
  state.filter = button.dataset.filter;
  $$('[data-filter]').forEach(b => {
    b.classList.toggle('selected', b === button);
    b.setAttribute('aria-pressed', String(b === button));
  });
  renderLibrary();
  haptic();
}));

$('#post-search').addEventListener('input', renderLibrary);
$('#clear-search')?.addEventListener('click', () => {
  $('#post-search').value = '';
  renderLibrary();
  $('#post-search').focus();
});
$('#load-more').addEventListener('click', () => loadData(true));
$('#post-sort').addEventListener('change', renderLibrary);
$('#refresh-posts').addEventListener('click', async () => {
  if (demo) { renderPosts(); toast('Studio library refreshed.'); return; }
  await loadData(false);
});

async function loadData(more = false) {
  if (state.loading) return;
  state.loading = true;
  $('#refresh-posts').disabled = true;
  $('#load-more').disabled = true;
  $('#library-posts').setAttribute('aria-busy', 'true');
  if (!more) {
    $('#status-panel').hidden = true;
    $('#recent-posts').innerHTML = '<div class="skeleton"></div><div class="skeleton"></div>';
  }
  try {
    const data = await api(`/api/data?page=${more ? state.page + 1 : 0}`);
    state.profile = data.profile;
    state.leaderboard = data.leaderboard;
    state.page = data.page;
    state.hasMore = data.has_more;
    state.ready = true;
    state.posts = more ? [...new Map([...state.posts, ...data.posts].map(p => [p.id, p])).values()] : data.posts;
    renderProfile();
    renderPosts();
    renderLeaders();
  } catch (error) {
    if (!more) {
      showStatus('Could not load posts', error.message, true);
      if (!state.ready) {
        $('#recent-posts').innerHTML = emptyState('Unable to load your library', 'Your posts have not been changed. Try again in a moment.');
        $('#library-posts').innerHTML = $('#recent-posts').innerHTML;
      }
    } else toast(error.message);
  } finally {
    state.loading = false;
    $('#load-more').disabled = false;
    $('#refresh-posts').disabled = false;
    $('#library-posts').setAttribute('aria-busy', 'false');
  }
}

async function mediaURL(path) {
  if (state.photoCache.has(path)) return state.photoCache.get(path);
  if (!state.mediaJobs.has(path)) state.mediaJobs.set(path, (async () => {
    const response = await fetch(path, { headers, signal: AbortSignal.timeout(20000) });
    if (!response.ok || response.status === 204) return null;
    if (!response.headers.get('content-type')?.startsWith('image/')) return null;
    const url = URL.createObjectURL(await response.blob());
    state.photoCache.set(path, url);
    return url;
  })().finally(() => state.mediaJobs.delete(path)));
  return state.mediaJobs.get(path);
}

async function attachImage(image) {
  const post = state.posts.find(p => p.id === image.dataset.photo);
  if (!post) return;
  try {
    const url = post.demo_image || (demo ? '/static/demo-mountains.webp' : await mediaURL(`/api/posts/${encodeURIComponent(post.id)}/photo`));
    if (!url) throw new Error('Unavailable');
    image.onerror = () => {
      image.replaceWith(Object.assign(document.createElement('div'), { className: 'media-unavailable', textContent: 'Photo preview unavailable' }));
    };
    image.src = url;
  } catch (_) {
    image.replaceWith(Object.assign(document.createElement('div'), { className: 'media-unavailable', textContent: 'Photo preview unavailable' }));
  }
}

const photoObserver = 'IntersectionObserver' in window
  ? new IntersectionObserver(entries => entries.forEach(entry => {
      if (entry.isIntersecting) {
        photoObserver.unobserve(entry.target);
        attachImage(entry.target);
      }
    }), { rootMargin: '120px' })
  : null;

function loadImages(root) {
  $$('[data-photo]', root).forEach(image => photoObserver ? photoObserver.observe(image) : attachImage(image));
}

async function loadAvatar() {
  try {
    const url = await mediaURL('/api/profile/photo');
    if (url) $$('.user-avatar').forEach(el => {
      const image = new Image();
      image.alt = 'Your Telegram profile photo';
      image.src = url;
      image.onerror = () => image.remove();
      el.append(image);
    });
  } catch (_) { /* Fall back to initials. */ }
}

function openPostDetail(post, openSendSection = false) {
  state.selectedPost = post;
  $('#send-options').open = openSendSection;
  $('#send-error').hidden = true;
  $('#send-status').textContent = '';
  $('#send-form').reset();
  $('#copy-post').innerHTML = `${icon('copy')} <span>Copy Text</span>`;

  const rows = normalizePostRows(post);
  const totalBtns = rows.reduce((acc, r) => acc + r.length, 0);
  const buttonsGridHTML = rows.map(row => {
    const cols = Math.min(row.length, MAX_COLS);
    const rowItems = row.map(btn => {
      const theme = BUTTON_THEMES.includes(btn.color) ? btn.color : 'violet';
      const badgeHTML = btn.badge
        ? `<span class="preview-btn-inner-badge">${escapeHTML(btn.badge)} ${icon('arrow-up')}</span>`
        : `<span class="preview-btn-inner-badge">OPEN ${icon('arrow-up')}</span>`;
      return `<div class="detail-button theme-${theme}"><span class="preview-btn-label">${icon('link')} ${escapeHTML(btn.name)}</span>${badgeHTML}</div>`;
    }).join('');
    return `<div class="preview-btn-row" style="--cols:${cols}">${rowItems}</div>`;
  }).join('');

  $('#detail-content').innerHTML = `
    <div class="detail-meta">
      <span>${icon('calendar')} ${escapeHTML(dateLabel(post.created_at))}</span>
      <span>·</span>
      <span>${icon('check-circle')} Saved in Studio</span>
      ${totalBtns ? `<span>·</span><span>${icon('link')} ${totalBtns} ${totalBtns === 1 ? 'button' : 'buttons'} (${rows.length} ${rows.length === 1 ? 'row' : 'rows'})</span>` : ''}
    </div>
    ${post.has_photo ? `<img class="detail-photo" data-photo="${escapeHTML(post.id)}" alt="Your post photo">` : ''}
    <p class="detail-text">${escapeHTML(post.text)}</p>
    ${buttonsGridHTML ? `<div class="detail-buttons-grid">${buttonsGridHTML}</div>` : ''}
  `;
  $('#detail').showModal();
  loadImages($('#detail-content'));
  if (openSendSection) {
    setTimeout(() => $('#send-options').scrollIntoView({ block: 'nearest', behavior: 'smooth' }), 80);
  }
  haptic();
}

document.addEventListener('click', event => {
  const trigger = event.target.closest('[data-open-post]');
  if (!trigger) return;
  const post = state.posts.find(p => p.id === trigger.dataset.openPost);
  if (post) openPostDetail(post, false);
});

$('#show-send').addEventListener('click', () => {
  $('#send-options').open = true;
  $('#send-options').scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  $('#share-post').focus();
});

$('#clone-post')?.addEventListener('click', () => {
  if (!state.selectedPost) return;
  const post = state.selectedPost;
  $('#detail').close();
  remixPostInStudio(post);
});

function remixPostInStudio(post) {
  openComposer();
  $('#post-text').value = post.text || '';
  const rows = normalizePostRows(post);
  state.composerRows = rows.map((row, rIdx) =>
    row.map((btn, cIdx) => ({
      name: btn.name || '',
      url: 'https://t.me/telegram',
      badge: btn.badge || '',
      color: btn.color || BUTTON_THEMES[(rIdx + cIdx) % BUTTON_THEMES.length],
    }))
  );
  renderComposerButtonRows();
  countText();
  toast('Post loaded into studio for remixing!');
}

async function sendSaved(action, target) {
  if (!state.selectedPost || state.sending) return;
  $('#send-error').hidden = true;
  $('#send-status').textContent = '';
  if (demo && !initData) {
    const destLabel = action === 'share' ? 'Telegram chat chooser' : action === 'self' ? 'your bot chat' : target;
    $('#send-status').textContent = `Preview Mode: Ready to send "${state.selectedPost.text.slice(0, 28)}…" to ${destLabel}. Open in Telegram to dispatch live!`;
    toast(`Simulated send to ${destLabel}`);
    return;
  }
  if (action === 'share' && (!tg?.isVersionAtLeast?.('8.0') || typeof tg.shareMessage !== 'function')) {
    $('#send-error').textContent = 'Update Telegram to choose a chat here. Or use Send to my bot, then forward the post.';
    $('#send-error').hidden = false;
    return;
  }
  state.sending = true;
  $$('#send-options button, #send-options input, #show-send').forEach(el => { el.disabled = true; });
  $('#send-status').textContent = action === 'share' ? 'Preparing your post…' : 'Sending…';
  try {
    const result = await api(`/api/posts/${encodeURIComponent(state.selectedPost.id)}/send`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action, target }),
    });
    if (action === 'share') {
      $('#send-status').textContent = 'Choose a chat in Telegram.';
      tg.shareMessage(result.prepared_id, sent => {
        $('#send-status').textContent = sent ? 'Post shared.' : 'Not shared. You can try again.';
      });
    } else {
      $('#send-status').textContent = action === 'self'
        ? 'Sent to your bot. You can forward it from there.'
        : 'Post sent to your channel.';
    }
  } catch (error) {
    $('#send-status').textContent = '';
    $('#send-error').textContent = error.message;
    $('#send-error').hidden = false;
  } finally {
    state.sending = false;
    $$('#send-options button, #send-options input, #show-send').forEach(el => { el.disabled = false; });
  }
}

$('#share-post').addEventListener('click', () => sendSaved('share'));
$('#send-self').addEventListener('click', () => sendSaved('self'));
$('#send-form').addEventListener('submit', event => {
  event.preventDefault();
  sendSaved('publish', $('#send-target').value.trim());
});

/* ------------------------------------------------------------------
   Smart Button Builder: Flexible Rows, Sub-Buttons & Presets
------------------------------------------------------------------- */
function totalComposerButtons() {
  return state.composerRows.reduce((sum, r) => sum + r.length, 0);
}

function nextThemeColor() {
  return BUTTON_THEMES[totalComposerButtons() % BUTTON_THEMES.length];
}

function syncComposerRowsFromDOM() {
  const rowGroups = $$('.btn-row-group', $('#button-fields'));
  if (!rowGroups.length) return;
  state.composerRows = rowGroups.map(group =>
    $$('.button-item-card', group).map(card => ({
      name: $('.btn-name-input', card)?.value || '',
      url: $('.btn-url-input', card)?.value || '',
      badge: $('.btn-badge-input', card)?.value || '',
      color: card.dataset.color || 'violet',
    }))
  ).filter(r => r.length > 0);
}

function renderComposerButtonRows() {
  const container = $('#button-fields');
  container.replaceChildren();
  state.composerRows = state.composerRows.filter(r => Array.isArray(r) && r.length > 0);

  state.composerRows.forEach((row, rIdx) => {
    const group = document.createElement('div');
    group.className = 'btn-row-group';
    const cols = Math.min(row.length, MAX_COLS);
    const canAddCol = row.length < MAX_COLS && totalComposerButtons() < MAX_BUTTONS;

    group.innerHTML = `
      <div class="btn-row-header">
        <span class="btn-row-badge">${icon('layers')} Row ${rIdx + 1} · ${row.length === 1 ? 'Full Width' : `${row.length} Side-by-Side`}</span>
        <div class="btn-row-actions">
          <button type="button" class="row-add-col-btn" data-add-to-row="${rIdx}" ${canAddCol ? '' : 'disabled'}>
            ${icon('plus')} <span>+ Inside Row (${row.length}/${MAX_COLS})</span>
          </button>
        </div>
      </div>
      <div class="btn-row-items" style="--row-cols:${cols}"></div>
    `;

    const itemsWrap = $('.btn-row-items', group);
    row.forEach((btn, cIdx) => {
      const theme = BUTTON_THEMES.includes(btn.color) ? btn.color : BUTTON_THEMES[(rIdx + cIdx) % BUTTON_THEMES.length];
      const card = document.createElement('div');
      card.className = 'button-item-card';
      card.dataset.color = theme;

      const swatchesHTML = BUTTON_THEMES.map(t =>
        `<button type="button" class="color-dot${t === theme ? ' active' : ''}" data-swatch="${t}" aria-label="Color ${t}"></button>`
      ).join('');

      card.innerHTML = `
        <div class="btn-item-top">
          <div class="color-dots">${swatchesHTML}</div>
          <button type="button" class="btn-remove-mini" data-remove-btn="${rIdx}:${cIdx}" aria-label="Remove button">${icon('close')}</button>
        </div>
        <div class="btn-item-inputs">
          <input class="btn-name-input" aria-label="Button label" placeholder="Button label (e.g. Join Now)" maxlength="64" value="${escapeHTML(btn.name)}" required>
          <input class="btn-badge-input" aria-label="Inner badge" placeholder="TAG (HOT)" maxlength="12" value="${escapeHTML(btn.badge || '')}" title="Optional inner pill badge">
        </div>
        <input class="btn-url-input" aria-label="Button destination" placeholder="https:// link or @username" maxlength="2048" value="${escapeHTML(btn.url)}" required>
      `;

      // Color swatch switching
      $$('.color-dot', card).forEach(dot => {
        dot.addEventListener('click', () => {
          syncComposerRowsFromDOM();
          const chosen = dot.dataset.swatch;
          card.dataset.color = chosen;
          state.composerRows[rIdx][cIdx].color = chosen;
          $$('.color-dot', card).forEach(d => d.classList.toggle('active', d === dot));
          state.submissionKey = null;
          updatePreview();
        });
      });

      // Remove button
      $('[data-remove-btn]', card).addEventListener('click', () => {
        syncComposerRowsFromDOM();
        state.composerRows[rIdx].splice(cIdx, 1);
        if (!state.composerRows[rIdx].length) state.composerRows.splice(rIdx, 1);
        state.submissionKey = null;
        renderComposerButtonRows();
        updatePreview();
      });

      itemsWrap.append(card);
    });

    $('[data-add-to-row]', group)?.addEventListener('click', () => {
      syncComposerRowsFromDOM();
      if (state.composerRows[rIdx].length >= MAX_COLS || totalComposerButtons() >= MAX_BUTTONS) return;
      state.composerRows[rIdx].push({
        name: '',
        url: '',
        badge: 'NEW',
        color: nextThemeColor(),
      });
      state.submissionKey = null;
      renderComposerButtonRows();
      updatePreview();
      const newInputs = $$('.btn-name-input', $('#button-fields'));
      newInputs[newInputs.length - 1]?.focus();
    });

    container.append(group);
  });

  const total = totalComposerButtons();
  $('#button-count-badge').textContent = `${total} / ${MAX_BUTTONS}`;
  $('#clear-all-buttons').hidden = total === 0;
  $('#add-button').disabled = total >= MAX_BUTTONS;
  const lastRow = state.composerRows[state.composerRows.length - 1];
  $('#add-inline-button').disabled = total >= MAX_BUTTONS || (lastRow && lastRow.length >= MAX_COLS);
}

function applyPresetButtons(presetItems) {
  const grouped = new Map();
  presetItems.forEach((b, idx) => {
    const r = b.row ?? idx;
    if (!grouped.has(r)) grouped.set(r, []);
    grouped.get(r).push({
      name: b.name || '',
      url: b.url || 'https://t.me/telegram',
      badge: b.badge || '',
      color: b.color || BUTTON_THEMES[idx % BUTTON_THEMES.length],
    });
  });
  state.composerRows = [...grouped.values()];
  $('#button-options').open = true;
  renderComposerButtonRows();
  updatePreview();
  haptic();
}

function applyQuickAllocation(mode) {
  $$('.scaler-chip').forEach(chip => chip.classList.toggle('active', chip.dataset.btnCount === mode));
  if (mode === '0') {
    state.composerRows = [];
  } else if (mode === '1') {
    state.composerRows = [[{ name: 'Explore Now', url: 'https://t.me/telegram', badge: 'HOT', color: 'violet' }]];
  } else if (mode === '2-row') {
    state.composerRows = [[
      { name: 'Join Channel', url: 'https://t.me/telegram', badge: 'VIP', color: 'violet' },
      { name: 'Open Chat', url: 'https://t.me/telegram', badge: 'LIVE', color: 'emerald' },
    ]];
  } else if (mode === '3-pack') {
    state.composerRows = [
      [{ name: 'Main Official Link', url: 'https://t.me/telegram', badge: 'TOP', color: 'violet' }],
      [
        { name: 'Discussion', url: 'https://t.me/telegram', badge: 'CHAT', color: 'emerald' },
        { name: 'Resources', url: 'https://t.me/telegram', badge: 'FREE', color: 'amber' },
      ],
    ];
  } else if (mode === '4-grid') {
    applyPresetButtons(BUTTON_PRESETS.grid);
    return;
  } else if (mode === '6-pack') {
    state.composerRows = [
      [
        { name: 'Channel', url: 'https://t.me/telegram', badge: 'VIP', color: 'violet' },
        { name: 'Group', url: 'https://t.me/telegram', badge: '24/7', color: 'emerald' },
      ],
      [
        { name: 'Website', url: 'https://t.me/telegram', badge: 'PRO', color: 'ocean' },
        { name: 'Offers', url: 'https://t.me/telegram', badge: 'HOT', color: 'rose' },
      ],
      [
        { name: 'Tutorials', url: 'https://t.me/telegram', badge: 'NEW', color: 'amber' },
        { name: 'Support', url: 'https://t.me/telegram', badge: 'HELP', color: 'sunset' },
      ],
    ];
  }
  $('#button-options').open = true;
  renderComposerButtonRows();
  updatePreview();
  haptic();
}

$$('[data-btn-count]').forEach(chip => {
  chip.addEventListener('click', () => applyQuickAllocation(chip.dataset.btnCount));
});

$$('[data-preset]').forEach(pill => {
  pill.addEventListener('click', () => {
    const preset = BUTTON_PRESETS[pill.dataset.preset];
    if (preset) {
      applyPresetButtons(preset);
      toast(`Loaded "${pill.textContent.trim()}" button pack!`);
    }
  });
});

$('#clear-all-buttons')?.addEventListener('click', () => {
  state.composerRows = [];
  $$('.scaler-chip').forEach(c => c.classList.remove('active'));
  renderComposerButtonRows();
  updatePreview();
});

$('#add-button').addEventListener('click', () => {
  if (state.busy || totalComposerButtons() >= MAX_BUTTONS) return;
  syncComposerRowsFromDOM();
  state.composerRows.push([{
    name: '',
    url: '',
    badge: 'HOT',
    color: nextThemeColor(),
  }]);
  state.submissionKey = null;
  $('#button-options').open = true;
  renderComposerButtonRows();
  updatePreview();
  const inputs = $$('.btn-name-input', $('#button-fields'));
  inputs[inputs.length - 1]?.focus();
});

$('#add-inline-button')?.addEventListener('click', () => {
  if (state.busy || totalComposerButtons() >= MAX_BUTTONS) return;
  syncComposerRowsFromDOM();
  if (!state.composerRows.length || state.composerRows[state.composerRows.length - 1].length >= MAX_COLS) {
    state.composerRows.push([{ name: '', url: '', badge: 'NEW', color: nextThemeColor() }]);
  } else {
    state.composerRows[state.composerRows.length - 1].push({
      name: '',
      url: '',
      badge: 'NEW',
      color: nextThemeColor(),
    });
  }
  state.submissionKey = null;
  $('#button-options').open = true;
  renderComposerButtonRows();
  updatePreview();
  const inputs = $$('.btn-name-input', $('#button-fields'));
  inputs[inputs.length - 1]?.focus();
});

$('#insert-template-btn')?.addEventListener('click', () => {
  const tpl = STARTER_TEMPLATES[state.templateIndex % STARTER_TEMPLATES.length];
  state.templateIndex += 1;
  $('#post-text').value = tpl;
  countText();
  haptic();
});

function openComposer(options = {}) {
  $('#compose-error').hidden = true;
  if (options.preset && BUTTON_PRESETS[options.preset]) {
    applyPresetButtons(BUTTON_PRESETS[options.preset]);
    if (!$('#post-text').value.trim()) {
      $('#post-text').value = STARTER_TEMPLATES[0];
    }
  } else if (options.mode === 'photo') {
    $('#photo-options').open = true;
  } else if (options.mode === 'text' && !totalComposerButtons()) {
    applyQuickAllocation('1');
  }
  countText();
  $('#composer').showModal();
  haptic();
}

function countText() {
  const hasPhoto = Boolean($('#photo-input').files.length);
  const limit = hasPhoto ? 1024 : 4096;
  $('#post-text').maxLength = limit;
  $('#char-count').textContent = `${$('#post-text').value.length.toLocaleString()} / ${limit.toLocaleString()}`;
  $('#char-count').classList.toggle('over-limit', $('#post-text').value.length > limit);
  updatePreview();
}

$('#post-text').addEventListener('input', countText);

function clearPhoto() {
  state.submissionKey = null;
  if (state.photoURL) URL.revokeObjectURL(state.photoURL);
  state.photoURL = null;
  $('#photo-input').value = '';
  $('#selected-photo').removeAttribute('src');
  $('#photo-preview').hidden = true;
  $('#upload-zone').hidden = false;
  if ($('#photo-status-pill')) $('#photo-status-pill').textContent = 'Add Photo';
  countText();
}

$('#photo-input').addEventListener('change', () => {
  const file = $('#photo-input').files[0];
  if (!file) { clearPhoto(); return; }
  if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type) || file.size > 9 * 1024 * 1024) {
    clearPhoto();
    showComposeError('Choose a JPEG, PNG or WebP photo smaller than 9 MB.');
    return;
  }
  if (state.photoURL) URL.revokeObjectURL(state.photoURL);
  state.photoURL = URL.createObjectURL(file);
  $('#selected-photo').src = state.photoURL;
  $('#photo-preview').hidden = false;
  $('#upload-zone').hidden = true;
  if ($('#photo-status-pill')) $('#photo-status-pill').textContent = '1 Attached';
  countText();
});

$('#remove-photo').addEventListener('click', clearPhoto);

function showComposeError(message) {
  $('#compose-error').textContent = message;
  $('#compose-error').hidden = false;
  $('#compose-error').scrollIntoView({ block: 'nearest' });
}

function setComposerBusy(busy) {
  $$('#compose-form input, #compose-form textarea, #compose-form button').forEach(el => { el.disabled = busy; });
  if (!busy) renderComposerButtonRows();
}

$('#compose-form').addEventListener('invalid', event => {
  let parent = event.target.parentElement;
  while (parent) {
    if (parent.tagName === 'DETAILS') parent.open = true;
    parent = parent.parentElement;
  }
}, true);

function collectFlatButtonsPayload() {
  syncComposerRowsFromDOM();
  const flat = [];
  state.composerRows.forEach((row, rIdx) => {
    row.forEach(btn => {
      if (btn.name.trim() || btn.url.trim()) {
        flat.push({
          name: btn.name.trim(),
          url: btn.url.trim(),
          badge: btn.badge.trim(),
          color: btn.color || 'violet',
          row: rIdx,
        });
      }
    });
  });
  return flat;
}

$('#compose-form').addEventListener('submit', async event => {
  event.preventDefault();
  if (state.busy) return;
  const text = $('#post-text').value.trim();
  const photo = $('#photo-input').files[0];
  if (!text && !photo) {
    showComposeError('Write a post or attach a photo first.');
    return;
  }
  if (text.length > (photo ? 1024 : 4096)) {
    showComposeError(photo ? 'Photo captions can be up to 1,024 characters.' : 'Keep your post under 4,096 characters.');
    return;
  }

  const buttons = collectFlatButtonsPayload();
  for (const b of buttons) {
    if (!b.name || !b.url) {
      showComposeError('Every button needs both a label and a destination link or @username.');
      return;
    }
  }

  // Interactive Demo Mode: Save directly into the live session library so users can test full flow
  if (demo && !initData) {
    const newPostId = `local-${Date.now()}`;
    const demoImg = state.photoURL ? state.photoURL : null;
    const groupedRows = state.composerRows
      .map(r => r.filter(b => b.name.trim()).map(b => ({ name: b.name.trim(), badge: b.badge.trim(), color: b.color })))
      .filter(r => r.length > 0);
    const createdPost = {
      id: newPostId,
      text: text || 'Photo showcase post',
      has_photo: Boolean(demoImg),
      demo_image: demoImg,
      button_names: buttons.map(b => b.name),
      button_rows: groupedRows,
      created_at: new Date().toISOString(),
    };
    state.posts.unshift(createdPost);
    if (state.profile) state.profile.total_posts += 1;
    state.photoURL = null; // Keep object URL alive for the session card
    $('#composer').close();
    $('#compose-form').reset();
    $('#selected-photo').removeAttribute('src');
    $('#photo-preview').hidden = true;
    $('#upload-zone').hidden = false;
    state.composerRows = [];
    renderComposerButtonRows();
    renderProfile();
    renderPosts();
    navigate('posts');
    toast('Post saved to your studio library!');
    return;
  }

  const data = new FormData();
  data.append('save_only', '1');
  data.append('text', text);
  data.append('buttons', JSON.stringify(buttons));
  if (photo) data.append('photo', photo);

  state.busy = true;
  $('#compose-error').hidden = true;
  setComposerBusy(true);
  $('#submit-post').innerHTML = '<span>Saving…</span>';
  try {
    state.submissionKey ||= crypto.randomUUID();
    const result = await api('/api/compose', { method: 'POST', body: data, headers: { 'X-Idempotency-Key': state.submissionKey } });
    state.submissionKey = null;
    state.busy = false;
    $('#composer').close();
    $('#compose-form').reset();
    clearPhoto();
    state.composerRows = [];
    renderComposerButtonRows();
    toast(result.saved ? 'Post saved. Share it anytime.' : result.warning || 'Your preview is in Telegram.');
    navigate('posts');
    await loadData(false);
  } catch (error) {
    showComposeError(error.message);
  } finally {
    state.busy = false;
    setComposerBusy(false);
    $('#submit-post').innerHTML = `<span class="btn-icon-box">${icon('check')}</span><span>Save to Studio</span><span class="btn-inner-pill">Ready</span>`;
  }
});

// Build preview nodes with a strict formatting allowlist; never inject user HTML.
function updatePreview() {
  syncComposerRowsFromDOM();
  const root = $('#live-text');
  root.replaceChildren();
  const text = $('#post-text').value;
  if (!text.trim()) {
    const placeholder = document.createElement('span');
    placeholder.className = 'preview-placeholder';
    placeholder.textContent = 'Your live Telegram post preview…';
    root.append(placeholder);
  } else {
    const parsed = new DOMParser().parseFromString(text, 'text/html');
    const allowed = new Set(['B', 'STRONG', 'I', 'EM', 'U', 'S', 'DEL', 'CODE', 'PRE', 'BLOCKQUOTE']);
    function appendSafe(source, target, depth = 0) {
      if (depth > 40) { target.append(document.createTextNode(source.textContent)); return; }
      for (const node of source.childNodes) {
        if (node.nodeType === Node.TEXT_NODE) target.append(document.createTextNode(node.textContent));
        else if (node.nodeType === Node.ELEMENT_NODE) {
          if (node.tagName === 'BR') { target.append(document.createElement('br')); continue; }
          if (allowed.has(node.tagName)) {
            const element = document.createElement(node.tagName.toLowerCase());
            appendSafe(node, element, depth + 1);
            target.append(element);
          } else appendSafe(node, target, depth + 1);
        }
      }
    }
    appendSafe(parsed.body, root);
  }

  $('#live-photo').hidden = !state.photoURL;
  if (state.photoURL) $('#live-photo').src = state.photoURL;
  else $('#live-photo').removeAttribute('src');

  const liveBtns = $('#live-buttons');
  liveBtns.replaceChildren();
  state.composerRows.forEach(row => {
    if (!row.length) return;
    const rowEl = document.createElement('div');
    rowEl.className = 'preview-btn-row';
    rowEl.style.setProperty('--cols', String(Math.min(row.length, MAX_COLS)));

    row.forEach(btn => {
      const item = document.createElement('div');
      const theme = BUTTON_THEMES.includes(btn.color) ? btn.color : 'violet';
      item.className = `preview-inline-btn theme-${theme}`;
      const labelSpan = document.createElement('span');
      labelSpan.className = 'preview-btn-label';
      labelSpan.innerHTML = `${icon('link')} ${escapeHTML(btn.name.trim() || 'Button label')}`;

      const badgeSpan = document.createElement('span');
      badgeSpan.className = 'preview-btn-inner-badge';
      badgeSpan.innerHTML = `${escapeHTML(btn.badge.trim() || 'LINK')} ${icon('arrow-up')}`;

      item.append(labelSpan, badgeSpan);
      rowEl.append(item);
    });
    liveBtns.append(rowEl);
  });
}

// Theme management
const systemDark = matchMedia('(prefers-color-scheme: dark)');
const THEME_COLORS = { light: '#f3f4fa', dark: '#0c0c14' };
function setTheme(choice, persist = true) {
  const mode = ['light', 'dark', 'system'].includes(choice) ? choice : 'system';
  const dark = mode === 'dark' || (mode === 'system' && systemDark.matches);
  document.documentElement.dataset.theme = dark ? 'dark' : 'light';
  const toggleIcon = icon(dark ? 'sun' : 'moon');
  const toggleLabel = `Switch to ${dark ? 'light' : 'dark'} mode`;
  $('#theme-toggle').innerHTML = `<span class="nav-icon-wrap sunset">${toggleIcon}</span><span class="theme-text">${dark ? 'Light mode' : 'Dark mode'}</span>`;
  $('#theme-toggle').setAttribute('aria-label', toggleLabel);
  $('#theme-toggle-mobile').innerHTML = toggleIcon;
  $('#theme-toggle-mobile').setAttribute('aria-label', toggleLabel);
  $$('[data-theme-choice]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.themeChoice === mode)));
  $('meta[name="theme-color"]').content = dark ? THEME_COLORS.dark : THEME_COLORS.light;
  if (persist) { try { localStorage.setItem('poststudio-theme', mode); } catch (_) {} }
  try {
    if (tg?.isVersionAtLeast?.('6.1')) {
      tg.setHeaderColor(dark ? THEME_COLORS.dark : THEME_COLORS.light);
      tg.setBackgroundColor(dark ? THEME_COLORS.dark : THEME_COLORS.light);
    }
  } catch (_) {}
  try {
    if (tg?.isVersionAtLeast?.('7.10')) tg.setBottomBarColor?.(dark ? '#161622' : '#ffffff');
  } catch (_) {}
}

let savedTheme;
try { savedTheme = localStorage.getItem('poststudio-theme'); } catch (_) {}
setTheme(savedTheme || 'system', false);
systemDark.addEventListener?.('change', () => {
  let mode;
  try { mode = localStorage.getItem('poststudio-theme'); } catch (_) {}
  if (!mode || mode === 'system') setTheme('system', false);
});
function flipTheme() {
  setTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark');
  haptic();
}
$('#theme-toggle').addEventListener('click', flipTheme);
$('#theme-toggle-mobile').addEventListener('click', flipTheme);
$$('[data-theme-choice]').forEach(button => button.addEventListener('click', () => {
  setTheme(button.dataset.themeChoice);
  haptic();
}));

$('#compose-form').addEventListener('input', () => {
  state.submissionKey = null;
  updatePreview();
});
$('#compose-form').addEventListener('change', () => {
  state.submissionKey = null;
});

$$('[data-format]').forEach(button => button.addEventListener('click', () => {
  const input = $('#post-text');
  const { selectionStart: start, selectionEnd: end } = input;
  const tag = button.dataset.format;
  const selection = input.value.slice(start, end) || 'your text';
  const replacement = `<${tag}>${selection}</${tag}>`;
  if (input.value.length - (end - start) + replacement.length > input.maxLength) {
    showComposeError('There is not enough space to add formatting. Shorten your message first.');
    return;
  }
  input.setRangeText(replacement, start, end, 'select');
  input.focus();
  input.dispatchEvent(new Event('input', { bubbles: true }));
  countText();
}));

// Drag-and-drop photo support
const uploadZone = $('#upload-zone');
['dragenter', 'dragover'].forEach(name => uploadZone.addEventListener(name, event => {
  event.preventDefault();
  uploadZone.classList.add('dragging');
}));
['dragleave', 'drop'].forEach(name => uploadZone.addEventListener(name, event => {
  event.preventDefault();
  uploadZone.classList.remove('dragging');
}));
uploadZone.addEventListener('drop', event => {
  if (state.busy) return;
  const file = event.dataTransfer.files[0];
  if (!file) return;
  const transfer = new DataTransfer();
  transfer.items.add(file);
  $('#photo-input').files = transfer.files;
  $('#photo-input').dispatchEvent(new Event('change', { bubbles: true }));
});

async function copyTextToClipboard(text, btnElement) {
  const originalHTML = btnElement.innerHTML;
  try {
    await navigator.clipboard.writeText(text);
    btnElement.innerHTML = `${icon('check')} <span>Copied!</span>`;
    toast('Post text copied to clipboard!');
    setTimeout(() => { btnElement.innerHTML = originalHTML; }, 1800);
  } catch (_) {
    toast('Select the text to copy it.');
  }
}

$('#copy-post').addEventListener('click', () => {
  if (!state.selectedPost) return;
  copyTextToClipboard(state.selectedPost.text, $('#copy-post'));
});

document.addEventListener('keydown', event => {
  if (event.ctrlKey || event.metaKey || event.altKey || event.repeat || event.isComposing) return;
  if (event.target.closest('input, textarea, select, [contenteditable="true"]') || $('dialog[open]')) return;
  if (event.key.toLowerCase() === 'n') { event.preventDefault(); openComposer(); }
  if (event.key === '/') { event.preventDefault(); navigate('posts'); $('#post-search').focus(); }
});

window.addEventListener('beforeunload', event => {
  if ($('#post-text').value.trim() || $('#photo-input').files.length || state.busy) {
    event.preventDefault();
    event.returnValue = '';
  }
});
window.addEventListener('offline', () => toast('You’re offline. Your current draft is still here.'));
window.addEventListener('online', () => toast('You’re back online. Ready when you are.'));

function loadDemo() {
  $('#demo-banner').hidden = false;
  state.profile = { id: 6069200310, first_name: 'Alex', last_name: 'Morgan', username: 'alexcreates', total_posts: 4 };
  const now = Date.now();
  state.posts = [
    {
      id: 'sample-1',
      text: 'A fresh perspective.\nSometimes all you need is a little distance to see things differently. Tap any button below to explore our new studio packs.',
      has_photo: true,
      demo_image: '/static/demo-mountains.webp',
      button_names: ['Explore Studio', 'Join VIP', 'Live Chat'],
      button_rows: [
        [{ name: 'Explore Studio', badge: 'HOT', color: 'violet' }],
        [
          { name: 'Join VIP', badge: 'PRO', color: 'emerald' },
          { name: 'Live Chat', badge: '24/7', color: 'amber' },
        ],
      ],
      created_at: new Date(now - 3600000).toISOString(),
    },
    {
      id: 'sample-2',
      text: 'Multi-Button Grid Showcase.\nGive every post the exact number of buttons it needs — 1, 2, 3, or a full 2×2 colorful action grid.',
      has_photo: false,
      button_names: ['Channel', 'Community', 'Tutorials', 'Support'],
      button_rows: [
        [
          { name: 'Channel', badge: 'TOP', color: 'violet' },
          { name: 'Community', badge: 'LIVE', color: 'emerald' },
        ],
        [
          { name: 'Tutorials', badge: 'FREE', color: 'amber' },
          { name: 'Support', badge: 'HELP', color: 'rose' },
        ],
      ],
      created_at: new Date(now - 86400000).toISOString(),
    },
    {
      id: 'sample-3',
      text: 'Chasing the golden hour.\nA moment of stillness before the world wakes up. Save a little space for the things that make you pause.',
      has_photo: true,
      demo_image: '/static/demo-ocean.webp',
      button_names: ['Read Full Story', 'Gallery'],
      button_rows: [
        [
          { name: 'Read Full Story', badge: 'NEW', color: 'ocean' },
          { name: 'Gallery', badge: 'HD', color: 'rose' },
        ],
      ],
      created_at: new Date(now - 172800000).toISOString(),
    },
    {
      id: 'sample-4',
      text: 'Your next chapter starts now.\nA blank page isn’t empty — it’s full of possibilities. What will you build today?',
      has_photo: false,
      button_names: ['Start Creating'],
      button_rows: [
        [{ name: 'Start Creating', badge: 'GO', color: 'sunset' }],
      ],
      created_at: new Date(now - 259200000).toISOString(),
    },
  ];
  state.leaderboard = Array.from({ length: 100 }, (_, i) => ({
    name: ['Maya Chen', 'Arjun Patel', 'Sofia Rivera', 'Jamie Park'][i] || `Creator ${i + 1}`,
    total_posts: 420 - i * 4,
    is_you: i === 11,
  }));
  state.leaderboard[11].name = 'Alex Morgan';
  state.ready = true;
  renderProfile();
  renderPosts();
  renderLeaders();
}

if (initData) {
  loadData();
  loadAvatar();
} else {
  loadDemo();
}

window.addEventListener('pagehide', () => {
  for (const url of state.photoCache.values()) URL.revokeObjectURL(url);
  state.photoCache.clear();
});
