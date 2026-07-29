const STORAGE_KEY = 'draftboard_v1_drafted';

let allPlayers = [];
let sortCol = 'rank';
let sortDir = 'asc';
let posFilter = 'ALL';
let hideDrafted = false;
let excludeDV = false;
let expanded = new Set();
let drafted = new Set(JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]'));
let activePopup = null;

function saveDrafted() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify([...drafted]));
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
    if (hideDrafted && drafted.has(p.name)) return false;
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
    const isDrafted = drafted.has(p.name);
    const isExpanded = expanded.has(p.name);
    const flags = p.flags || [];
    const injuries = p.injuries || [];
    const hasAnyFlag = flags.length > 0 || injuries.length > 0;

    // ── main row ──
    const tr = document.createElement('tr');
    tr.className = `player-row${isDrafted ? ' drafted' : ''}`;
    tr.dataset.name = p.name;

    tr.innerHTML = `
      <td class="cell-rk">${p.rank}</td>
      <td>
        <div class="player-name">
          ${p.name}
          ${hasAnyFlag ? buildFlagIndicators(p) : ''}
        </div>
        <div class="player-sub">
          <span class="player-team">${p.team}</span>
          <span class="player-posrk">${p.pos_rank}</span>
        </div>
      </td>
      <td><span class="pos-badge pos-${p.position}">${p.position}</span></td>
      <td class="cell-pts">${p.projected_points.toFixed(1)}</td>
      <td class="cell-vbd">${p.vbd.toFixed(1)}</td>
      <td class="cell-action">
        <button class="${isDrafted ? 'btn-undo' : 'btn-drafted'}" data-name="${p.name}">
          ${isDrafted ? 'UNDO' : 'DRAFTED'}
        </button>
      </td>
    `;

    tr.addEventListener('click', e => {
      if (e.target.closest('button') || e.target.closest('.flag-indicator')) return;
      toggleExpand(p.name);
    });

    tr.querySelector('button').addEventListener('click', e => {
      e.stopPropagation();
      toggleDrafted(p.name);
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
    dr.dataset.name = p.name;

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

function toggleExpand(name) {
  if (expanded.has(name)) expanded.delete(name);
  else expanded.add(name);
  render();
}

function toggleDrafted(name) {
  if (drafted.has(name)) drafted.delete(name);
  else drafted.add(name);
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

async function init() {
  try {
    const res = await fetch('players.json');
    if (!res.ok) throw new Error(res.statusText);
    allPlayers = await res.json();
  } catch (err) {
    document.getElementById('playerList').innerHTML =
      `<tr><td colspan="6" class="empty-state">FAILED TO LOAD PLAYER DATA</td></tr>`;
    console.error(err);
    return;
  }

  initSorting();
  initFilters();
  render();
}

init();
