/**
 * Post Maker – Telegram Mini App (single-file React + Tailwind + Lucide)
 * ---------------------------------------------------------------------------------------------
 * Design system : telegram-apps/telegram-ui (Section / Cell / Switch / Chip anatomy) + iOS Telegram.
 * Backend       : the existing aiohttp API in /bot/api.py (state, draft, media, chats, send, posts).
 *
 * Layout model (this is what fixes the "floating bar overlaps bottom nav" bug):
 *
 *   ┌ header ────────────────────────────┐  flex child, safe-area top
 *   ├ stage (relative, flex-1, min-h-0) ─┤
 *   │   scroll pages  (pb-36)            │  content scrolls UNDER the glass action bar
 *   │   action bar    (absolute bottom)  │  docked to the stage's bottom edge
 *   ├ bottom nav ────────────────────────┤  flex child, owns safe-area bottom padding
 *   └────────────────────────────────────┘
 *
 *   The bar is positioned relative to the stage, and the stage ends exactly where the nav begins,
 *   so the two can never overlap on any device, keyboard state or safe-area inset.
 *
 * Sections:  1 Utilities · 2 API · 3 Theme · 4 UI kit · 5 State engines · 6 Screens · 7 App shell
 */
import React, {
  createContext, useCallback, useContext, useEffect, useMemo, useRef, useState,
} from 'react';
import {
  Bold, Italic, Underline, Strikethrough, Code, EyeOff, Quote, Link2, SquarePen, UsersRound,
  Bookmark, UserRound, Send, Paperclip, Image as ImageIcon, X, RefreshCw, Plus, Trash2, Pencil,
  ChevronRight, Check, Star, ExternalLink, Save, Cloud, CloudOff, LoaderCircle, BadgeCheck,
  Megaphone, Film, Music, File as FileIcon, Type, TriangleAlert, CircleCheck, CircleX, Clock,
  RotateCcw, Ellipsis, Sparkles, ShieldCheck, Hash, Crown,
} from 'lucide-react';

/* ============================================================================================
 * 1. UTILITIES
 * ========================================================================================== */
const getTg = () => (typeof window !== 'undefined' && window.Telegram && window.Telegram.WebApp) || null;
const cx = (...a) => a.filter(Boolean).join(' ');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const plural = (n, a, b) => `${n} ${n === 1 ? a : b}`;
const fmtNum = (n) => Number(n || 0).toLocaleString();
const uuid = () => (crypto.randomUUID ? crypto.randomUUID() : `r${Date.now().toString(36)}${Math.random().toString(36).slice(2, 12)}`);
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

/**
 * Telegram haptics. EVERY button press and toggle calls `haptic.tap()` (= impactOccurred('light'));
 * `haptic.notify()` is used for outcomes (success / error / warning). Always safe outside Telegram.
 */
const haptic = {
  /** User preference (Profile > Haptic feedback). Defaults to on. */
  get enabled() { try { return localStorage.getItem('pm_haptics') !== '0'; } catch (_) { return true; } },
  set enabled(v) { try { localStorage.setItem('pm_haptics', v ? '1' : '0'); } catch (_) { /* private mode */ } },
  tap() { try { if (this.enabled) getTg()?.HapticFeedback?.impactOccurred('light'); } catch (_) { /* not in Telegram */ } },
  notify(kind) { try { if (this.enabled) getTg()?.HapticFeedback?.notificationOccurred(kind); } catch (_) { /* not in Telegram */ } },
};

function openLink(url) {
  const tg = getTg();
  try {
    if (tg && /^https:\/\/t\.me\//.test(url)) return tg.openTelegramLink(url);
    if (tg) return tg.openLink(url);
  } catch (_) { /* fall through */ }
  return window.open(url, '_blank', 'noopener');
}

const typeName = (t) => (t === 'channel' ? 'Channel' : t === 'supergroup' ? 'Supergroup' : 'Group');
const fullName = (u) => [u.first_name, u.last_name].filter(Boolean).join(' ') || (u.username ? `@${u.username}` : 'Telegram user');
const fmtLabel = (u) => String(u || '').replace(/^https?:\/\/(www\.)?/, '').replace(/\/$/, '');

function ago(iso) {
  const t = Date.parse(iso);
  if (!t) return '';
  const m = Math.max(0, Math.round((Date.now() - t) / 60000));
  if (m < 1) return 'just now';
  if (m < 60) return `${m} min ago`;
  if (m < 1440) return `${Math.round(m / 60)} h ago`;
  return `${Math.round(m / 1440)} d ago`;
}

/** "@name", "example.com" or full URL -> normalised https URL (or null when invalid). */
function normLink(raw) {
  const v = String(raw || '').trim();
  if (/^@[A-Za-z0-9_]{4,32}$/.test(v)) return `https://t.me/${v.slice(1)}`;
  if (!v || /\s/.test(v)) return null;
  const u = /^https?:\/\//i.test(v) ? v : `https://${v}`;
  try {
    const p = new URL(u);
    if (!/^https?:$/.test(p.protocol) || !p.hostname.includes('.') || p.username) return null;
    return p.href.replace(/\/$/, p.pathname === '/' && !p.search && !p.hash ? '' : '/');
  } catch (_) { return null; }
}

/* ---- Telegram-safe HTML (mirror of the server sanitiser; keeps the editor and backend in sync) ---- */
const TAGS = { B: 'b', STRONG: 'b', I: 'i', EM: 'i', U: 'u', INS: 'u', S: 's', STRIKE: 's', DEL: 's', CODE: 'code', PRE: 'pre', 'TG-SPOILER': 'tg-spoiler', BLOCKQUOTE: 'blockquote', A: 'a' };
const BLOCK = new Set(['DIV', 'P', 'LI', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6']);
const xml = (t) => t.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

function tgClean(html) {
  const doc = new DOMParser().parseFromString(`<body>${html || ''}</body>`, 'text/html');
  let out = '';
  let plain = '';
  const open = [];
  const nl = () => { if (plain && !plain.endsWith('\n')) { out += '\n'; plain += '\n'; } };
  (function walk(n) {
    if (n.nodeType === 3) { const t = n.nodeValue.replace(/\u00a0/g, ' '); out += xml(t); plain += t; return; }
    if (n.nodeType !== 1) return;
    const tag = n.tagName;
    if (tag === 'BR') { out += '\n'; plain += '\n'; return; }
    if (BLOCK.has(tag)) nl();
    let name = TAGS[tag];
    let href = '';
    if (name === 'a') { href = n.getAttribute('href') || ''; if (!/^https?:\/\//i.test(href)) name = null; }
    if (name && open.includes(name)) name = null;
    if ((open.includes('pre') || open.includes('code')) && !(name === 'code' && open.includes('pre') && !open.includes('code'))) name = null;
    if (name) { out += name === 'a' ? `<a href="${esc(href)}">` : `<${name}>`; open.push(name); }
    n.childNodes.forEach(walk);
    if (name) { out += `</${name}>`; open.pop(); }
    if (BLOCK.has(tag)) nl();
  })(doc.body);
  for (let prev = null; prev !== out;) {
    prev = out;
    out = out.replace(/<(b|i|u|s|code|pre|tg-spoiler|blockquote)><\/\1>|<a href="[^"]*"><\/a>/g, '');
  }
  return { html: out.trim(), plain: plain.trim() };
}

/* ---- Avatars: Telegram's own peer-colour gradients (top -> bottom) ---- */
const AVATAR_COLORS = [
  ['#FF885E', '#FF516A'], ['#FFCD6A', '#FFA85C'], ['#82B1FF', '#665FFF'], ['#A0DE7E', '#54CB68'],
  ['#53EDD6', '#28C9B7'], ['#72D5FD', '#2A9EF1'], ['#E0A2F3', '#D669ED'],
];
const initials = (name) => {
  const w = String(name || '?').replace(/[^\p{L}\p{N} ]/gu, '').trim().split(/\s+/).filter(Boolean);
  return ((w[0] ? Array.from(w[0])[0] : '?') + (w[1] ? Array.from(w[1])[0] : '')).toUpperCase();
};

/* ============================================================================================
 * 2. API CLIENT  (same contract as bot/api.py: X-Init-Data auth, retries, ApiErr)
 * ========================================================================================== */
class ApiErr extends Error {
  constructor(status, code, message, network) {
    super(message);
    this.status = status; this.code = code; this.network = !!network;
  }
}

/** Hooks wired up by <App/> so the plain functions below can report auth + connectivity. */
const hooks = { authFail: () => {}, online: () => {} };

const initData = () => {
  const tg = getTg();
  if (tg && tg.initData) return tg.initData;
  // Dev convenience (vite dev only): http://localhost:5173/?initData=<printed by tools/devserver.py>
  return import.meta.env.DEV ? new URLSearchParams(window.location.search).get('initData') || '' : '';
};

async function api(method, path, body, opt = {}) {
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
      let data = null;
      try { data = await res.json(); } catch (_) { /* non-JSON body */ }
      if (res.ok && data && data.ok) { hooks.online(true); return data; }
      const err = new ApiErr(res.status, (data && data.error) || 'http', (data && data.message) || 'Request failed', false);
      if ([429, 502, 503, 504].includes(res.status) && attempt < retries) {
        attempt += 1;
        await sleep(Math.max((Number(res.headers.get('Retry-After')) || 0) * 1000, 400 * 2 ** attempt));
        continue;
      }
      if (res.status === 401) hooks.authFail(err);
      throw err;
    } catch (e) {
      clearTimeout(timer);
      if (e instanceof ApiErr) throw e;
      hooks.online(false);
      if (attempt < retries) { attempt += 1; await sleep(400 * 2 ** attempt); continue; }
      throw new ApiErr(0, 'network', 'No connection. Your changes are kept and will sync.', true);
    }
  }
}

function uploadMedia(file, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/media');
    xhr.setRequestHeader('X-Init-Data', initData());
    xhr.setRequestHeader('X-File-Name', encodeURIComponent(file.name || 'file'));
    xhr.setRequestHeader('Content-Type', file.type || 'application/octet-stream');
    xhr.timeout = 5 * 60 * 1000;
    xhr.upload.onprogress = (e) => { if (e.lengthComputable) onProgress(e.loaded / e.total); };
    xhr.onload = () => {
      let d = null;
      try { d = JSON.parse(xhr.responseText); } catch (_) { /* ignore */ }
      if (xhr.status >= 200 && xhr.status < 300 && d && d.ok) return resolve(d);
      return reject(new ApiErr(xhr.status, (d && d.error) || 'http', (d && d.message) || 'Upload failed. Try again.', false));
    };
    xhr.onerror = () => reject(new ApiErr(0, 'network', 'Upload interrupted. Check your connection and retry.', true));
    xhr.ontimeout = xhr.onerror;
    xhr.send(file);
  });
}

/* ============================================================================================
 * 3. THEME
 *    Surfaces follow the spec palette (light #F4F4F5/#FFF/#E4E4E7 · dark #09090B/#18181B/#27272A).
 *    Text, hint, accent and destructive colours come from Telegram's live theme (themeParams /
 *    --tg-theme-* variables) and fall back to Telegram Blue #2481CC. Values are stored as
 *    "r g b" triplets so Tailwind opacity modifiers work (bg-accent/10, border-hint/40 …).
 * ========================================================================================== */
const THEME_CSS = `
:root{
  --bg:244 244 245; --card:255 255 255; --line:228 228 231; --fill:244 244 245;
  --tx:9 9 11; --hint:113 113 122; --accent:36 129 204; --accent-fg:255 255 255;
  --danger:229 72 77; --ok:52 199 89;
}
.dark{
  --bg:9 9 11; --card:24 24 27; --line:39 39 42; --fill:39 39 42;
  --tx:250 250 250; --hint:161 161 170; --danger:255 99 99;
}
html,body,#root{margin:0;height:100%;}
body{background:rgb(var(--bg));color:rgb(var(--tx));-webkit-tap-highlight-color:transparent;overscroll-behavior:none;
  -webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility;}
/* Safe areas: env() for iOS notch/home bar, --tg-* vars injected by telegram-web-app.js (fullscreen, Bot API 8+) */
.safe-t{padding-top:calc(max(env(safe-area-inset-top),var(--tg-safe-area-inset-top,0px)) + var(--tg-content-safe-area-inset-top,0px));}
.safe-b{padding-bottom:max(env(safe-area-inset-bottom),var(--tg-safe-area-inset-bottom,0px));}
.sheet-foot{padding-bottom:calc(12px + max(env(safe-area-inset-bottom),var(--tg-safe-area-inset-bottom,0px)));}
.no-scrollbar{scrollbar-width:none;} .no-scrollbar::-webkit-scrollbar{display:none;}
/* Rich-text editor + preview (matches what Telegram renders) */
.rich:empty:before{content:attr(data-ph);color:rgb(var(--hint));pointer-events:none;}
.rich{caret-color:rgb(var(--accent));word-break:break-word;white-space:pre-wrap;-webkit-user-select:text;user-select:text;}
.rich code,.rich pre{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.92em;background:rgb(var(--hint)/.18);border-radius:5px;padding:1px 5px;}
.rich a{color:rgb(var(--accent));text-decoration:none;}
.rich tg-spoiler{background:rgb(var(--hint)/.28);border-radius:4px;padding:0 2px;}
.rich blockquote{margin:4px 0;padding:2px 0 2px 10px;border-left:3px solid rgb(var(--accent));border-radius:2px;}
@keyframes pm-up{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}
@keyframes pm-toast{from{opacity:0;transform:translateY(-12px) scale(.96)}to{opacity:1;transform:none}}
.pm-up{animation:pm-up .28s ease-out both;} .pm-toast{animation:pm-toast .22s ease-out both;}
@media (prefers-reduced-motion:reduce){.pm-up,.pm-toast{animation:none;}}
`;

const hexToTriplet = (hex) => {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex || '');
  if (!m) return null;
  const n = parseInt(m[1], 16);
  return `${(n >> 16) & 255} ${(n >> 8) & 255} ${n & 255}`;
};

function applyTheme() {
  const tg = getTg();
  const dark = tg && tg.colorScheme ? tg.colorScheme === 'dark' : window.matchMedia('(prefers-color-scheme: dark)').matches;
  const root = document.documentElement;
  root.classList.toggle('dark', dark);
  const p = (tg && tg.themeParams) || {};
  const set = (name, hex) => { const t = hexToTriplet(hex); if (t) root.style.setProperty(name, t); else root.style.removeProperty(name); };
  set('--tx', p.text_color); set('--hint', p.hint_color);
  set('--accent', p.button_color); set('--accent-fg', p.button_text_color);
  set('--danger', p.destructive_text_color);
  const bg = dark ? '#09090B' : '#F4F4F5';
  const meta = document.querySelector('meta[name=theme-color]');
  if (meta) meta.content = bg;
  try { tg?.setHeaderColor?.(bg); tg?.setBackgroundColor?.(bg); tg?.setBottomBarColor?.(dark ? '#18181B' : '#FFFFFF'); } catch (_) { /* old client */ }
}

/* ============================================================================================
 * 4. UI KIT  (telegram-ui anatomy: Section · Cell · Switch · Chip · Segmented · Sheet)
 * ========================================================================================== */

/** Tactile press feedback used by EVERY interactive element. */
const PRESS = 'active:scale-[0.97] transition-all duration-150';

const AppCtx = createContext(null);
const useApp = () => useContext(AppCtx);

/** Solid colour tiles à la iOS Settings (white glyph on a saturated rounded square). */
const TILE = { blue: '#2481CC', green: '#34C759', orange: '#FF9500', indigo: '#6366F1', red: '#FF3B30', gray: '#8E8E93', pink: '#FF2D55' };

function IconTile({ icon: Icon, color = 'blue', size = 32 }) {
  return (
    <span className="grid shrink-0 place-items-center rounded-[9px] text-white" style={{ width: size, height: size, background: TILE[color] }}>
      <Icon className="h-[18px] w-[18px]" strokeWidth={2.2} />
    </span>
  );
}

function Avatar({ name, id, photo, size = 44, short = false }) {
  const [broken, setBroken] = useState(false);
  const [c1, c2] = AVATAR_COLORS[Math.abs(Number(id) || 0) % AVATAR_COLORS.length];
  return (
    <span
      className="grid shrink-0 select-none place-items-center overflow-hidden rounded-full font-semibold text-white"
      style={{ width: size, height: size, fontSize: size * 0.38, background: `linear-gradient(180deg,${c1},${c2})` }}
    >
      {photo && !broken
        ? <img src={photo} alt="" referrerPolicy="no-referrer" onError={() => setBroken(true)} className="h-full w-full object-cover" />
        : (short ? Array.from(initials(name))[0] : initials(name))}
    </span>
  );
}

const Spinner = ({ className }) => <LoaderCircle className={cx('animate-spin', className)} />;

/* ---- Buttons ---------------------------------------------------------------------------- */
const BTN = {
  primary: 'bg-accent text-accent-fg',
  soft: 'bg-accent/10 text-accent',
  neutral: 'bg-fill text-tx border border-line',
  danger: 'bg-danger/10 text-danger',
  ghost: 'text-accent',
};

/** `dim` = looks disabled but stays tappable, so we can explain *why* it can't be used yet. */
function Btn({ variant = 'primary', icon: Icon, children, onClick, disabled, dim, block, size = 'md', className, ...rest }) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={(e) => { haptic.tap(); onClick?.(e); }}
      className={cx(
        'inline-flex select-none items-center justify-center gap-2 rounded-xl font-semibold',
        size === 'lg' ? 'h-12 px-5 text-[16px]' : 'h-11 px-4 text-[15px]',
        PRESS, BTN[variant], block && 'w-full', (disabled || dim) && 'opacity-50', disabled && 'pointer-events-none', className,
      )}
      {...rest}
    >
      {Icon && <Icon className="h-[18px] w-[18px]" strokeWidth={2.2} />}
      {children}
    </button>
  );
}

function IconBtn({ icon: Icon, label, onClick, tone = 'neutral', className, stop }) {
  const tones = { neutral: 'bg-fill text-hint', accent: 'bg-accent/10 text-accent', danger: 'bg-danger/10 text-danger' };
  return (
    <button
      type="button"
      aria-label={label}
      onClick={(e) => { if (stop) e.stopPropagation(); haptic.tap(); onClick?.(e); }}
      className={cx('grid h-9 w-9 shrink-0 place-items-center rounded-full', PRESS, tones[tone], className)}
    >
      <Icon className="h-[18px] w-[18px]" strokeWidth={2.2} />
    </button>
  );
}

/* ---- Grouped list (iOS inset grouped) ---------------------------------------------------- */
function Section({ header, action, footer, children, className }) {
  return (
    <section className={cx('mb-6', className)}>
      {(header || action) && (
        <div className="mb-1.5 flex min-h-[28px] items-center gap-2 px-4">
          <h2 className="flex-1 text-[13px] font-medium uppercase tracking-wide text-hint">{header}</h2>
          {action}
        </div>
      )}
      <div className="overflow-hidden rounded-2xl border border-line bg-card">{children}</div>
      {footer && <p className="mt-1.5 px-4 text-[13px] leading-snug text-hint">{footer}</p>}
    </section>
  );
}

/**
 * Cell = one row of a Section. The hairline divider is inset past the leading element, exactly like iOS.
 * Rendered as role="button" (not <button>) so it may safely contain other buttons / switches.
 */
function Cell({ before, title, subtitle, after, onClick, chevron, bold, inset = 16, disabled, className, children }) {
  const interactive = !!onClick && !disabled;
  const fire = (e) => { haptic.tap(); onClick(e); };
  return (
    <div
      role={interactive ? 'button' : undefined}
      tabIndex={interactive ? 0 : undefined}
      onClick={interactive ? fire : undefined}
      onKeyDown={interactive ? (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fire(e); } } : undefined}
      style={{ '--inset': `${inset}px` }}
      className={cx(
        'relative flex min-h-[52px] items-center gap-3 px-4 py-2.5 text-left',
        'after:absolute after:bottom-0 after:left-[var(--inset)] after:right-0 after:h-px after:bg-line last:after:hidden',
        interactive && cx('cursor-pointer select-none active:bg-fill', PRESS),
        disabled && 'opacity-60', className,
      )}
    >
      {before}
      <div className="min-w-0 flex-1">
        {title != null && <div className={cx('truncate text-[16px] leading-tight', bold ? 'font-semibold' : 'font-medium')}>{title}</div>}
        {subtitle != null && <div className="mt-0.5 text-[13px] leading-snug text-hint">{subtitle}</div>}
        {children}
      </div>
      {after}
      {chevron && <ChevronRight className="h-[18px] w-[18px] shrink-0 text-hint/60" strokeWidth={2.4} />}
    </div>
  );
}

/** Small rounded secondary label ("Default", "Channel", "12 chars"…). */
function Badge({ children, tone = 'muted', icon: Icon }) {
  const tones = {
    muted: 'bg-fill text-hint', accent: 'bg-accent/10 text-accent', warn: 'bg-orange-500/10 text-orange-600 dark:text-orange-400',
    danger: 'bg-danger/10 text-danger', ok: 'bg-ok/15 text-green-700 dark:text-ok',
  };
  return (
    <span className={cx('inline-flex items-center gap-1 whitespace-nowrap rounded-md px-1.5 py-[2px] text-[11.5px] font-medium leading-none', tones[tone])}>
      {Icon && <Icon className="h-3 w-3" strokeWidth={2.4} />}{children}
    </span>
  );
}

/* ---- Toggles ----------------------------------------------------------------------------- */
function Switch({ checked, onChange, label }) {
  return (
    <button
      type="button" role="switch" aria-checked={checked} aria-label={label}
      onClick={(e) => { e.stopPropagation(); haptic.tap(); onChange(!checked); }}
      className={cx('relative h-[31px] w-[51px] shrink-0 rounded-full transition-colors duration-200 active:scale-[0.97]', checked ? 'bg-ok' : 'bg-hint/30')}
    >
      <span className={cx('absolute left-[2px] top-[2px] h-[27px] w-[27px] rounded-full bg-white shadow-md transition-transform duration-200', checked && 'translate-x-[20px]')} />
    </button>
  );
}

/** iOS circular checkbox (right edge of selectable cells). Purely visual: the Cell owns the click. */
function SelectDot({ checked, disabled }) {
  return (
    <span
      aria-hidden="true"
      className={cx(
        'grid h-6 w-6 shrink-0 place-items-center rounded-full border-2 transition-all duration-150',
        checked ? 'scale-100 border-accent bg-accent' : 'border-hint/40', disabled && 'opacity-40',
      )}
    >
      <Check className={cx('h-4 w-4 text-accent-fg transition-opacity duration-150', checked ? 'opacity-100' : 'opacity-0')} strokeWidth={3.2} />
    </span>
  );
}

/** Filter pill. */
function Chip({ active, children, onClick, icon: Icon }) {
  return (
    <button
      type="button" aria-pressed={!!active}
      onClick={() => { haptic.tap(); onClick(); }}
      className={cx(
        'inline-flex h-8 shrink-0 items-center gap-1.5 rounded-full border px-3.5 text-[14px] font-medium',
        PRESS, active ? 'border-accent bg-accent text-accent-fg' : 'border-line bg-card text-tx',
      )}
    >
      {Icon && <Icon className="h-3.5 w-3.5" strokeWidth={2.4} />}{children}
    </button>
  );
}

/**
 * Connected segmented control (used by the formatting toolbar).
 * Active segments are SOLID accent with accent-fg text (max contrast). `onMouseDown` preventDefault keeps
 * the editor's text selection alive while tapping a segment.
 */
function Segmented({ items, active = {}, onPress, className }) {
  return (
    <div role="group" className={cx('flex rounded-xl border border-line bg-fill p-0.5', className)}>
      {items.map(({ k, Icon, label }) => {
        const on = !!active[k];
        return (
          <button
            key={k} type="button" aria-label={label} aria-pressed={on} title={label}
            onMouseDown={(e) => e.preventDefault()} onPointerDown={(e) => e.preventDefault()}
            onClick={() => { haptic.tap(); onPress(k); }}
            className={cx(
              'grid h-9 min-w-0 flex-1 place-items-center rounded-[10px]', PRESS,
              on ? 'bg-accent text-accent-fg shadow-sm' : 'text-tx',
            )}
          >
            <Icon className="h-[18px] w-[18px]" strokeWidth={on ? 2.8 : 2.2} />
          </button>
        );
      })}
    </div>
  );
}

const inputCls = 'h-11 w-full rounded-xl border border-line bg-fill px-3 text-[16px] text-tx outline-none transition-colors placeholder:text-hint focus:border-accent';

/* ---- Bottom sheet ------------------------------------------------------------------------ */
const sheetStack = []; // lets Telegram's BackButton / Escape close the top-most sheet

function Sheet({ onClose, dismissable = true, title, subtitle, children, footer }) {
  const [on, setOn] = useState(false);
  const closeRef = useRef(null);
  closeRef.current = () => { if (dismissable) onClose(); };

  useEffect(() => {
    const raf = requestAnimationFrame(() => setOn(true));
    const entry = { close: () => closeRef.current() };
    sheetStack.push(entry);
    const onKey = (e) => { if (e.key === 'Escape' && sheetStack[sheetStack.length - 1] === entry) entry.close(); };
    document.addEventListener('keydown', onKey);
    return () => {
      cancelAnimationFrame(raf);
      document.removeEventListener('keydown', onKey);
      const i = sheetStack.indexOf(entry);
      if (i >= 0) sheetStack.splice(i, 1);
    };
  }, []);

  return (
    <div className="fixed inset-0 z-50 flex items-end" role="dialog" aria-modal="true">
      <div onClick={() => closeRef.current()} className={cx('absolute inset-0 bg-black/40 transition-opacity duration-300', on ? 'opacity-100' : 'opacity-0')} />
      <div className={cx('relative flex max-h-[88%] w-full flex-col rounded-t-3xl border-t border-line bg-card shadow-2xl transition-transform duration-300 ease-out', on ? 'translate-y-0' : 'translate-y-full')}>
        <div className="mx-auto mt-2 h-1 w-9 shrink-0 rounded-full bg-hint/30" />
        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 pb-4 pt-3">
          {title && <h2 className="text-[20px] font-bold leading-tight">{title}</h2>}
          {subtitle && <p className="mt-1.5 text-[14px] leading-snug text-hint">{subtitle}</p>}
          {(title || subtitle) && <div className="h-3" />}
          {children}
        </div>
        {footer && <div className="sheet-foot flex shrink-0 gap-2 border-t border-line px-4 pt-3">{footer}</div>}
      </div>
    </div>
  );
}

function ToastHost({ toasts }) {
  const ICON = { ok: CircleCheck, err: CircleX, warn: TriangleAlert, info: Sparkles };
  const TONE = { ok: 'text-ok', err: 'text-danger', warn: 'text-orange-500', info: 'text-accent' };
  return (
    // Outer layer owns the safe-area inset; inner layer adds 56px (48px header + 8px gap) so toasts never cover the title.
    <div className="safe-t pointer-events-none fixed inset-x-0 top-0 z-[60] px-4" aria-live="polite">
      <div className="flex flex-col items-center gap-2 pt-14">
        {toasts.map((t) => {
          const I = ICON[t.kind] || ICON.info;
          return (
            <div key={t.id} className="pm-toast flex max-w-full items-center gap-2 rounded-2xl border border-line bg-card px-3.5 py-2.5 text-[14px] font-medium shadow-lg">
              <I className={cx('h-[18px] w-[18px] shrink-0', TONE[t.kind])} strokeWidth={2.4} />
              <span className="min-w-0">{t.msg}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function EmptyState({ icon: Icon, title, text, children }) {
  return (
    <div className="flex flex-col items-center px-6 py-14 text-center">
      <span className="mb-4 grid h-16 w-16 place-items-center rounded-full bg-accent/10 text-accent"><Icon className="h-8 w-8" strokeWidth={1.8} /></span>
      <h2 className="text-[20px] font-bold">{title}</h2>
      <p className="mb-5 mt-1.5 max-w-[280px] text-[15px] leading-snug text-hint">{text}</p>
      {children}
    </div>
  );
}

/* ============================================================================================
 * 5. STATE ENGINES (hooks)
 * ========================================================================================== */

function useToasts() {
  const [toasts, setToasts] = useState([]);
  const toast = useCallback((msg, kind = 'info', ms = 3000) => {
    const id = uuid();
    setToasts((t) => [...t.slice(-2), { id, msg, kind }]);
    if (kind === 'ok') haptic.notify('success'); else if (kind === 'err') haptic.notify('error'); else if (kind === 'warn') haptic.notify('warning');
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), ms);
  }, []);
  return [toasts, toast];
}

/**
 * Draft engine – identical guarantees to the previous vanilla app:
 *  • edits are debounced (550 ms) and PUT to /api/draft, one request at a time, latest snapshot wins
 *  • a localStorage copy survives offline / closed app and wins over the server copy on next open
 *  • network + 5xx errors retry with backoff; validation errors (e.g. bad link) roll the buttons back
 */
function useDraft({ initial, userId, setSync, toast }) {
  const [draft, setDraft] = useState(initial);   // `initial` already carries _plain (see <Main/>)
  const [version, setVersion] = useState(0);        // bump => the editor re-hydrates from draft.text
  const [photoUrl, setPhotoUrl] = useState(null);
  const ref = useRef(initial);
  const eng = useRef({ dirty: false, timer: null, inflight: null, failures: 0, lastGood: [] });
  const dep = useRef({}); dep.current = { setSync, toast };
  const lsKey = `pm_pending_${userId || 0}`;

  const commit = useCallback((next) => { ref.current = next; setDraft(next); }, []);
  const patch = useCallback((p) => commit({ ...ref.current, ...p }), [commit]);

  const saveLocal = () => {
    const d = ref.current;
    try { localStorage.setItem(lsKey, JSON.stringify({ text: d.text, buttons: d.buttons, link_preview: d.link_preview })); } catch (_) { /* quota */ }
  };
  const clearLocal = () => { try { localStorage.removeItem(lsKey); } catch (_) { /* ignore */ } };

  const run = async () => {
    const e = eng.current;
    while (e.dirty) {
      e.dirty = false;
      const d = ref.current;
      const snap = { text: d.text, buttons: d.buttons.map((b) => ({ ...b })), link_preview: d.link_preview };
      try {
        const r = await api('PUT', '/api/draft', snap, { retries: 2 });
        patch({ chars: r.draft.chars, splits: r.draft.splits, empty: r.draft.empty });
        e.lastGood = snap.buttons; e.failures = 0;
        if (!e.dirty) { clearLocal(); dep.current.setSync('saved'); }
      } catch (err) {
        if (err.status === 401) return false;
        if (err.network || err.status >= 500 || err.status === 429) {
          e.dirty = true; e.failures += 1;
          dep.current.setSync(err.network ? 'offline' : 'error');
          clearTimeout(e.timer); e.timer = setTimeout(flush, Math.min(1000 * 2 ** e.failures, 10000)); // eslint-disable-line no-use-before-define
          return false;
        }
        if (err.code === 'buttons') patch({ buttons: e.lastGood.map((b) => ({ ...b })) });
        dep.current.toast(err.message, 'err', 4200);
        if (!e.dirty) { dep.current.setSync('error', 'Not saved'); saveLocal(); }
        return false;
      }
    }
    return true;
  };
  const flush = useCallback(() => {
    const e = eng.current;
    clearTimeout(e.timer);
    if (!e.inflight) e.inflight = run().finally(() => { e.inflight = null; });
    return e.inflight;
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const pending = useCallback(() => eng.current.dirty || !!eng.current.inflight, []);
  const touch = useCallback(() => {
    const e = eng.current;
    e.dirty = true; saveLocal(); dep.current.setSync('saving');
    clearTimeout(e.timer); e.timer = setTimeout(flush, 550);
  }, [flush]); // eslint-disable-line react-hooks/exhaustive-deps

  /** Apply a user edit (text / buttons / link_preview) and schedule a sync. */
  const edit = useCallback((p) => { patch(p); touch(); }, [patch, touch]);
  /** Merge server-side metadata (media, counts) without scheduling a sync. */
  const meta = patch;

  const freePhoto = useCallback(() => setPhotoUrl((u) => { if (u) URL.revokeObjectURL(u); return null; }), []);
  const loadPhoto = useCallback(async (type = ref.current.media_type) => {
    freePhoto();
    if (type !== 'photo') return;
    try {
      const res = await fetch('/api/media', { headers: { 'X-Init-Data': initData() }, cache: 'no-store' });
      if (res.ok) setPhotoUrl(URL.createObjectURL(await res.blob()));
    } catch (_) { /* preview is optional */ }
  }, [freePhoto]);

  /** Replace the local draft with the server's (clear / load saved post). */
  const adopt = useCallback((d) => {
    const e = eng.current;
    e.dirty = false; clearTimeout(e.timer); clearLocal();
    commit({ ...ref.current, ...d, _plain: tgClean(d.text || '').plain.length });
    e.lastGood = (d.buttons || []).map((b) => ({ ...b }));
    dep.current.setSync('saved');
    setVersion((v) => v + 1);
    loadPhoto(d.media_type);
  }, [commit, loadPhoto]); // eslint-disable-line react-hooks/exhaustive-deps

  const clear = useCallback(async () => {
    await api('DELETE', '/api/draft', undefined, { retries: 2 });
    adopt({ text: '', buttons: [], media_type: null, media_name: '', empty: true, chars: 0, splits: false });
  }, [adopt]);

  // First mount: recover unsynced edits from a previous session, load the photo preview.
  useEffect(() => {
    eng.current.lastGood = (initial.buttons || []).map((b) => ({ ...b }));
    try {
      const raw = localStorage.getItem(lsKey);
      if (raw) {
        const p = JSON.parse(raw);
        commit({ ...ref.current, text: p.text || '', _plain: tgClean(p.text || '').plain.length, buttons: Array.isArray(p.buttons) ? p.buttons : [], link_preview: p.link_preview !== false });
        eng.current.dirty = true; setVersion((v) => v + 1); flush();
      }
    } catch (_) { clearLocal(); }
    loadPhoto(initial.media_type);
    const onHide = () => { if (document.hidden && eng.current.dirty) flush(); };
    const onPageHide = () => { if (eng.current.dirty) flush(); };
    document.addEventListener('visibilitychange', onHide);
    window.addEventListener('pagehide', onPageHide);
    return () => { document.removeEventListener('visibilitychange', onHide); window.removeEventListener('pagehide', onPageHide); };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const plainLen = draft._plain != null ? draft._plain : draft.chars || 0;
  const isEmpty = !(draft.text && draft.text.trim()) && !draft.media_type && !(draft.buttons && draft.buttons.length);

  return { draft, version, photoUrl, edit, meta, flush, pending, adopt, clear, loadPhoto, freePhoto, plainLen, isEmpty, retryNow: () => { if (eng.current.dirty) flush(); } };
}

/**
 * Chats engine – selection is optimistic, pushed to the server (350 ms debounce, one request at a time).
 */
function useChats({ initial, toast }) {
  const [chats, setChats] = useState(initial);
  const ref = useRef(initial);
  const s = useRef({ timer: null, busy: false, dirty: false });
  const dep = useRef({}); dep.current = { toast };

  const set = useCallback((list) => { const l = Array.isArray(list) ? list : []; ref.current = l; setChats(l); }, []);
  const mutate = useCallback((fn) => set(fn(ref.current)), [set]);

  const reload = useCallback(async (quiet) => {
    try {
      const r = await api('GET', '/api/chats');
      if (s.current.dirty || s.current.busy) return;
      set(r.chats);
    } catch (e) { if (!quiet) dep.current.toast(e.message, 'err'); }
  }, [set]);

  const pushSel = useCallback(async () => {
    const e = s.current;
    if (e.busy) return;
    e.busy = true;
    let failed = false;
    try {
      while (e.dirty) {
        e.dirty = false;
        const ids = ref.current.filter((c) => c.selected).map((c) => c.chat_id);
        try { await api('PUT', '/api/chats/selection', { chat_ids: ids }, { retries: 2 }); } catch (err) {
          if (err.network) { e.dirty = true; await sleep(2000); continue; }
          dep.current.toast(err.message, 'err'); failed = true; break;
        }
      }
    } finally { e.busy = false; }
    if (failed) reload(true);
  }, [reload]);

  const queue = useCallback(() => { const e = s.current; e.dirty = true; clearTimeout(e.timer); e.timer = setTimeout(pushSel, 350); }, [pushSel]);
  const flush = useCallback(async () => {
    const e = s.current;
    clearTimeout(e.timer);
    if (e.dirty) await pushSel();
    while (e.busy) await sleep(30);
  }, [pushSel]);

  useEffect(() => {
    const onHide = () => { if (document.hidden && s.current.dirty) flush(); };
    document.addEventListener('visibilitychange', onHide);
    return () => document.removeEventListener('visibilitychange', onHide);
  }, [flush]);

  const toggle = useCallback((id) => {
    const c = ref.current.find((x) => x.chat_id === id);
    if (!c) return;
    if (!c.can_post && !c.selected) { dep.current.toast('Make the bot an admin there first', 'warn'); return; }
    mutate((l) => l.map((x) => (x.chat_id === id ? { ...x, selected: !x.selected } : x)));
    queue();
  }, [mutate, queue]);

  const setAll = useCallback((fn) => { mutate((l) => l.map((x) => ({ ...x, selected: fn(x) }))); queue(); }, [mutate, queue]);
  const selectAll = useCallback(() => setAll((c) => c.can_post), [setAll]);
  const selectNone = useCallback(() => setAll(() => false), [setAll]);
  const selectDefault = useCallback(() => {
    const d = ref.current.find((c) => c.is_default && c.can_post);
    if (!d) { dep.current.toast('No default group with posting rights', 'warn'); return; }
    setAll((c) => c.chat_id === d.chat_id);
  }, [setAll]);

  const selected = useMemo(() => chats.filter((c) => c.selected && c.can_post), [chats]);

  return { chats, selected, set, reload, flush, toggle, selectAll, selectNone, selectDefault };
}

/* ============================================================================================
 * 6. SCREENS
 * ========================================================================================== */

/** Page wrapper. `pb-36` guarantees the last row can always scroll clear of the docked action bar. */
function Page({ active, children }) {
  return (
    <div className={cx('absolute inset-0 overflow-y-auto overscroll-contain px-4 pb-36 pt-2', !active && 'hidden')}>
      <div className="mx-auto w-full max-w-xl">{children}</div>
    </div>
  );
}

const MEDIA = {
  photo: [ImageIcon, 'Photo'], animation: [Film, 'GIF'], video: [Film, 'Video'], audio: [Music, 'Audio'],
  voice: [Music, 'Voice'], document: [FileIcon, 'File'], sticker: [ImageIcon, 'Sticker'], video_note: [Film, 'Video note'],
};
const BTN_COLORS = ['blue', 'green', 'red', 'plain'];
const BTN_NAME = { blue: 'Blue', green: 'Green', red: 'Red', plain: 'Plain' };
const BTN_BG = { blue: '#3390EC', green: '#2FB344', red: '#E5484D', plain: '#8E8E93' };

/* Toolbar definition: connected segmented control, 4 core marks + 4 extras. */
const FMT_MAIN = [
  { k: 'bold', Icon: Bold, label: 'Bold' }, { k: 'italic', Icon: Italic, label: 'Italic' },
  { k: 'underline', Icon: Underline, label: 'Underline' }, { k: 'code', Icon: Code, label: 'Code' },
];
const FMT_MORE = [
  { k: 'strikeThrough', Icon: Strikethrough, label: 'Strikethrough' }, { k: 'spoiler', Icon: EyeOff, label: 'Spoiler' },
  { k: 'quote', Icon: Quote, label: 'Quote' }, { k: 'link', Icon: Link2, label: 'Link' },
];
const WRAP_TAG = { code: 'code', spoiler: 'tg-spoiler', quote: 'blockquote' };

/* ---------------------------------------------------------------------------------------------
 * COMPOSE
 * ------------------------------------------------------------------------------------------- */
function ComposeScreen({ active }) {
  const { D, limits, toast, setSync, openSheet } = useApp();
  const { draft } = D;
  const ed = useRef(null);
  const fileRef = useRef(null);
  const savedRange = useRef(null);
  const [marks, setMarks] = useState({});
  const [upload, setUpload] = useState(null);                       // { name, p }
  const [form, setForm] = useState(null);                           // null | { text, url, color, err }

  /* Hydrate the contenteditable whenever the draft is replaced from outside (load saved / clear / recover). */
  useEffect(() => { if (ed.current) ed.current.innerHTML = tgClean(D.draft.text).html; }, [D.version]); // eslint-disable-line react-hooks/exhaustive-deps

  /* Reflect the selection's formatting in the segmented control (solid = active). */
  useEffect(() => {
    const inTag = (tag) => {
      const sel = window.getSelection();
      const n = sel && sel.anchorNode;
      const el = n && (n.nodeType === 1 ? n : n.parentElement);
      const hit = el && el.closest(tag);
      return !!(hit && ed.current && ed.current.contains(hit));
    };
    const read = () => {
      if (!ed.current || document.activeElement !== ed.current) return;
      const q = (c) => { try { return document.queryCommandState(c); } catch (_) { return false; } };
      setMarks({
        bold: q('bold'), italic: q('italic'), underline: q('underline'), strikeThrough: q('strikeThrough'),
        code: inTag('code'), spoiler: inTag('tg-spoiler'), quote: inTag('blockquote'),
      });
    };
    document.addEventListener('selectionchange', read);
    return () => document.removeEventListener('selectionchange', read);
  }, []);

  const onInput = () => {
    const c = tgClean(ed.current.innerHTML);
    D.edit({ text: c.html, _plain: c.plain.length });
  };

  /** Toggle a wrapper element (code / spoiler / quote) around the selection – removes it when already inside one. */
  const toggleWrap = (tag, attrs, range) => {
    const sel = window.getSelection();
    const r = range || (sel.rangeCount ? sel.getRangeAt(0) : null);
    if (!r || !ed.current.contains(r.commonAncestorContainer)) { toast('Select some text first', 'info'); return; }
    const n = r.commonAncestorContainer;
    const host = (n.nodeType === 1 ? n : n.parentElement).closest(tag);
    if (host && ed.current.contains(host) && !attrs) {            // unwrap
      const first = host.firstChild; const last = host.lastChild;
      while (host.firstChild) host.parentNode.insertBefore(host.firstChild, host);
      host.remove();
      if (first && last) { const nr = document.createRange(); nr.setStartBefore(first); nr.setEndAfter(last); sel.removeAllRanges(); sel.addRange(nr); }
      onInput(); return;
    }
    if (r.collapsed) { toast('Select some text first', 'info'); return; }
    const el = document.createElement(tag);
    Object.keys(attrs || {}).forEach((k) => el.setAttribute(k, attrs[k]));
    el.appendChild(r.extractContents()); r.insertNode(el);
    sel.removeAllRanges(); const nr = document.createRange(); nr.selectNodeContents(el); sel.addRange(nr);
    onInput();
  };

  const askLink = () => {
    const sel = window.getSelection();
    const r = sel.rangeCount && ed.current.contains(sel.getRangeAt(0).commonAncestorContainer) ? sel.getRangeAt(0).cloneRange() : null;
    if (!r || r.collapsed) { toast('Select the text to link first', 'info'); return; }
    savedRange.current = r;
    openSheet((close) => <LinkSheet onClose={close} onApply={(url) => { close(); ed.current.focus(); toggleWrap('a', { href: url }, savedRange.current); }} />);
  };

  const onFormat = (k) => {
    if (k === 'link') return askLink();
    if (WRAP_TAG[k]) { ed.current.focus(); return toggleWrap(WRAP_TAG[k]); }
    ed.current.focus(); document.execCommand(k, false, null); onInput();
    return undefined;
  };

  /* ---- attachment ---- */
  const onFile = async (e) => {
    const f = e.target.files && e.target.files[0];
    e.target.value = '';
    if (!f) return;
    const max = limits.upload_mb * 1024 * 1024;
    if (!f.size) return toast('That file is empty.', 'err');
    if (f.size > max) return toast(`Files can be up to ${limits.upload_mb} MB.`, 'err');
    setUpload({ name: f.name, p: 0 }); setSync('saving', 'Uploading');
    try {
      await D.flush();
      const r = await uploadMedia(f, (p) => setUpload({ name: f.name, p }));
      D.meta({ media_type: r.draft.media_type, media_name: r.draft.media_name, splits: r.draft.splits, empty: false });
      await D.loadPhoto(r.draft.media_type);
      setSync(D.pending() ? 'saving' : 'saved'); toast('Attached', 'ok', 1800);
    } catch (err) {
      setSync(D.pending() ? 'saving' : (err.network ? 'offline' : 'saved')); toast(err.message, 'err', 4500);
    } finally { setUpload(null); }
    return undefined;
  };
  const removeMedia = async () => {
    try {
      const r = await api('DELETE', '/api/media', undefined, { retries: 1 });
      D.meta({ media_type: null, media_name: '', splits: r.draft.splits, empty: r.draft.empty }); D.freePhoto();
    } catch (err) { toast(err.message, 'err'); }
  };

  /* ---- link buttons ---- */
  const buttons = draft.buttons || [];
  const addButton = () => {
    const text = form.text.replace(/\s+/g, ' ').trim();
    const url = normLink(form.url);
    if (!text) { haptic.notify('error'); return setForm({ ...form, err: 'Give the button a name.' }); }
    if (!url) { haptic.notify('error'); return setForm({ ...form, err: 'Enter a valid link, like example.com or @channel.' }); }
    D.edit({ buttons: [...buttons, { text, url, color: form.color }] });
    setForm(null); haptic.notify('success');
    return undefined;
  };
  const cycle = (i) => D.edit({ buttons: buttons.map((b, j) => (j === i ? { ...b, color: BTN_COLORS[(BTN_COLORS.indexOf(b.color) + 1) % BTN_COLORS.length] } : b)) });

  /* ---- counter ---- */
  const n = D.plainLen; const max = limits.text; const cap = limits.caption;
  let countTone = 'text-hint'; let countHint = '';
  if (n > max) { countTone = 'text-danger'; countHint = 'Too long for Telegram'; }
  else if (draft.media_type && n > cap) { countTone = 'text-orange-500'; countHint = `Sent as 2 messages (caption limit ${cap})`; }
  else if (n > max * 0.9) countTone = 'text-orange-500';

  const clearDraft = () => {
    if (D.isEmpty) { toast('Nothing to clear', 'info', 1600); return; }
    openSheet((close) => (
      <Sheet
        onClose={close} title="Clear this draft?" subtitle="The text, attachment and buttons will be removed. Saved posts are not affected."
        footer={(
          <>
            <Btn variant="neutral" block onClick={close}>Keep</Btn>
            <Btn variant="danger" block onClick={async () => { close(); try { await D.clear(); toast('Draft cleared', 'ok', 1600); } catch (e) { toast(e.message, 'err'); } }}>Clear draft</Btn>
          </>
        )}
      />
    ));
  };

  const mediaMeta = MEDIA[draft.media_type] || MEDIA.document;
  const MediaIcon = mediaMeta[0];

  return (
    <Page active={active}>
      {/* ---------- Message ---------- */}
      <Section header="Message" action={<span className={cx('text-[13px] tabular-nums', countTone)}>{n} / {max}</span>} footer={countHint || undefined}>
        <div className="flex gap-2 border-b border-line p-2.5">
          <Segmented items={FMT_MAIN} active={marks} onPress={onFormat} className="flex-[4]" />
          <Segmented items={FMT_MORE} active={marks} onPress={onFormat} className="flex-[4]" />
        </div>
        <div
          ref={ed} contentEditable suppressContentEditableWarning role="textbox" aria-multiline="true" aria-label="Post text"
          data-ph="Write your post here…" spellCheck onInput={onInput}
          onPaste={(e) => { e.preventDefault(); document.execCommand('insertText', false, (e.clipboardData || window.clipboardData).getData('text/plain')); }}
          onDrop={(e) => e.preventDefault()}
          className="rich min-h-[150px] px-4 py-3.5 text-[17px] leading-[1.4] outline-none"
        />
        {/* Attachment: photo preview card */}
        <div className="border-t border-line p-2.5">
          <input ref={fileRef} type="file" hidden onChange={onFile} />
          {upload ? (
            <div className="flex items-center gap-3 rounded-xl bg-fill p-2.5">
              <span className="grid h-14 w-14 shrink-0 place-items-center rounded-lg bg-accent/10 text-accent"><Spinner className="h-6 w-6" /></span>
              <div className="min-w-0 flex-1">
                <div className="text-[15px] font-semibold">Uploading…</div>
                <div className="truncate text-[13px] text-hint">{upload.name}</div>
                <div className="mt-2 h-1 overflow-hidden rounded-full bg-hint/20"><i className="block h-full rounded-full bg-accent transition-all" style={{ width: `${Math.round(upload.p * 100)}%` }} /></div>
              </div>
            </div>
          ) : draft.media_type ? (
            <div className="flex items-center gap-3 rounded-xl bg-fill p-2.5">
              <span className="grid h-14 w-14 shrink-0 place-items-center overflow-hidden rounded-lg bg-accent/10 text-accent">
                {draft.media_type === 'photo' && D.photoUrl ? <img src={D.photoUrl} alt="" className="h-full w-full object-cover" /> : <MediaIcon className="h-6 w-6" />}
              </span>
              <div className="min-w-0 flex-1">
                <div className="truncate text-[15px] font-semibold">{draft.media_name || mediaMeta[1]}</div>
                <div className="text-[13px] text-hint">{mediaMeta[1]} attached</div>
              </div>
              <IconBtn icon={RefreshCw} label="Replace attachment" tone="accent" onClick={() => fileRef.current.click()} />
              <IconBtn icon={X} label="Remove attachment" tone="danger" onClick={removeMedia} />
            </div>
          ) : (
            <button type="button" onClick={() => { haptic.tap(); fileRef.current.click(); }} className={cx('flex h-12 w-full items-center justify-center gap-2 rounded-xl border border-dashed border-hint/40 text-[15px] font-medium text-accent', PRESS)}>
              <Paperclip className="h-[18px] w-[18px]" strokeWidth={2.2} />Attach photo, video or file
            </button>
          )}
        </div>
      </Section>

      {/* ---------- Link buttons ---------- */}
      <Section header="Link buttons" action={<span className="text-[13px] tabular-nums text-hint">{buttons.length} / {limits.buttons}</span>} footer="Buttons appear under the post and open a link.">
        {buttons.map((b, i) => (
          <Cell
            key={`${b.text}-${i}`} inset={60}
            before={<button type="button" aria-label={`Colour: ${BTN_NAME[b.color]}. Tap to change`} onClick={() => { haptic.tap(); cycle(i); }} className={cx('grid h-8 w-8 shrink-0 place-items-center rounded-full', PRESS)} style={{ background: `${BTN_BG[b.color]}26` }}><i className="block h-3.5 w-3.5 rounded-full" style={{ background: BTN_BG[b.color] }} /></button>}
            title={b.text} subtitle={fmtLabel(b.url)}
            after={<IconBtn icon={Trash2} label="Remove button" tone="danger" onClick={() => D.edit({ buttons: buttons.filter((_, j) => j !== i) })} />}
          />
        ))}
        {form ? (
          <div className="space-y-2.5 p-3">
            <input className={inputCls} maxLength={64} autoComplete="off" placeholder="Button text, e.g. Join channel" value={form.text} onChange={(e) => setForm({ ...form, text: e.target.value, err: '' })} autoFocus />
            <input className={inputCls} inputMode="url" autoCapitalize="off" autoComplete="off" placeholder="Link: https://… or @channel" value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value, err: '' })} />
            <div className="flex flex-wrap gap-2">
              {BTN_COLORS.map((c) => (
                <Chip key={c} active={form.color === c} onClick={() => setForm({ ...form, color: c })}>
                  <i className="block h-2.5 w-2.5 rounded-full ring-2 ring-white/60" style={{ background: BTN_BG[c] }} />{BTN_NAME[c]}
                </Chip>
              ))}
            </div>
            {form.err && <p className="text-[13px] font-medium text-danger">{form.err}</p>}
            <div className="flex gap-2"><Btn variant="neutral" block onClick={() => setForm(null)}>Cancel</Btn><Btn block onClick={addButton}>Add button</Btn></div>
          </div>
        ) : buttons.length >= limits.buttons ? (
          <Cell title="Button limit reached" className="text-hint" />
        ) : (
          <Cell before={<IconTile icon={Plus} color="blue" />} title={<span className="text-accent">Add link button</span>} onClick={() => setForm({ text: '', url: '', color: 'blue', err: '' })} />
        )}
      </Section>

      {/* ---------- Options ---------- */}
      <Section footer="Show a card for the first link in your text.">
        <Cell
          before={<IconTile icon={Link2} color="indigo" />} title="Link preview"
          onClick={() => D.edit({ link_preview: !(draft.link_preview !== false) })}
          after={<Switch label="Link preview" checked={draft.link_preview !== false} onChange={(v) => D.edit({ link_preview: v })} />}
        />
      </Section>

      {/* ---------- Preview ---------- */}
      <Section header="Preview" action={<IconBtn icon={Trash2} label="Clear draft" tone="danger" onClick={clearDraft} className="!h-7 !w-7" />}>
        <PreviewBubble draft={draft} photoUrl={D.photoUrl} />
      </Section>
    </Page>
  );
}

function PreviewBubble({ draft, photoUrl }) {
  const html = useMemo(() => tgClean(draft.text).html, [draft.text]);
  const m = MEDIA[draft.media_type] || MEDIA.document;
  const MIcon = m[0];
  const empty = !html && !draft.media_type;
  return (
    <div className={cx('bg-fill p-3', empty && 'opacity-70')} onClick={(e) => { if (e.target.closest('a')) e.preventDefault(); }}>
      <div className="max-w-[88%] overflow-hidden rounded-2xl rounded-bl-md border border-line bg-card text-[16px] leading-snug shadow-sm">
        {draft.media_type && (
          <div className="grid h-40 place-items-center bg-accent/10 text-accent">
            {draft.media_type === 'photo' && photoUrl ? <img src={photoUrl} alt="" className="h-full w-full object-cover" /> : <MIcon className="h-10 w-10" />}
          </div>
        )}
        {(html || !draft.media_type) && (
          html
            ? <div className="rich px-3 py-2" dangerouslySetInnerHTML={{ __html: html }} />
            : <div className="px-3 py-2 text-hint">Your post will appear here</div>
        )}
      </div>
      {draft.buttons.length > 0 && (
        <div className="mt-1 grid max-w-[88%] gap-1">
          {draft.buttons.map((b, i) => (
            <span key={`${b.text}-${i}`} className="truncate rounded-lg px-3 py-2 text-center text-[14px] font-semibold text-white" style={{ background: BTN_BG[b.color] }}>{b.text}</span>
          ))}
        </div>
      )}
    </div>
  );
}

function LinkSheet({ onClose, onApply }) {
  const [v, setV] = useState('');
  const [err, setErr] = useState('');
  const apply = () => {
    const url = normLink(v);
    if (!url) { setErr('Enter a valid link, like example.com or @channel.'); haptic.notify('error'); return; }
    onApply(url);
  };
  return (
    <Sheet onClose={onClose} title="Add link" subtitle="The selected text will open this address." footer={<Btn block onClick={apply}>Apply link</Btn>}>
      <input className={inputCls} inputMode="url" autoCapitalize="off" autoComplete="off" placeholder="https://example.com or @channel" value={v} autoFocus onChange={(e) => { setV(e.target.value); setErr(''); }} onKeyDown={(e) => { if (e.key === 'Enter') apply(); }} />
      {err && <p className="mt-2 text-[13px] font-medium text-danger">{err}</p>}
    </Sheet>
  );
}

/* ---------------------------------------------------------------------------------------------
 * GROUPS  – iOS grouped list. Cell = avatar · bold title · metadata badges · circular checkbox.
 * ------------------------------------------------------------------------------------------- */
const RIGHTS = 'post_messages+edit_messages+delete_messages';
const deepLink = (bot, kind) => `https://t.me/${bot}${kind === 'channel' ? '?startchannel=pm&admin=' : '?startgroup=pm&admin='}${RIGHTS}`;

function GroupsScreen({ active }) {
  const { C, toast, openSheet } = useApp();
  const { chats, selected } = C;
  const [busy, setBusy] = useState(false);

  /* Which filter pill matches the current selection? (pills are shortcuts, so they reflect state) */
  const postable = chats.filter((c) => c.can_post);
  const def = chats.find((c) => c.is_default && c.can_post);
  const filter = (() => {
    if (!selected.length) return 'none';
    if (def && selected.length === 1 && selected[0].chat_id === def.chat_id && postable.length !== 1) return 'default';
    if (postable.length && selected.length === postable.length) return 'all';
    return null;
  })();

  const refresh = async () => {
    setBusy(true);
    try {
      await C.flush();
      const r = await api('POST', '/api/chats/refresh', {}, { timeout: 45000 });
      C.set(r.chats); toast('Groups updated', 'ok', 1500);
    } catch (e) { toast(e.message, 'err'); } finally { setBusy(false); }
  };

  const addChat = () => openSheet((close) => <AddChatSheet onClose={close} />);
  const menu = (c) => openSheet((close) => <ChatMenuSheet chat={c} onClose={close} />);

  return (
    <Page active={active}>
      <div className="mb-3 flex items-center gap-2 px-1">
        <div className="min-w-0 flex-1">
          <h1 className="text-[28px] font-bold leading-tight tracking-tight">Groups</h1>
          <p className="text-[14px] text-hint" aria-live="polite">
            {chats.length === 0 ? 'No chats linked yet' : selected.length === 0 ? 'Nothing selected' : `${selected.length} of ${chats.length} selected`}
          </p>
        </div>
        <IconBtn icon={RefreshCw} label="Refresh groups" onClick={refresh} className={busy ? '[&_svg]:animate-spin' : ''} />
        <IconBtn icon={Plus} label="Add group or channel" tone="accent" onClick={addChat} />
      </div>

      {chats.length === 0 ? (
        <Section>
          <EmptyState icon={UsersRound} title="No groups yet" text="Add the bot as an admin to any group or channel. It will show up here on its own.">
            <Btn icon={Plus} onClick={addChat}>Add group or channel</Btn>
          </EmptyState>
        </Section>
      ) : (
        <>
          {/* Filter pills */}
          <div className="no-scrollbar -mx-4 mb-4 flex gap-2 overflow-x-auto px-4" role="group" aria-label="Quick select">
            <Chip active={filter === 'all'} onClick={C.selectAll}>All</Chip>
            <Chip active={filter === 'default'} onClick={C.selectDefault} icon={Star}>Default only</Chip>
            <Chip active={filter === 'none'} onClick={C.selectNone}>None</Chip>
          </div>

          <Section footer="Tap a chat to include it. Tap ⋯ for more options.">
            {chats.map((c) => {
              const on = c.selected && c.can_post;
              return (
                <Cell
                  key={c.chat_id} inset={72} onClick={() => C.toggle(c.chat_id)} disabled={false}
                  className={cx(!c.can_post && 'opacity-70')}
                  before={<Avatar name={c.title} id={c.chat_id} size={44} />}
                  title={<span className="flex items-center gap-1.5"><span className="truncate">{c.title}</span></span>}
                  bold
                  subtitle={(
                    <span className="mt-1 flex flex-wrap items-center gap-1.5">
                      <Badge icon={c.type === 'channel' ? Megaphone : UsersRound}>{typeName(c.type)}</Badge>
                      {c.username && <span className="text-[13px] text-hint">@{c.username}</span>}
                      {c.is_default && <Badge tone="accent" icon={Star}>Default</Badge>}
                      {!c.can_post && <Badge tone="warn" icon={TriangleAlert}>Bot can't post</Badge>}
                    </span>
                  )}
                  after={(
                    <span className="flex items-center gap-2.5">
                      <button type="button" aria-label={`Options for ${c.title}`} onClick={(e) => { e.stopPropagation(); haptic.tap(); menu(c); }} className={cx('grid h-8 w-8 place-items-center rounded-full text-hint', PRESS)}>
                        <Ellipsis className="h-5 w-5" />
                      </button>
                      <SelectDot checked={on} disabled={!c.can_post} />
                    </span>
                  )}
                />
              );
            })}
          </Section>
        </>
      )}
      {chats.length > 0 && !selected.length && (
        <p className="px-4 text-center text-[13px] text-hint">Pick at least one chat, then press Send.</p>
      )}
    </Page>
  );
}

function ChatMenuSheet({ chat: c, onClose }) {
  const { C, toast } = useApp();
  const [confirm, setConfirm] = useState(false);
  const link = c.username ? `https://t.me/${c.username}` : '';

  const makeDefault = async () => {
    onClose();
    try {
      await C.flush();
      const r = await api('PUT', '/api/chats/default', { chat_id: c.chat_id });
      C.set(r.chats); haptic.notify('success'); toast('Default group updated', 'ok', 1800);
    } catch (e) { toast(e.message, 'err'); }
  };
  const remove = async () => {
    try {
      await C.flush();
      const r = await api('DELETE', `/api/chats/${c.chat_id}`);
      onClose(); C.set(r.chats); toast('Removed', 'ok', 1500);
    } catch (e) { toast(e.message, 'err'); }
  };

  if (confirm) {
    return (
      <Sheet
        onClose={onClose} title={`Remove "${c.title}"?`} subtitle="It only leaves this list. The bot stays in the chat and you can add it back any time."
        footer={<><Btn variant="neutral" block onClick={onClose}>Cancel</Btn><Btn variant="danger" block onClick={remove}>Remove</Btn></>}
      />
    );
  }
  return (
    <Sheet onClose={onClose}>
      <div className="mb-4 flex items-center gap-3">
        <Avatar name={c.title} id={c.chat_id} size={52} />
        <div className="min-w-0">
          <h2 className="truncate text-[20px] font-bold leading-tight">{c.title}</h2>
          <div className="text-[14px] text-hint">{typeName(c.type)}{c.username ? ` · @${c.username}` : ''}</div>
        </div>
      </div>
      {!c.can_post && <p className="mb-3 rounded-xl bg-danger/10 px-3 py-2 text-[13px] font-medium text-danger">The bot can't post here. Give it the "Post messages" right, then tap Refresh.</p>}
      <div className="overflow-hidden rounded-2xl border border-line bg-card">
        {c.is_default
          ? <Cell before={<IconTile icon={Star} color="orange" />} title="This is your default group" />
          : <Cell before={<IconTile icon={Star} color="orange" />} title="Make default" onClick={makeDefault} chevron inset={60} />}
        {link && <Cell before={<IconTile icon={ExternalLink} color="blue" />} title="Open chat" onClick={() => openLink(link)} chevron inset={60} />}
        <Cell before={<IconTile icon={Trash2} color="red" />} title={<span className="text-danger">Remove from list</span>} onClick={() => setConfirm(true)} inset={60} />
      </div>
    </Sheet>
  );
}

function AddChatSheet({ onClose }) {
  const { C, bot, toast } = useApp();
  const [ref, setRef] = useState('');
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);
  const known = useRef(new Set(C.chats.map((c) => c.chat_id)));

  /* Poll while the sheet is open so a chat added through Telegram appears instantly. */
  useEffect(() => {
    const t = setInterval(async () => {
      if (document.hidden) return;
      try {
        const r = await api('GET', '/api/chats', undefined, { retries: 0 });
        const fresh = r.chats.filter((c) => !known.current.has(c.chat_id));
        if (fresh.length) {
          fresh.forEach((c) => known.current.add(c.chat_id));
          C.set(r.chats); toast(`Added ${fresh[0].title}${fresh.length > 1 ? ` +${fresh.length - 1}` : ''}`, 'ok'); onClose();
        }
      } catch (_) { /* keep polling */ }
    }, 2500);
    return () => clearInterval(t);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const addByRef = async () => {
    const v = ref.trim();
    if (!v) { setErr('Enter @username, a t.me link or the chat id.'); haptic.notify('error'); return; }
    setBusy(true); setErr('');
    try {
      await C.flush();
      const r = await api('POST', '/api/chats', { ref: v }, { timeout: 30000 });
      C.set(r.chats);
      const c = r.chats.find((x) => x.chat_id === r.chat_id);
      toast(r.result === 'exists' ? 'Already in your list' : `Added ${c ? c.title : 'chat'}`, 'ok'); onClose();
    } catch (e) { setErr(e.message); haptic.notify('error'); } finally { setBusy(false); }
  };

  return (
    <Sheet onClose={onClose} title="Add a group or channel" subtitle="The bot posts for you, so it needs to be an admin there." footer={<Btn variant="neutral" block onClick={onClose}>Done</Btn>}>
      <div className="overflow-hidden rounded-2xl border border-line bg-card">
        <Cell before={<span className="grid h-7 w-7 place-items-center rounded-full bg-accent text-[14px] font-bold text-accent-fg">1</span>} title="Choose your chat" subtitle="Tap Group or Channel below" inset={56} />
        <Cell before={<span className="grid h-7 w-7 place-items-center rounded-full bg-accent text-[14px] font-bold text-accent-fg">2</span>} title="Confirm admin rights" subtitle="Allow “Post messages” for the bot" inset={56} />
        <Cell before={<span className="grid h-7 w-7 place-items-center rounded-full bg-accent text-[14px] font-bold text-accent-fg">3</span>} title="Come back here" subtitle="It appears automatically" inset={56} />
      </div>
      {bot && (
        <div className="mt-3 grid grid-cols-2 gap-2">
          <Btn icon={UsersRound} onClick={() => openLink(deepLink(bot, 'group'))}>Group</Btn>
          <Btn icon={Megaphone} onClick={() => openLink(deepLink(bot, 'channel'))}>Channel</Btn>
        </div>
      )}
      <div className="my-4 flex items-center gap-3 text-[12px] font-medium uppercase tracking-wide text-hint"><i className="h-px flex-1 bg-line" />or add by username<i className="h-px flex-1 bg-line" /></div>
      <div className="flex gap-2">
        <input className={inputCls} placeholder="@channel or t.me/link" autoCapitalize="off" autoComplete="off" inputMode="url" value={ref} onChange={(e) => { setRef(e.target.value); setErr(''); }} onKeyDown={(e) => { if (e.key === 'Enter') addByRef(); }} />
        <Btn variant="soft" onClick={addByRef} disabled={busy}>{busy ? <Spinner className="h-4 w-4" /> : 'Add'}</Btn>
      </div>
      {err && <p className="mt-2 text-[13px] font-medium text-danger">{err}</p>}
      <p className="mt-3 flex items-center gap-2 text-[13px] text-hint"><span className="h-2 w-2 animate-pulse rounded-full bg-accent" />Waiting for the bot to be added…</p>
    </Sheet>
  );
}

/* ---------------------------------------------------------------------------------------------
 * SAVED  – drafts as list cells with Edit (load into composer) + Delete actions
 * ------------------------------------------------------------------------------------------- */
const SAVED_ICON = { photo: ImageIcon, animation: Film, video: Film, audio: Music, voice: Music, document: FileIcon };

function SavedScreen({ active }) {
  const { saved, setSaved, limits, D, toast, openSheet, go } = useApp();

  const edit = async (p) => {
    const go_ = async () => {
      const r = await api('POST', `/api/posts/${p.id}/load`, {});
      D.adopt(r.draft); haptic.notify('success'); toast('Opened in editor', 'ok', 1500); go('compose');
    };
    try {
      if (D.pending()) await D.flush();
      if (D.isEmpty) { await go_(); return; }
      openSheet((close) => (
        <Sheet
          onClose={close} title="Replace your draft?" subtitle="Your current draft will be replaced by this saved post. Save it first if you want to keep it."
          footer={(
            <>
              <Btn variant="neutral" block onClick={close}>Cancel</Btn>
              <Btn block onClick={async () => { try { await go_(); close(); } catch (e) { toast(e.message, 'err'); } }}>Replace</Btn>
            </>
          )}
        />
      ));
    } catch (e) { toast(e.message, 'err'); }
  };

  const del = (p) => openSheet((close) => (
    <Sheet
      onClose={close} title={`Delete "${p.name}"?`} subtitle="This can't be undone."
      footer={(
        <>
          <Btn variant="neutral" block onClick={close}>Cancel</Btn>
          <Btn variant="danger" block onClick={async () => {
            try { const r = await api('DELETE', `/api/posts/${p.id}`); setSaved(r.posts); close(); toast('Deleted', 'ok', 1400); } catch (e) { toast(e.message, 'err'); }
          }}
          >Delete
          </Btn>
        </>
      )}
    />
  ));

  const saveDraft = () => {
    if (D.isEmpty) { haptic.notify('warning'); toast('Write something first', 'warn'); return; }
    openSheet((close) => <SaveSheet onClose={close} />);
  };

  return (
    <Page active={active}>
      <div className="mb-3 flex items-center gap-2 px-1">
        <div className="min-w-0 flex-1">
          <h1 className="text-[28px] font-bold leading-tight tracking-tight">Saved</h1>
          <p className="text-[14px] text-hint">{saved == null ? 'Loading…' : `${saved.length} / ${limits.saved} drafts`}</p>
        </div>
        <IconBtn icon={Save} label="Save current draft" tone="accent" onClick={saveDraft} />
      </div>

      {saved == null && (
        <Section>{[0, 1, 2].map((i) => <div key={i} className="m-3 h-14 animate-pulse rounded-xl bg-fill" />)}</Section>
      )}
      {saved != null && saved.length === 0 && (
        <Section>
          <EmptyState icon={Bookmark} title="Nothing saved" text="Save a post you use often, then reuse it in one tap.">
            <Btn icon={Save} onClick={saveDraft}>Save current draft</Btn>
          </EmptyState>
        </Section>
      )}
      {saved != null && saved.length > 0 && (
        <Section footer="Edit loads a draft into the composer. Your current draft is never replaced without asking.">
          {saved.map((p) => {
            const I = SAVED_ICON[p.media_type] || Type;
            return (
              <div key={p.id} className="relative px-4 py-3 after:absolute after:bottom-0 after:left-[68px] after:right-0 after:h-px after:bg-line last:after:hidden">
                <div className="flex items-start gap-3">
                  <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-accent/10 text-accent"><I className="h-5 w-5" strokeWidth={2} /></span>
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-[16px] font-semibold leading-tight">{p.name}</div>
                    <p className="mt-0.5 line-clamp-2 text-[14px] leading-snug text-hint">{p.preview || <i>No text</i>}</p>
                    <div className="mt-2 flex flex-wrap items-center gap-1.5">
                      <Badge>{p.chars} chars</Badge>
                      {p.buttons > 0 && <Badge icon={Link2}>{plural(p.buttons, 'button', 'buttons')}</Badge>}
                      {p.media_type && <Badge icon={SAVED_ICON[p.media_type] || FileIcon}>{p.media_type}</Badge>}
                      <span className="text-[12px] text-hint">{ago(p.updated_at)}</span>
                    </div>
                  </div>
                </div>
                <div className="mt-3 flex gap-2 pl-14">
                  <Btn variant="soft" icon={Pencil} onClick={() => edit(p)} className="!h-9 flex-1 !text-[14px]">Edit</Btn>
                  <Btn variant="danger" icon={Trash2} onClick={() => del(p)} className="!h-9 flex-1 !text-[14px]">Delete</Btn>
                </div>
              </div>
            );
          })}
        </Section>
      )}
    </Page>
  );
}

function SaveSheet({ onClose }) {
  const { D, setSaved, toast } = useApp();
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const save = async () => {
    setBusy(true);
    try {
      if (D.pending()) await D.flush();
      if (D.pending()) throw new Error('Your draft is still syncing. Try again in a moment.');
      const r = await api('POST', '/api/posts', { name: name.trim() });
      setSaved(r.posts); onClose(); toast(r.updated ? 'Saved post updated' : 'Saved', 'ok', 1800);
    } catch (e) { setBusy(false); toast(e.message, 'err'); }
  };
  return (
    <Sheet
      onClose={onClose} title="Save this post" subtitle="Give it a name so you can find it later."
      footer={<><Btn variant="neutral" block onClick={onClose}>Cancel</Btn><Btn block onClick={save} disabled={busy}>Save</Btn></>}
    >
      <input className={inputCls} maxLength={60} autoComplete="off" placeholder="e.g. Weekly update" value={name} autoFocus onChange={(e) => setName(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') save(); }} />
    </Sheet>
  );
}

/* ---------------------------------------------------------------------------------------------
 * PROFILE – avatar banner · 2×2 bento stats · list-cell settings
 * ------------------------------------------------------------------------------------------- */
function StatCard({ icon: Icon, value, label, i }) {
  return (
    <div className="pm-up relative overflow-hidden rounded-2xl border border-line bg-card p-4" style={{ animationDelay: `${i * 50}ms` }}>
      <Icon className="absolute right-3.5 top-3.5 h-[22px] w-[22px] text-hint/50" strokeWidth={1.8} />
      <div className="text-[34px] font-extrabold leading-none tracking-tight tabular-nums">{value}</div>
      <div className="mt-2 text-[13px] font-medium text-hint">{label}</div>
    </div>
  );
}

function ProfileScreen({ active }) {
  const { user, chats, saved, storage, go, hapticsOn, setHapticsOn, theme } = useApp();
  const def = chats.find((c) => c.is_default);
  const cloud = storage === 'supabase';
  const name = fullName(user);

  return (
    <Page active={active}>
      {/* Avatar banner */}
      <div className="mb-4 overflow-hidden rounded-2xl border border-line bg-card">
        <div className="h-20 bg-gradient-to-br from-accent/90 to-accent/50" aria-hidden="true" />
        <div className="-mt-11 flex flex-col items-center px-4 pb-5">
          <span className="rounded-full bg-card p-1"><Avatar name={name} id={user.id} photo={user.photo_url} size={80} /></span>
          <h1 className="mt-2 flex items-center gap-1.5 text-[22px] font-bold leading-tight">
            {name}{user.is_premium && <BadgeCheck className="h-5 w-5 text-accent" aria-label="Telegram Premium" />}
          </h1>
          <div className="text-[14px] text-hint">{user.username ? `@${user.username}` : 'No username'}</div>
        </div>
      </div>

      {/* 2×2 bento stats */}
      <div className="mb-6 grid grid-cols-2 gap-3">
        <StatCard i={0} icon={Send} value={fmtNum(user.posts_created)} label="Posts sent" />
        <StatCard i={1} icon={Check} value={fmtNum(user.deliveries)} label="Deliveries" />
        <StatCard i={2} icon={UsersRound} value={fmtNum(chats.length)} label="Groups" />
        <StatCard i={3} icon={Bookmark} value={fmtNum(saved ? saved.length : user.saved)} label="Saved" />
      </div>

      {/* Settings list */}
      <Section header="Account">
        <Cell before={<IconTile icon={Star} color="orange" />} title="Default group" after={<span className="max-w-[45%] truncate text-[15px] text-hint">{def ? def.title : 'None yet'}</span>} />
        <Cell before={<IconTile icon={Hash} color="gray" />} title="Telegram ID" after={<span className="text-[15px] tabular-nums text-hint">{user.id}</span>} />
        <Cell before={<IconTile icon={Crown} color="pink" />} title="Plan" after={<span className="text-[15px] text-hint">{user.is_premium ? 'Telegram Premium' : 'Standard'}</span>} />
      </Section>

      <Section header="Preferences" footer={cloud ? undefined : "Cloud storage isn't connected, so drafts and groups reset when the server restarts."}>
        <Cell
          before={<IconTile icon={cloud ? Cloud : CloudOff} color={cloud ? 'green' : 'orange'} />} title="Sync"
          after={<Badge tone={cloud ? 'ok' : 'warn'}>{cloud ? 'Cloud' : 'Temporary'}</Badge>}
        />
        <Cell
          before={<IconTile icon={Sparkles} color="indigo" />} title="Haptic feedback" onClick={() => setHapticsOn(!hapticsOn)}
          after={<Switch label="Haptic feedback" checked={hapticsOn} onChange={setHapticsOn} />}
        />
        <Cell before={<IconTile icon={ShieldCheck} color="blue" />} title="Appearance" after={<span className="text-[15px] capitalize text-hint">{theme} · follows Telegram</span>} />
      </Section>

      <Section>
        <Cell before={<IconTile icon={UsersRound} color="blue" />} title="Manage groups" chevron onClick={() => go('groups')} inset={60} />
        <Cell before={<IconTile icon={Bookmark} color="indigo" />} title="Saved drafts" chevron onClick={() => go('saved')} inset={60} />
        <Cell before={<IconTile icon={X} color="gray" />} title="Close app" onClick={() => { try { getTg()?.close(); } catch (_) { /* browser */ } }} inset={60} />
      </Section>
    </Page>
  );
}

/* ============================================================================================
 * 7. APP SHELL  (header · stage · docked action bar · bottom nav · sheets · send flow · boot)
 * ========================================================================================== */
const TABS = [
  { k: 'compose', label: 'Compose', Icon: SquarePen },
  { k: 'groups', label: 'Groups', Icon: UsersRound },
  { k: 'saved', label: 'Saved', Icon: Bookmark },
  { k: 'profile', label: 'Profile', Icon: UserRound },
];

const SYNC = {
  saved: [Cloud, 'Synced', 'text-hint'], saving: [LoaderCircle, 'Saving', 'text-accent'],
  error: [TriangleAlert, 'Retrying', 'text-orange-500'], offline: [CloudOff, 'Offline', 'text-orange-500'],
};

function SyncChip({ sync }) {
  const [Icon, label, tone] = SYNC[sync.s] || SYNC.saved;
  return (
    <div role="status" aria-live="polite" className={cx('flex h-7 items-center gap-1.5 rounded-full bg-fill px-2.5 text-[12px] font-medium', tone)}>
      <Icon className={cx('h-3.5 w-3.5', sync.s === 'saving' && 'animate-spin')} strokeWidth={2.4} />{sync.label || label}
    </div>
  );
}

/* ---------------------------------------------------------------------------------------------
 * ACTION BAR – "N chats | Send".
 * Absolutely positioned at the bottom edge of the *stage*, which ends where the bottom nav begins,
 * so it is docked directly above the nav and can never overlap it. Glass backdrop per spec.
 * ------------------------------------------------------------------------------------------- */
function ActionBar({ visible, selected, chatCount, ready, onSend, onTargets }) {
  let title; let sub;
  if (!chatCount) { title = 'No groups yet'; sub = 'Tap to add one'; }
  else if (!selected.length) { title = 'Choose where to send'; sub = 'Tap to pick groups'; }
  else if (selected.length === 1) { title = selected[0].title; sub = typeName(selected[0].type); }
  else { title = plural(selected.length, 'chat', 'chats'); sub = selected.slice(0, 2).map((c) => c.title).join(', ') + (selected.length > 2 ? '…' : ''); }

  return (
    <div
      inert={!visible ? '' : undefined} aria-hidden={!visible}
      className={cx('pointer-events-none absolute inset-x-0 bottom-0 z-30 px-3 pb-2 transition-all duration-200', visible ? 'translate-y-0 opacity-100' : 'translate-y-4 opacity-0')}
    >
      <div className="pointer-events-auto mx-auto flex max-w-xl items-center gap-2 rounded-2xl border border-slate-200/60 bg-white/80 p-2 shadow-lg shadow-black/5 backdrop-blur-lg dark:border-zinc-800 dark:bg-zinc-900/80">
        <button
          type="button" aria-label="Choose groups" onClick={() => { haptic.tap(); onTargets(); }}
          className={cx('flex min-w-0 flex-1 items-center gap-2.5 rounded-xl px-1.5 py-1 text-left', PRESS)}
        >
          <span className="flex shrink-0 -space-x-2">
            {selected.length
              ? selected.slice(0, 3).map((c) => <span key={c.chat_id} className="rounded-full ring-2 ring-white dark:ring-zinc-900"><Avatar name={c.title} id={c.chat_id} size={30} short /></span>)
              : <span className="grid h-[30px] w-[30px] place-items-center rounded-full bg-fill text-hint"><UsersRound className="h-4 w-4" /></span>}
          </span>
          <span className="min-w-0 leading-tight">
            <span className="block truncate text-[15px] font-semibold">{title}</span>
            <span className="block truncate text-[12.5px] text-hint">{sub}</span>
          </span>
        </button>
        <Btn icon={Send} dim={!ready} onClick={onSend} size="lg" className="shrink-0 !rounded-xl">Send</Btn>
      </div>
    </div>
  );
}

function BottomNav({ tab, onTab, hidden, groupsBadge }) {
  return (
    <nav
      aria-label="Main" inert={hidden ? '' : undefined}
      className={cx('safe-b z-40 shrink-0 border-t border-line bg-card/90 backdrop-blur-lg', hidden && 'hidden')}
    >
      <div className="mx-auto flex max-w-xl">
        {TABS.map(({ k, label, Icon }) => {
          const on = tab === k;
          return (
            <button
              key={k} type="button" aria-current={on ? 'page' : undefined}
              onClick={() => { haptic.tap(); onTab(k); }}
              className={cx('relative flex h-[52px] flex-1 flex-col items-center justify-center gap-0.5', PRESS, on ? 'text-accent' : 'text-hint')}
            >
              <span className="relative">
                <Icon className="h-[24px] w-[24px]" strokeWidth={on ? 2.5 : 2} />
                {k === 'groups' && groupsBadge > 0 && (
                  <span className="absolute -right-2.5 -top-1.5 grid min-w-[16px] place-items-center rounded-full bg-accent px-1 text-[10px] font-bold leading-[16px] text-accent-fg">{groupsBadge}</span>
                )}
              </span>
              <span className={cx('text-[10.5px] leading-none', on ? 'font-semibold' : 'font-medium')}>{label}</span>
            </button>
          );
        })}
      </div>
    </nav>
  );
}

/* ---------------------------------------------------------------------------------------------
 * SEND FLOW – confirm sheet -> live progress sheet (polls /api/send/{id}) -> retry failed / new post
 * ------------------------------------------------------------------------------------------- */
const RES_ICON = { queued: [Clock, 'text-hint'], sending: [LoaderCircle, 'text-accent'], ok: [CircleCheck, 'text-ok'], failed: [CircleX, 'text-danger'], partial: [TriangleAlert, 'text-orange-500'], unconfirmed: [TriangleAlert, 'text-orange-500'] };
const RES_LABEL = { queued: 'Waiting…', sending: 'Sending…', ok: 'Delivered', failed: 'Failed', partial: 'Partly sent', unconfirmed: 'Not confirmed' };

function ConfirmSheet({ targets, draft, onClose, onSent }) {
  const { toast } = useApp();
  const [busy, setBusy] = useState(false);
  const reqId = useRef(uuid());                                   // reused on retry so the server can dedupe
  const preview = tgClean(draft.text).plain.replace(/\s+/g, ' ');
  const send = async () => {
    setBusy(true);
    try {
      const r = await api('POST', '/api/send', { request_id: reqId.current, chat_ids: targets.map((c) => c.chat_id) }, { retries: 2, timeout: 30000 });
      onClose(); onSent(r.job);
    } catch (e) {
      setBusy(false);
      if (e.code === 'busy') { onClose(); onSent(null, true); return; }
      toast(e.message, 'err', 4200);
      if (!e.network) reqId.current = uuid();
    }
  };
  return (
    <Sheet
      onClose={onClose} title={`Send to ${plural(targets.length, 'chat', 'chats')}?`}
      subtitle={preview ? (preview.length > 120 ? `${preview.slice(0, 120)}…` : preview) : `Your ${draft.media_type || 'post'}`}
      footer={<><Btn variant="neutral" block onClick={onClose}>Cancel</Btn><Btn block icon={Send} onClick={send} disabled={busy}>Send now</Btn></>}
    >
      <div className="overflow-hidden rounded-2xl border border-line bg-card">
        {targets.map((c) => <Cell key={c.chat_id} inset={68} before={<Avatar name={c.title} id={c.chat_id} size={40} />} title={c.title} bold subtitle={typeName(c.type)} />)}
      </div>
    </Sheet>
  );
}

function ProgressSheet({ initial, onClose, onRetry, onNewPost, onDelivered }) {
  const [job, setJob] = useState(initial);
  const [lost, setLost] = useState(false);
  const counted = useRef(false);

  useEffect(() => {
    if (job.done) return undefined;
    let stop = false;
    let misses = 0;
    (async () => {
      while (!stop) {
        await sleep(job.total > 6 ? 1000 : 700);
        if (stop) return;
        try {
          const r = await api('GET', `/api/send/${job.id}`, undefined, { retries: 1 });
          misses = 0; setJob(r.job); if (r.job.done) return;
        } catch (e) {
          if (e.status === 404) { setLost(true); return; }
          misses += 1; if (misses > 40) { setLost(true); return; }
        }
      }
    })();
    return () => { stop = true; };
  }, [job.id, job.done]); // eslint-disable-line react-hooks/exhaustive-deps

  const finished = job.results.filter((r) => !['queued', 'sending'].includes(r.status)).length;
  const frac = job.total ? finished / job.total : 0;
  const retryIds = job.results.filter((r) => r.status === 'failed').map((r) => r.chat_id);
  const allOk = job.done && !job.failed && !job.unconfirmed;
  const canClose = job.done || lost;

  useEffect(() => {
    if (!job.done || counted.current) return;
    counted.current = true;
    const delivered = job.results.filter((r) => r.status === 'ok' || r.status === 'partial').length;
    if (delivered) onDelivered(delivered);
    haptic.notify(allOk ? 'success' : 'warning');
  }, [job.done]); // eslint-disable-line react-hooks/exhaustive-deps

  const R = 26; const CIRC = 2 * Math.PI * R;
  let sub = 'Keep this open or close the app. Sending continues.';
  if (lost) sub = 'Lost track of this send. Check your chats before sending again.';
  else if (job.done) sub = job.unconfirmed ? 'Some chats could not be confirmed. Check them before sending again, to avoid duplicates.' : job.failed ? 'You can retry the ones that failed.' : 'Your post is live in every selected chat.';

  return (
    <Sheet
      dismissable={canClose} onClose={onClose}
      title={job.done ? (job.failed || job.unconfirmed ? 'Finished with issues' : 'Posted!') : 'Sending your post'} subtitle={sub}
      footer={canClose && (
        <>
          {retryIds.length > 0 && <Btn icon={RotateCcw} block onClick={() => onRetry(retryIds)}>Retry {retryIds.length} failed</Btn>}
          {allOk && <Btn icon={Sparkles} block onClick={onNewPost}>New post</Btn>}
          <Btn variant="neutral" block onClick={onClose}>Close</Btn>
        </>
      )}
    >
      <div className="mb-3 flex items-center gap-4 rounded-2xl border border-line bg-card p-4">
        <svg viewBox="0 0 60 60" className="h-[60px] w-[60px] -rotate-90" aria-hidden="true">
          <circle cx="30" cy="30" r={R} fill="none" strokeWidth="6" className="stroke-fill" />
          <circle cx="30" cy="30" r={R} fill="none" strokeWidth="6" strokeLinecap="round" className="stroke-accent transition-all duration-500" strokeDasharray={CIRC} strokeDashoffset={CIRC * (1 - frac)} />
        </svg>
        <div>
          <div className="text-[30px] font-extrabold leading-none tabular-nums">{job.done ? job.ok : finished}<span className="text-[18px] font-semibold text-hint"> / {job.total}</span></div>
          <div className="mt-1 text-[13px] text-hint">{!job.done ? 'Sending…' : job.failed || job.unconfirmed ? `${job.ok} delivered, ${job.failed + job.unconfirmed} need attention` : 'All delivered'}</div>
        </div>
      </div>
      <div className="max-h-[40vh] overflow-y-auto rounded-2xl border border-line bg-card">
        {job.results.map((r) => {
          const [I, tone] = RES_ICON[r.status] || RES_ICON.queued;
          return (
            <Cell
              key={r.chat_id} inset={68} before={<Avatar name={r.title} id={r.chat_id} size={40} />} title={r.title} bold
              subtitle={<span className={r.status === 'failed' || r.status === 'partial' ? 'text-danger' : r.status === 'unconfirmed' ? 'text-orange-500' : ''}>{r.error || RES_LABEL[r.status] || ''}</span>}
              after={(
                <span className="flex items-center gap-2">
                  {r.url && <IconBtn icon={ExternalLink} label="Open message" tone="accent" onClick={() => openLink(r.url)} />}
                  <I className={cx('h-[22px] w-[22px]', tone, r.status === 'sending' && 'animate-spin')} strokeWidth={2.4} />
                </span>
              )}
            />
          );
        })}
      </div>
    </Sheet>
  );
}

/* ---------------------------------------------------------------------------------------------
 * MAIN (rendered once /api/state has loaded)
 * ------------------------------------------------------------------------------------------- */
function Main({ st, onFatal }) {
  const [toasts, toast] = useToasts();
  const [sync, setSyncState] = useState({ s: 'saved', label: '' });
  const [tab, setTab] = useState('compose');
  const [user, setUser] = useState(st.user);
  const [saved, setSaved] = useState(null);
  const [sheets, setSheets] = useState([]);
  const [kb, setKb] = useState(false);
  const [hapticsOn, setHapticsOnState] = useState(haptic.enabled);
  const [theme, setTheme] = useState(document.documentElement.classList.contains('dark') ? 'Dark' : 'Light');
  const { limits, bot, storage } = st;

  const setSync = useCallback((s, label = '') => {
    setSyncState({ s, label });
    try {
      const tg = getTg();
      if (tg && tg.isVersionAtLeast && tg.isVersionAtLeast('6.2')) {
        if (s === 'saving' || s === 'error' || s === 'offline') tg.enableClosingConfirmation(); else tg.disableClosingConfirmation();
      }
    } catch (_) { /* old client */ }
  }, []);

  const initialDraft = useMemo(() => ({ text: '', buttons: [], link_preview: true, media_type: null, media_name: '', ...st.draft, _plain: tgClean(st.draft.text || '').plain.length }), []); // eslint-disable-line react-hooks/exhaustive-deps
  const D = useDraft({ initial: initialDraft, userId: st.user.id, setSync, toast });
  const C = useChats({ initial: st.chats, toast });
  const dRef = useRef(D); dRef.current = D;

  /* ---- sheets ---- */
  const openSheet = useCallback((render) => {
    const id = uuid();
    const close = () => setSheets((s) => s.filter((x) => x.id !== id));
    setSheets((s) => [...s, { id, node: render(close, id), render, close }]);
    return close;
  }, []);

  /* ---- navigation ---- */
  const go = useCallback((k) => { setTab(k); }, []);
  const switchTab = (k) => { if (k !== tab) setTab(k); };

  /* ---- online / auth hooks for the API client ---- */
  useEffect(() => {
    hooks.authFail = (err) => onFatal(err.code === 'expired' ? 'Session expired' : 'Open from Telegram', err.message, 'Close', () => getTg()?.close());
    hooks.online = (on) => { setSyncState((cur) => (!on ? { s: 'offline', label: '' } : cur.s === 'offline' ? { s: dRef.current.pending() ? 'saving' : 'saved', label: '' } : cur)); if (on && dRef.current.pending()) dRef.current.retryNow(); };
    const off = () => hooks.online(false); const on = () => hooks.online(true);
    window.addEventListener('offline', off); window.addEventListener('online', on);
    return () => { window.removeEventListener('offline', off); window.removeEventListener('online', on); };
  }, [onFatal]);

  /* ---- theme + telegram chrome + back button ---- */
  useEffect(() => {
    const tg = getTg();
    const sync_ = () => { applyTheme(); setTheme(document.documentElement.classList.contains('dark') ? 'Dark' : 'Light'); };
    tg?.onEvent?.('themeChanged', sync_);
    const mq = window.matchMedia('(prefers-color-scheme: dark)'); mq.addEventListener?.('change', sync_);
    const onBack = () => { const top = sheetStack[sheetStack.length - 1]; if (top) top.close(); else setTab('compose'); };
    tg?.onEvent?.('backButtonClicked', onBack);
    return () => { tg?.offEvent?.('themeChanged', sync_); tg?.offEvent?.('backButtonClicked', onBack); mq.removeEventListener?.('change', sync_); };
  }, []);
  useEffect(() => {
    try { const b = getTg()?.BackButton; if (b) (tab === 'compose' && !sheets.length ? b.hide() : b.show()); } catch (_) { /* old client */ }
  }, [tab, sheets.length]);

  /* ---- hide the bars while a text field has focus (virtual keyboard) ---- */
  useEffect(() => {
    const isField = (el) => el && el.matches && el.matches('input,textarea,[contenteditable=true]');
    const inn = (e) => { if (isField(e.target)) setKb(true); };
    const out = () => setTimeout(() => { if (!isField(document.activeElement)) setKb(false); }, 120);
    document.addEventListener('focusin', inn); document.addEventListener('focusout', out);
    return () => { document.removeEventListener('focusin', inn); document.removeEventListener('focusout', out); };
  }, []);

  /* ---- lazy data per tab ---- */
  const loadSaved = useCallback(async (quiet) => {
    try { const r = await api('GET', '/api/posts'); setSaved(r.posts); } catch (e) { if (!quiet) toast(e.message, 'err'); setSaved((s) => s || []); }
  }, [toast]);
  useEffect(() => { loadSaved(true); }, [loadSaved]);
  useEffect(() => {
    if (tab === 'groups') C.reload(true);
    if (tab === 'saved') loadSaved(true);
  }, [tab]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const v = () => { if (!document.hidden && tab === 'groups') C.reload(true); };
    document.addEventListener('visibilitychange', v);
    return () => document.removeEventListener('visibilitychange', v);
  }, [tab, C.reload]); // eslint-disable-line react-hooks/exhaustive-deps

  /* ---- send flow ---- */
  const sending = useRef(false);
  const ready = () => {
    if (D.isEmpty) return { ok: false, why: 'Write something or attach a file first' };
    if (D.plainLen > limits.text) return { ok: false, why: 'Your text is too long for Telegram' };
    if (!C.chats.length) return { ok: false, why: 'Add a group or channel first', tab: 'groups' };
    if (!C.selected.length) return { ok: false, why: 'Pick where to send. Open the Groups tab', tab: 'groups' };
    return { ok: true };
  };

  const showProgress = useCallback((job) => {
    openSheet((close) => (
      <ProgressSheet
        key={job.id} initial={job} onClose={close}
        onDelivered={(n) => setUser((u) => ({ ...u, posts_created: u.posts_created + 1, deliveries: u.deliveries + n }))}
        onRetry={async (ids) => {
          try { const r = await api('POST', '/api/send', { request_id: uuid(), chat_ids: ids }, { retries: 0, timeout: 30000 }); close(); showProgress(r.job); } catch (e) { toast(e.message, 'err'); }
        }}
        onNewPost={async () => { try { close(); await dRef.current.clear(); setTab('compose'); } catch (e) { toast(e.message, 'err'); } }}
      />
    ));
  }, [openSheet, toast]);

  const resumeActive = useCallback(async (announce) => {
    try {
      const r = await api('GET', '/api/send/active');
      if (r.job && !r.job.done) { if (announce) toast('Your previous send is still running', 'info'); showProgress(r.job); } else if (announce) toast('Try again in a moment', 'info');
    } catch (_) { /* ignore */ }
  }, [showProgress, toast]);
  useEffect(() => { resumeActive(false); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const onSend = async () => {
    if (sending.current) return;
    const r = ready();
    if (!r.ok) { haptic.notify('warning'); toast(r.why, 'warn'); if (r.tab) setTab(r.tab); return; }
    sending.current = true;
    try {
      await D.flush(); await C.flush();
      if (D.pending()) { haptic.notify('error'); toast('Your draft is still syncing. Try again in a moment.', 'warn'); return; }
      const targets = C.selected;
      openSheet((close) => <ConfirmSheet targets={targets} draft={dRef.current.draft} onClose={close} onSent={(job, busy) => (busy ? resumeActive(true) : showProgress(job))} />);
    } finally { sending.current = false; }
  };

  const setHapticsOn = (v) => { haptic.enabled = v; setHapticsOnState(v); if (v) haptic.tap(); };

  const ctx = { D, C, user, saved, setSaved, limits, bot, storage, chats: C.chats, toast, setSync, openSheet, go, hapticsOn, setHapticsOn, theme };
  const barVisible = (tab === 'compose' || tab === 'groups') && !kb && sheets.length === 0;

  return (
    <AppCtx.Provider value={ctx}>
      <div className="fixed inset-0 flex flex-col bg-bg text-tx">
        {/* Header */}
        <header className="safe-t z-30 shrink-0 border-b border-line bg-card/90 backdrop-blur-lg">
          <div className="mx-auto flex h-12 max-w-xl items-center gap-3 px-4">
            <button type="button" aria-label="Profile" onClick={() => { haptic.tap(); go('profile'); }} className={cx('rounded-full', PRESS)}><Avatar name={fullName(user)} id={user.id} photo={user.photo_url} size={30} /></button>
            <h1 className="flex-1 truncate text-center text-[17px] font-semibold">{TABS.find((t) => t.k === tab).label}</h1>
            <SyncChip sync={sync} />
          </div>
        </header>

        {/* Stage: scroll pages + docked action bar. Ends exactly where the nav begins. */}
        <main className="relative min-h-0 flex-1">
          <ComposeScreen active={tab === 'compose'} />
          <GroupsScreen active={tab === 'groups'} />
          <SavedScreen active={tab === 'saved'} />
          <ProfileScreen active={tab === 'profile'} />
          <ActionBar
            visible={barVisible} selected={C.selected} chatCount={C.chats.length} ready={ready().ok}
            onSend={onSend} onTargets={() => setTab('groups')}
          />
        </main>

        <BottomNav tab={tab} onTab={switchTab} hidden={kb} groupsBadge={C.selected.length} />
      </div>

      {sheets.map((s) => <React.Fragment key={s.id}>{s.node}</React.Fragment>)}
      <ToastHost toasts={toasts} />
    </AppCtx.Provider>
  );
}

/* ---------------------------------------------------------------------------------------------
 * ROOT – boot, auth, fatal screens
 * ------------------------------------------------------------------------------------------- */
function Splash() {
  return (
    <div className="fixed inset-0 grid place-items-center bg-bg">
      <div className="flex flex-col items-center gap-4">
        <span className="grid h-16 w-16 place-items-center rounded-[20px] bg-accent text-accent-fg shadow-lg"><Send className="h-8 w-8" strokeWidth={2.2} /></span>
        <div className="text-[17px] font-semibold">Post Maker</div>
        <Spinner className="h-5 w-5 text-hint" />
      </div>
    </div>
  );
}

function Fatal({ title, msg, label, onAction }) {
  return (
    <div className="fixed inset-0 grid place-items-center bg-bg px-6">
      <EmptyState icon={ShieldCheck} title={title} text={msg}>
        {label && <Btn onClick={onAction}>{label}</Btn>}
      </EmptyState>
    </div>
  );
}

export default function App() {
  const [phase, setPhase] = useState({ k: 'boot' });

  useEffect(() => {
    const tg = getTg();
    try { tg?.ready(); tg?.expand(); tg?.disableVerticalSwipes?.(); } catch (_) { /* browser */ }
    applyTheme();
    const reapply = () => applyTheme();
    tg?.onEvent?.('themeChanged', reapply);

    (async () => {
      if (!initData()) { setPhase({ k: 'fatal', title: 'Open from Telegram', msg: "This app works inside Telegram. Open it from the bot's menu button.", label: 'Close', act: () => tg?.close() }); return; }
      try { const st = await api('GET', '/api/state', undefined, { retries: 4 }); setPhase({ k: 'ready', st }); } catch (e) {
        if (e.status === 401) return;
        setPhase({ k: 'fatal', title: "Can't connect", msg: e.message || 'Check your connection and try again.', label: 'Try again', act: () => window.location.reload() });
      }
    })();
    return () => tg?.offEvent?.('themeChanged', reapply);
  }, []);

  const onFatal = useCallback((title, msg, label, act) => setPhase({ k: 'fatal', title, msg, label, act }), []);

  return (
    <>
      <style>{THEME_CSS}</style>
      {phase.k === 'boot' && <Splash />}
      {phase.k === 'fatal' && <Fatal title={phase.title} msg={phase.msg} label={phase.label} onAction={phase.act} />}
      {phase.k === 'ready' && <Main st={phase.st} onFatal={onFatal} />}
    </>
  );
}
