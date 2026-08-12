// ─────────────────────────────────────────────────────────────────────────
// Multi-league state
// ─────────────────────────────────────────────────────────────────────────
// The board serves all 5 leagues from this one page. Which league is active
// is driven by the ?league= URL param, so two browser tabs can each point at
// a different league at the same time and stay fully independent. Drafted
// state is stored per-league in localStorage under a league-scoped key, so
// marking a player drafted in one league never touches another league.

const SEASON = 2026;

let leagues = [];          // [{id, name}], loaded from docs/leagues.json
let allLeaguesData = {};   // { league_id: [player, ...] }, from docs/players.json
let currentLeague = null;  // the active league's id

let allPlayers = [];       // === allLeaguesData[currentLeague]
let drafted = new Set();   // player_ids drafted in the CURRENT league only

let sortCol = 'rank';
let sortDir = 'asc';
let posFilter = 'ALL';
let hideDrafted = false;
let excludeDV = false;
let expanded = new Set();  // player_ids whose source-breakdown row is open
let activePopup = null;

// ─────────────────────────────────────────────────────────────────────────
// League-scoped persistence
// ─────────────────────────────────────────────────────────────────────────
// storageKey() MUST be recomputed from the current league every time it's
// read or written - never captured once at module load. If it were captured
// once, switching leagues in-tab would keep reading/writing the previous
// league's key, which is exactly the cross-league state bleed this whole
// feature is meant to prevent.
function storageKey() {
  return 'draftboard_v1_drafted_' + currentLeague;
}
function loadDrafted() {
  drafted = new Set(JSON.parse(localStorage.getItem(storageKey()) || '[]'));
}
function saveDrafted() {
  localStorage.setItem(storageKey(), JSON.stringify([...drafted]));
}

// --- Flag helpers ---

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

// --- Popup ---

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

// ---

function getVisible() {
  let list = allPlayers.filter(p => {
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
  const players = getVisible();

  if (!players.length) {
    tbody.innerHTML = `<tr><td colspan="6" class="empty-state">NO PLAYERS MATCH FILTER</td></tr>`;
    updateSubbar();
    return;
  }

  const fragment = document.createDocumentFragment();

  players.forEach(p => {
    // Identity is the pipeline-minted player_id (Firebase-safe, stable across
    // rebuilds), not the display name - so the same person is tracked
    // consistently and the upcoming Firebase sync can reuse the same key.
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

    dr.innerHTML = `
      <td colspan="6">
        <div class="detail-inner">
          <div class="sources-grid">${sourcesHtml}</div>
        </div>
      </td>`;

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

function toggleDrafted(id) {
  if (drafted.has(id)) drafted.delete(id);
  else drafted.add(id);
  saveDrafted();
  render();
}

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
}

document.addEventListener('click', e => {
  if (activePopup && !activePopup.contains(e.target) && !e.target.closest('.flag-indicator')) {
    hidePopup();
  }
});

// ─────────────────────────────────────────────────────────────────────────
// League selection
// ─────────────────────────────────────────────────────────────────────────

function updateTitle() {
  // Distinct per-league tab titles matter: on draft day two tabs are open at
  // once, and identical titles make them impossible to tell apart.
  const lg = leagues.find(l => l.id === currentLeague);
  document.title = (lg ? lg.name : 'Draft Board') + ' · ' + SEASON;
}

// Point the board at a league: swap in that league's players, reload its
// (separate) drafted set, reset any open detail rows, and retitle the tab.
// Sort column, position filter, and the toggles are intentionally left as-is
// so they persist across a league switch.
function setActiveLeague(id) {
  currentLeague = id;
  allPlayers = allLeaguesData[id] || [];  // guard: unknown id -> empty board, not a crash
  loadDrafted();       // load THIS league's drafted player_ids
  expanded = new Set(); // don't carry an expanded row over from the old league
  updateTitle();
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
    // Fetch both files once, up front. players.json holds ALL leagues, so
    // switching leagues later just re-indexes what's already in memory - no
    // re-fetch needed.
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

  // Resolve the active league from ?league=, validated against the known ids.
  // A missing or unknown value falls back to the first league AND is written
  // back into the URL, so the tab is never left in an ambiguous state (and a
  // bad ?league= shows an empty board rather than throwing on undefined).
  const validIds = new Set(leagues.map(l => l.id));
  let requested = new URLSearchParams(location.search).get('league');
  if (!requested || !validIds.has(requested)) {
    requested = leagues[0].id;
    const url = new URL(location);
    url.searchParams.set('league', requested);
    history.replaceState(null, '', url);
  }

  setActiveLeague(requested);
  initLeagueSelect();
  initSorting();
  initFilters();
  render();
}

init();
