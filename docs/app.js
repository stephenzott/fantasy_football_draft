// ─────────────────────────────────────────────────────────────────────────
// Firebase (loaded LAZILY, not statically)
// ─────────────────────────────────────────────────────────────────────────
// The Firebase SDK is pulled in via dynamic import() inside initFirebase(),
// not with a static import at the top of the module, on purpose: that way if
// the gstatic CDN is unreachable - or Firebase just isn't configured yet -
// the board degrades to an unsynced view that STILL shows rankings, instead
// of a blank page (a static top-level import that fails would kill the whole
// module). Only the local config file is imported statically; it's always
// present (a committed placeholder until the user fills it in).
import { firebaseConfig } from "./firebase-config.js";

// ─────────────────────────────────────────────────────────────────────────
// Multi-league state
// ─────────────────────────────────────────────────────────────────────────
// The board serves all 5 leagues from this one page. The active league is
// driven by the ?league= URL param, so two tabs can each point at a different
// league independently.
//
// Draft-day state lives in Firebase Realtime Database, scoped by league at
// /leagues/{league_id}/drafted/{player_id}. Firebase is the single source of
// truth: toggleDrafted only WRITES; the `drafted` Set is rebuilt from the
// database snapshot by an onValue listener, which then re-renders. (The RTDB
// SDK applies writes to its local cache and fires the listener immediately,
// before the server round-trip, so the UI stays instant.)

const SEASON = 2026;

let leagues = [];          // [{id, name}], from docs/leagues.json
let allLeaguesData = {};   // { league_id: [player, ...] }, from docs/players.json
let currentLeague = null;  // the active league's id

let allPlayers = [];       // === allLeaguesData[currentLeague]
let drafted = new Set();   // player_ids drafted in the CURRENT league (from Firebase)

let sortCol = 'rank';
let sortDir = 'asc';
let posFilter = 'ALL';
let hideDrafted = false;
let excludeDV = false;
let compactMode = false;   // COMPACT toggle: shrinks rows to rank/name/flag/pos
let searchTerm = '';       // lowercased name-search text; '' = no search
let expanded = new Set();  // player_ids whose source-breakdown row is open
let activePopup = null;

// ── Firebase handles ──
let db = null;             // the Realtime Database instance (null if not configured/loaded)
let fb = null;             // the SDK functions we use { ref, onValue, set, remove }, once loaded
let unsubscribeDrafted = null;  // teardown fn for the current league's onValue listener

// Whether firebase-config.js holds real values (vs the committed placeholder).
// Computed synchronously at module load so it's known from the very FIRST
// render - before the SDK finishes its async load. toggleDrafted relies on
// this: if we're configured but Firebase hasn't connected yet, a local
// in-memory pick would be silently wiped by the first snapshot, so we refuse
// the click instead. A placeholder config makes this false -> intentional
// ephemeral (in-memory) drafting.
const firebaseConfigured =
  !!(firebaseConfig &&
     typeof firebaseConfig.databaseURL === 'string' &&
     firebaseConfig.databaseURL &&
     !firebaseConfig.databaseURL.includes('PASTE'));

// ─────────────────────────────────────────────────────────────────────────
// Firebase wiring
// ─────────────────────────────────────────────────────────────────────────

// Set the little sync-status pill in the subbar. State is one of:
// 'connected' (green), 'disconnected' (red), 'unconfigured' (amber), 'error'.
function setSyncStatus(state) {
  const el = document.getElementById('syncStatus');
  if (!el) return;
  const label = {
    connected: 'SYNCED',
    disconnected: 'OFFLINE',
    unconfigured: 'NOT SYNCED',
    error: 'SYNC ERROR',
  }[state] || '';
  // The CSS class drives the dot color; 'error' reuses the disconnected red.
  el.className = 'sync-status ' + (state === 'error' ? 'disconnected' : state);
  el.textContent = label;
}

// Initialize Firebase IF the config has been filled in. Until firebase-config.js
// has a real databaseURL (the placeholder still contains "PASTE"), we leave db
// null and run in an unsynced, in-memory-only mode - clearly flagged in the
// status pill rather than silently pretending to sync. Async because it
// dynamically imports the SDK; awaited by init() before the drafted listener
// is attached.
async function initFirebase() {
  if (!firebaseConfigured) {
    db = null;
    setSyncStatus('unconfigured');
    return;
  }

  try {
    // Lazy-load the modular SDK from the gstatic CDN only when we actually
    // have a config to use it with.
    const [appMod, dbMod] = await Promise.all([
      import("https://www.gstatic.com/firebasejs/10.12.0/firebase-app.js"),
      import("https://www.gstatic.com/firebasejs/10.12.0/firebase-database.js"),
    ]);
    const app = appMod.initializeApp(firebaseConfig);
    db = dbMod.getDatabase(app);
    fb = { ref: dbMod.ref, onValue: dbMod.onValue, set: dbMod.set, remove: dbMod.remove };
    // Firebase's built-in connection state - flips the status pill live as the
    // connection drops/recovers, so a draft-day outage is visible, not silent.
    fb.onValue(fb.ref(db, '.info/connected'), snap => {
      setSyncStatus(snap.val() ? 'connected' : 'disconnected');
    });
  } catch (err) {
    // A CDN failure or bad config shouldn't blank the board - fall back to
    // unsynced mode (rankings still render, picks are ephemeral).
    console.error('Firebase init failed:', err);
    db = null;
    fb = null;
    setSyncStatus('error');
  }
}

// ─────────────────────────────────────────────────────────────────────────
// Flag helpers
// ─────────────────────────────────────────────────────────────────────────

function conductDotType(flags) {
  if (flags.some(f => f.toLowerCase().includes('domestic violence'))) return 'dv';
  return 'other';
}

function entryType(flagStr) {
  return flagStr.toLowerCase().includes('domestic violence') ? 'dv' : 'other';
}

function buildFlagIndicators(p) {
  const flags = p.flags || [];
  const injuries = p.injuries || [];
  let html = '';
  if (flags.length) {
    const type = conductDotType(flags);
    html += `<span class="flag-indicator flag-dot ${type}"></span>`;
  }
  if (injuries.length) {
    html += `<span class="flag-indicator flag-cross">✚</span>`;
  }
  return html;
}

// ─────────────────────────────────────────────────────────────────────────
// Flag popup
// ─────────────────────────────────────────────────────────────────────────

function showFlagPopup(p, anchor) {
  hidePopup();

  const flags = p.flags || [];
  const injuries = p.injuries || [];
  if (!flags.length && !injuries.length) return;

  const popup = document.createElement('div');
  popup.className = 'flag-popup';

  const conductHtml = flags.map(f => {
    const type = entryType(f);
    const sep = f.indexOf(' — ');
    const incident = sep >= 0 ? f.slice(0, sep) : f;
    const resolution = sep >= 0 ? f.slice(sep + 3) : '';
    return `
      <div class="flag-popup-entry">
        <div class="flag-popup-incident ${type}">${incident}</div>
        ${resolution ? `<div class="flag-popup-resolution">${resolution}</div>` : ''}
      </div>`;
  }).join('');

  const injuryHtml = injuries.map(f => `
    <div class="flag-popup-entry">
      <div class="flag-popup-incident injury">&#10010; ${f}</div>
    </div>`).join('');

  popup.innerHTML = `
    <div class="flag-popup-name">${p.name}</div>
    ${conductHtml}${injuryHtml}
  `;

  document.body.appendChild(popup);

  const rect = anchor.getBoundingClientRect();
  const pw = 300;
  let left = rect.left;
  if (left + pw > window.innerWidth - 8) left = window.innerWidth - pw - 8;
  let top = rect.bottom + 6;
  if (top + 200 > window.innerHeight) top = rect.top - 6 - popup.offsetHeight;

  popup.style.top = top + 'px';
  popup.style.left = left + 'px';

  activePopup = popup;
}

function hidePopup() {
  if (activePopup) { activePopup.remove(); activePopup = null; }
}

// ─────────────────────────────────────────────────────────────────────────
// Rendering
// ─────────────────────────────────────────────────────────────────────────

function getVisible() {
  let list = allPlayers.filter(p => {
    // Name search ANDs with the other filters (search within the current view).
    if (searchTerm && !p.name.toLowerCase().includes(searchTerm)) return false;
    if (posFilter === 'FLEX' && !['RB', 'WR', 'TE'].includes(p.position)) return false;
    if (posFilter !== 'ALL' && posFilter !== 'FLEX' && p.position !== posFilter) return false;
    if (hideDrafted && drafted.has(p.player_id)) return false;
    if (excludeDV && p.flags && p.flags.length > 0) return false;
    return true;
  });

  list.sort((a, b) => {
    let av = a[sortCol], bv = b[sortCol];
    if (typeof av === 'string') { av = av.toLowerCase(); bv = bv.toLowerCase(); }
    if (av < bv) return sortDir === 'asc' ? -1 : 1;
    if (av > bv) return sortDir === 'asc' ? 1 : -1;
    return 0;
  });

  return list;
}

function updateSubbar() {
  const total = allPlayers.length;
  const d = drafted.size;
  document.getElementById('statAvail').textContent = `${total - d} AVAILABLE`;
  document.getElementById('statDrafted').textContent = `${d} DRAFTED`;
}

function render() {
  const tbody = document.getElementById('playerList');
  const board = document.getElementById('board');
  // Toggling this class is what actually drives the compact layout - the CSS
  // rules scoped under `.board.compact` are what hide the team/pos-rank/FPTS/
  // VBD/action columns and relax the table's min-width so it can shrink to
  // phone width without a horizontal scrollbar. See style.css.
  board.classList.toggle('compact', compactMode);
  const players = getVisible();

  if (!players.length) {
    tbody.innerHTML = `<tr><td colspan="6" class="empty-state">NO PLAYERS MATCH FILTER</td></tr>`;
    updateSubbar();
    return;
  }

  const fragment = document.createDocumentFragment();

  players.forEach(p => {
    // Identity is the pipeline-minted player_id (Firebase-safe, stable across
    // rebuilds) - the same key used for the Firebase drafted path.
    const isDrafted = drafted.has(p.player_id);
    const isExpanded = expanded.has(p.player_id);
    const flags = p.flags || [];
    const injuries = p.injuries || [];
    const hasAnyFlag = flags.length > 0 || injuries.length > 0;

    // ── main row ──
    const tr = document.createElement('tr');
    tr.className = `player-row${isDrafted ? ' drafted' : ''}`;
    tr.dataset.id = p.player_id;

    tr.innerHTML = `
      <td class="cell-rk">${p.rank}</td>
      <td>
        <div class="player-name">
          ${p.name}
          ${hasAnyFlag ? buildFlagIndicators(p) : ''}
        </div>
        <div class="player-sub">
          <span class="player-team">${p.team || '—'}</span>
          <span class="player-posrk">${p.pos_rank}</span>
        </div>
      </td>
      <td><span class="pos-badge pos-${p.position}">${p.position}</span></td>
      <td class="cell-pts">${p.projected_points.toFixed(1)}</td>
      <td class="cell-vbd">${p.vbd.toFixed(1)}</td>
      <td class="cell-action">
        <button class="${isDrafted ? 'btn-undo' : 'btn-drafted'}" data-id="${p.player_id}">
          ${isDrafted ? 'UNDO' : 'DRAFTED'}
        </button>
      </td>
    `;

    tr.addEventListener('click', e => {
      if (e.target.closest('button') || e.target.closest('.flag-indicator')) return;
      toggleExpand(p.player_id);
    });

    tr.querySelector('button').addEventListener('click', e => {
      e.stopPropagation();
      toggleDrafted(p.player_id);
    });

    tr.querySelectorAll('.flag-indicator').forEach(el => {
      el.addEventListener('click', e => {
        e.stopPropagation();
        if (activePopup) { hidePopup(); return; }
        showFlagPopup(p, el);
      });
    });

    fragment.appendChild(tr);

    // ── detail row (projection sources only) ──
    const dr = document.createElement('tr');
    dr.className = `detail-row${isExpanded ? ' open' : ''}`;
    dr.dataset.id = p.player_id;

    const sourcesHtml = Object.entries(p.sources)
      .map(([src, pts]) => `
        <div class="source-item">
          <span class="source-label">${src.toUpperCase()}</span>
          <span class="source-val">${pts.toFixed(1)}</span>
        </div>`)
      .join('');

    // In compact mode, the main row hides team/pos-rank/FPTS/VBD and the
    // DRAFTED button (CSS, see .board.compact rules in style.css) to keep
    // rows down to rank/name/flag/position. Nothing is lost, though - those
    // fields + a working DRAFTED/UNDO button are added into this same
    // tap-to-expand detail row that already shows the source breakdown, so a
    // tap still reaches everything. In the normal (non-compact) desktop view
    // this block is simply omitted, since those fields are already visible
    // in the main row.
    const compactExtraHtml = compactMode ? `
      <div class="compact-meta">
        <span class="compact-stat"><span class="compact-stat-label">TEAM</span>${p.team || '—'}</span>
        <span class="compact-stat"><span class="compact-stat-label">POS RK</span>${p.pos_rank}</span>
        <span class="compact-stat"><span class="compact-stat-label">FPTS</span>${p.projected_points.toFixed(1)}</span>
        <span class="compact-stat"><span class="compact-stat-label">VBD</span>${p.vbd.toFixed(1)}</span>
      </div>
      <button class="${isDrafted ? 'btn-undo' : 'btn-drafted'} compact-draft-btn" data-id="${p.player_id}">
        ${isDrafted ? 'UNDO' : 'DRAFTED'}
      </button>
    ` : '';

    dr.innerHTML = `
      <td colspan="6">
        <div class="detail-inner">
          ${compactExtraHtml}
          <div class="sources-grid">${sourcesHtml}</div>
        </div>
      </td>`;

    // The compact DRAFTED/UNDO button only exists in the DOM when compactMode
    // is on (see compactExtraHtml above), so this query naturally no-ops in
    // desktop mode - the main row's own button (wired earlier) already
    // handles that case.
    const compactBtn = dr.querySelector('.compact-draft-btn');
    if (compactBtn) {
      compactBtn.addEventListener('click', e => {
        e.stopPropagation();
        toggleDrafted(p.player_id);
      });
    }

    fragment.appendChild(dr);
  });

  tbody.innerHTML = '';
  tbody.appendChild(fragment);
  updateSubbar();
}

function toggleExpand(id) {
  if (expanded.has(id)) expanded.delete(id);
  else expanded.add(id);
  render();
}

// Toggle a player's drafted state. With Firebase configured this only WRITES;
// the onValue listener (set up in setActiveLeague) rebuilds `drafted` and
// re-renders - one direction of truth, so we never mutate `drafted` here and
// risk a later snapshot silently reverting it. Without Firebase we fall back
// to an ephemeral in-memory toggle (clearly flagged NOT SYNCED in the pill).
function toggleDrafted(id) {
  if (db && fb) {
    // Firebase is up: write only; the onValue listener updates `drafted` and
    // re-renders (fires immediately from local cache, so the UI stays instant).
    const node = fb.ref(db, `leagues/${currentLeague}/drafted/${id}`);
    if (drafted.has(id)) fb.remove(node);   // undo
    else fb.set(node, true);                // draft
  } else if (firebaseConfigured) {
    // Configured, but Firebase hasn't connected yet (still loading) or errored
    // out. Do NOT mutate a local set here: during the load window the first
    // snapshot would wipe the pick (silent loss), and after an error we're in
    // hard-replace mode with no local store to fall back to. Ignore the click
    // - the row visibly doesn't change and the status pill shows why. A pick
    // that doesn't register beats one that registers and then vanishes.
    return;
  } else {
    // No Firebase configured at all: ephemeral in-memory drafting (clearly
    // flagged NOT SYNCED). Lost on refresh - that's the unconfigured mode.
    if (drafted.has(id)) drafted.delete(id);
    else drafted.add(id);
    render();
  }
}

// ─────────────────────────────────────────────────────────────────────────
// Sorting / filters
// ─────────────────────────────────────────────────────────────────────────

function initSorting() {
  document.querySelectorAll('th.sortable').forEach(th => {
    th.addEventListener('click', () => {
      const col = th.dataset.col;
      if (sortCol === col) {
        sortDir = sortDir === 'asc' ? 'desc' : 'asc';
      } else {
        sortCol = col;
        sortDir = col === 'rank' ? 'asc' : 'desc';
      }
      document.querySelectorAll('th.sortable').forEach(t => t.classList.remove('active', 'asc', 'desc'));
      th.classList.add('active', sortDir);
      render();
    });
  });
}

function initFilters() {
  document.getElementById('posFilters').addEventListener('click', e => {
    const btn = e.target.closest('.filter-btn');
    if (!btn) return;
    posFilter = btn.dataset.pos;
    document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    render();
  });

  document.getElementById('hideDrafted').addEventListener('change', e => {
    hideDrafted = e.target.checked;
    render();
  });

  document.getElementById('excludeDV').addEventListener('change', e => {
    excludeDV = e.target.checked;
    render();
  });

  document.getElementById('compactMode').addEventListener('change', e => {
    compactMode = e.target.checked;
    render();
  });

  const searchBox = document.getElementById('searchBox');
  searchBox.addEventListener('input', e => {
    searchTerm = e.target.value.trim().toLowerCase();
    render();
  });
  // Escape clears the search quickly (the input's native clear button also
  // fires 'input', so that path is already handled above).
  searchBox.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
      e.target.value = '';
      searchTerm = '';
      render();
    }
  });
}

document.addEventListener('click', e => {
  if (activePopup && !activePopup.contains(e.target) && !e.target.closest('.flag-indicator')) {
    hidePopup();
  }
});

// ─────────────────────────────────────────────────────────────────────────
// Mobile header: FILTERS dropdown
// ─────────────────────────────────────────────────────────────────────────
// #filtersToggle and the .open class it drives only do anything visually
// below the phone-width media query in style.css - at desktop widths the
// button is display:none and #headerControls is always visible, so this
// wiring is harmless (just unreachable) on a full-size screen.
function initHeaderControls() {
  const filtersToggle = document.getElementById('filtersToggle');
  const headerControls = document.getElementById('headerControls');

  function setOpen(open) {
    headerControls.classList.toggle('open', open);
    filtersToggle.classList.toggle('active', open);
    filtersToggle.setAttribute('aria-expanded', String(open));
  }

  filtersToggle.addEventListener('click', e => {
    e.stopPropagation();  // don't let this bubble into the outside-click handler below
    setOpen(!headerControls.classList.contains('open'));
  });

  // Tapping anywhere outside the open panel (and outside the toggle button
  // itself, already handled above) closes it - standard dropdown behavior.
  document.addEventListener('click', e => {
    if (!headerControls.classList.contains('open')) return;
    if (headerControls.contains(e.target)) return;
    setOpen(false);
  });
}

// ─────────────────────────────────────────────────────────────────────────
// League selection
// ─────────────────────────────────────────────────────────────────────────

function updateTitle() {
  // Distinct per-league tab titles matter: on draft day two tabs are open at
  // once, and identical titles make them impossible to tell apart.
  const lg = leagues.find(l => l.id === currentLeague);
  document.title = (lg ? lg.name : 'Draft Board') + ' · ' + SEASON;
}

// (Re)subscribe the Firebase drafted listener to the CURRENT league's path.
// Called on a league switch and again once Firebase finishes loading (it comes
// up asynchronously, after the first board render).
//
// Tearing down the previous listener first is essential: if we subscribed to
// league_1's drafted node and never unsubscribed, switching to league_2 would
// leave the old listener still writing league_1's data into `drafted` - the
// exact cross-league bleed the multi-league design prevents, reintroduced via
// a stale listener.
function attachDraftedListener() {
  if (unsubscribeDrafted) { unsubscribeDrafted(); unsubscribeDrafted = null; }
  if (!db || !fb) return;  // unsynced mode: nothing to subscribe

  const draftedRef = fb.ref(db, `leagues/${currentLeague}/drafted`);
  unsubscribeDrafted = fb.onValue(draftedRef, snap => {
    // Snapshot is { player_id: true, ... } (or null when nothing drafted).
    // Rebuild `drafted` wholesale from it - Firebase is the source of truth.
    drafted = new Set(Object.keys(snap.val() || {}));
    render();
  });
}

// Point the board at a league: swap in that league's players and re-subscribe
// the drafted listener. Sort/filter/toggles are intentionally left as-is so
// they persist across a switch.
function setActiveLeague(id) {
  currentLeague = id;
  allPlayers = allLeaguesData[id] || [];  // guard: unknown id -> empty board, not a crash
  expanded = new Set();                    // don't carry an expanded row across leagues
  drafted = new Set();                     // reset; the listener repopulates from Firebase
  updateTitle();
  attachDraftedListener();
}

function initLeagueSelect() {
  const sel = document.getElementById('leagueSelect');
  sel.innerHTML = leagues.map(l => `<option value="${l.id}">${l.name}</option>`).join('');
  sel.value = currentLeague;

  sel.addEventListener('change', e => {
    const id = e.target.value;
    // Keep the URL in sync so a refresh or a copied link stays on this league.
    const url = new URL(location);
    url.searchParams.set('league', id);
    history.replaceState(null, '', url);

    setActiveLeague(id);
    render();
  });
}

async function init() {
  try {
    // Fetch both data files once. players.json holds ALL leagues, so switching
    // leagues later just re-indexes what's already in memory - no re-fetch.
    const [leaguesRes, playersRes] = await Promise.all([
      fetch('leagues.json'),
      fetch('players.json'),
    ]);
    if (!leaguesRes.ok) throw new Error('leagues.json: ' + leaguesRes.statusText);
    if (!playersRes.ok) throw new Error('players.json: ' + playersRes.statusText);
    leagues = await leaguesRes.json();
    allLeaguesData = await playersRes.json();
  } catch (err) {
    document.getElementById('playerList').innerHTML =
      `<tr><td colspan="6" class="empty-state">FAILED TO LOAD DATA</td></tr>`;
    console.error(err);
    return;
  }

  if (!leagues.length) {
    document.getElementById('playerList').innerHTML =
      `<tr><td colspan="6" class="empty-state">NO LEAGUES CONFIGURED</td></tr>`;
    return;
  }

  // Resolve the active league from ?league=, validated against known ids. A
  // missing/unknown value falls back to the first league AND is written back
  // into the URL, so the tab is never ambiguous (and a bad ?league= shows an
  // empty board rather than throwing on undefined).
  const validIds = new Set(leagues.map(l => l.id));
  let requested = new URLSearchParams(location.search).get('league');
  if (!requested || !validIds.has(requested)) {
    requested = leagues[0].id;
    const url = new URL(location);
    url.searchParams.set('league', requested);
    history.replaceState(null, '', url);
  }

  // Render the board immediately (unsynced) so rankings are never blocked on
  // Firebase loading. Firebase then comes up in the background; when it's
  // ready, attachDraftedListener() subscribes the current league and the
  // drafted state streams in and re-renders.
  setActiveLeague(requested);
  initLeagueSelect();
  initSorting();
  initFilters();
  initHeaderControls();
  render();

  await initFirebase();
  attachDraftedListener();
}

init();
