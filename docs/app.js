/**
 * app.js — Uptime Dashboard (GitHub Pages edition)
 *
 * This dashboard is hosted on GitHub Pages and the status data lives in a
 * DIFFERENT origin (raw.githubusercontent.com), so you MUST paste the full
 * raw URL of your status.json below.
 *
 * Find it in the Actions run log ("Print public status.json URL" step), or build
 * it yourself:
 *   https://raw.githubusercontent.com/<user>/<repo>/<branch>/status.json
 */

// <<< PASTE YOUR status.json RAW URL HERE >>>
const STATUS_URL = 'https://raw.githubusercontent.com/USER/REPO/main/status.json';

const REFRESH_INTERVAL_MS = 30_000;   // 30 seconds

// ── DOM refs ──────────────────────────────────────────────────────────────────
const $banner      = document.getElementById('summary-banner');
const $bannerIcon  = document.getElementById('summary-icon');
const $bannerText  = document.getElementById('summary-text');
const $lastUpdated = document.getElementById('last-updated');
const $cards       = document.getElementById('cards');
const $errorState  = document.getElementById('error-state');
const $refreshBtn  = document.getElementById('refresh-btn');
const $retryBtn    = document.getElementById('error-retry-btn');

// ── State ─────────────────────────────────────────────────────────────────────
let _timer     = null;
let _firstLoad = true;

// ── Entry point ───────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  if (_firstLoad) showSkeletons();
  fetchAndRender();
  scheduleRefresh();
  $refreshBtn.addEventListener('click', onManualRefresh);
  $retryBtn  .addEventListener('click', onManualRefresh);
  document.addEventListener('visibilitychange', onVisibilityChange);
});

// ── Refresh scheduling ─────────────────────────────────────────────────────────
function scheduleRefresh() {
  clearTimeout(_timer);
  _timer = setTimeout(() => { fetchAndRender(); scheduleRefresh(); }, REFRESH_INTERVAL_MS);
}
function onManualRefresh() {
  clearTimeout(_timer);
  fetchAndRender();
  scheduleRefresh();
}
function onVisibilityChange() {
  if (document.visibilityState === 'visible') {
    clearTimeout(_timer);
    fetchAndRender();
    scheduleRefresh();
  }
}

// ── Fetch + render ─────────────────────────────────────────────────────────────
async function fetchAndRender() {
  try {
    // Cache-bust so we always get the latest committed status.json
    const resp = await fetch(STATUS_URL + '?_=' + Date.now(), { cache: 'no-store' });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    if (!Array.isArray(data)) throw new Error('Unexpected JSON shape');
    showData(data);
  } catch (err) {
    console.warn('[uptime] Fetch failed:', err.message);
    showError();
  }
}

// ── Render: data ───────────────────────────────────────────────────────────────
function showData(endpoints) {
  _firstLoad = false;
  hideError();

  const downCount = endpoints.filter(e => e.status === 'DOWN').length;
  if (downCount === 0) {
    setBanner('ok', '✅', 'All systems operational');
  } else {
    const noun = downCount === 1 ? 'system' : 'systems';
    setBanner('degraded', '🔴', `${downCount} ${noun} down`);
  }

  endpoints.forEach(upsertCard);

  const currentNames = new Set(endpoints.map(e => e.name));
  document.querySelectorAll('.card[data-name]').forEach(el => {
    if (!currentNames.has(el.dataset.name)) el.remove();
  });

  $lastUpdated.textContent = 'Updated ' + new Date().toLocaleTimeString();
}

// ── Render: error ──────────────────────────────────────────────────────────────
function showError() {
  if (_firstLoad) {
    $cards.innerHTML = '';
    setBanner('loading', '⏳', 'Loading…');
  }
  $errorState.classList.remove('hidden');
}
function hideError() { $errorState.classList.add('hidden'); }

// ── Skeletons ──────────────────────────────────────────────────────────────────
function showSkeletons(count = 2) {
  $cards.innerHTML = Array.from({ length: count }, () => `
    <div class="skeleton">
      <div class="skeleton-line" style="width:55%"></div>
      <div class="skeleton-line" style="width:80%"></div>
      <div class="skeleton-line"></div>
    </div>`).join('');
}

// ── Card upsert ────────────────────────────────────────────────────────────────
function upsertCard(ep) {
  const id   = 'card-' + slugify(ep.name);
  let   card = document.getElementById(id);
  const isDown = ep.status === 'DOWN';
  const html   = buildCardHTML(ep, isDown);

  if (!card) {
    card = document.createElement('div');
    card.id           = id;
    card.className     = `card card--${isDown ? 'down' : 'up'}`;
    card.dataset.name  = ep.name;
    card.innerHTML     = html;
    $cards.appendChild(card);
  } else {
    const newClass = `card card--${isDown ? 'down' : 'up'}`;
    if (card.className !== newClass) card.className = newClass;
    card.innerHTML = html;
  }
}

function buildCardHTML(ep, isDown) {
  const badgeClass = isDown ? 'badge--down' : 'badge--up';
  const statusText = isDown ? 'DOWN' : 'UP';
  const httpCode   = ep.http_code   != null ? ep.http_code : '—';
  const responseMs = ep.response_ms != null ? `${ep.response_ms} ms` : '—';
  const checked    = ep.last_checked ? timeAgo(ep.last_checked) : '—';
  const since      = ep.since        ? `Since ${timeAgo(ep.since)}` : '';

  return `
    <div class="card-header">
      <span class="card-name">${esc(ep.name)}</span>
      <span class="badge ${badgeClass}"><span class="badge-dot"></span>${statusText}</span>
    </div>
    <div class="card-url">${esc(ep.url)}</div>
    <div class="card-stats">
      <span class="stat"><strong>HTTP</strong> ${httpCode}</span>
      <span class="stat"><strong>Response</strong> ${responseMs}</span>
      <span class="stat"><strong>Checked</strong> ${checked}</span>
      ${since ? `<span class="stat">${esc(since)}</span>` : ''}
    </div>`;
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function setBanner(type, icon, text) {
  $banner.className       = `banner banner--${type}`;
  $bannerIcon.textContent = icon;
  $bannerText.textContent = text;
}
function slugify(s) { return s.toLowerCase().replace(/[^a-z0-9]/g, '-'); }
function esc(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
                  .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
function timeAgo(iso) {
  try {
    const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
    if (diff < 5)     return 'just now';
    if (diff < 60)    return `${diff}s ago`;
    if (diff < 3600)  return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return `${Math.floor(diff / 86400)}d ago`;
  } catch { return iso; }
}
