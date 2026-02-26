const PAGE_SIZE = 50;
let currentQuery = '';
let currentPage = 0;
let totalResults = 0;
let currentResults = [];
let selectedId = null;
let suggestionsData = [];
let map = null;
let debounceTimer = null;
let addrDebounce = null;
let locationLat = null;
let locationLon = null;
let locationActive = false;
let activeFilters = { pristup: [], poistovna: [], wc: null };

// ==================== INIT ====================

async function init() {
  const stats = await fetchJson('/api/stats');
  suggestionsData = await fetchJson('/api/suggestions') || [];
  await doSearch('');

  const input = document.getElementById('searchInput');
  const suggBox = document.getElementById('suggestions');
  let suggIdx = -1;

  input.addEventListener('input', () => {
    clearTimeout(debounceTimer);
    const q = input.value.trim();
    if (q.length >= 1) showSuggestions(q, suggBox);
    else suggBox.classList.remove('active');
    debounceTimer = setTimeout(() => { currentPage = 0; doSearch(q); }, 250);
  });

  input.addEventListener('keydown', (e) => {
    const items = suggBox.querySelectorAll('div');
    if (e.key === 'ArrowDown') { e.preventDefault(); suggIdx = Math.min(suggIdx + 1, items.length - 1); updateSel(items, suggIdx); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); suggIdx = Math.max(suggIdx - 1, -1); updateSel(items, suggIdx); }
    else if (e.key === 'Enter') {
      e.preventDefault();
      if (suggIdx >= 0 && items[suggIdx]) input.value = items[suggIdx].dataset.val;
      suggBox.classList.remove('active');
      suggIdx = -1;
      currentPage = 0;
      doSearch(input.value.trim());
    }
    else if (e.key === 'Escape') { suggBox.classList.remove('active'); suggIdx = -1; }
  });

  input.addEventListener('blur', () => setTimeout(() => suggBox.classList.remove('active'), 150));

  // === LOCATION FILTER ===
  const addrInput = document.getElementById('addressInput');
  addrInput.addEventListener('input', () => {
    clearTimeout(addrDebounce);
    if (!addrInput.value.trim()) { clearLocation(); return; }
    addrDebounce = setTimeout(() => geocodeAddress(addrInput.value.trim()), 700);
  });
  addrInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      clearTimeout(addrDebounce);
      if (addrInput.value.trim()) geocodeAddress(addrInput.value.trim());
    }
  });
  document.getElementById('addressClear').addEventListener('click', clearLocation);
  document.getElementById('gpsBtn').addEventListener('click', useMyLocation);
}

// ==================== API ====================

async function fetchJson(url) {
  try { return await (await fetch(url)).json(); }
  catch (e) { console.error('API error:', e); return null; }
}

async function doSearch(query) {
  currentQuery = query;
  let data;

  // Build filter query string
  let fq = '';
  activeFilters.pristup.forEach(v => fq += `&pristup=${encodeURIComponent(v)}`);
  activeFilters.poistovna.forEach(v => fq += `&poistovna=${encodeURIComponent(v)}`);
  if (activeFilters.wc !== null) fq += `&wc=${activeFilters.wc}`;

  if (locationActive && locationLat !== null) {
    data = await fetchJson(`/api/search_nearby?q=${encodeURIComponent(query)}&lat=${locationLat}&lon=${locationLon}&page=${currentPage}&limit=${PAGE_SIZE}${fq}`);
  } else {
    data = await fetchJson(`/api/search?q=${encodeURIComponent(query)}&page=${currentPage}&limit=${PAGE_SIZE}${fq}`);
  }
  if (!data) return;
  totalResults = data.total;
  currentResults = data.results;
  document.getElementById('countResults').textContent = totalResults.toLocaleString();
  renderTable();
}

async function loadDetail(id) {
  const panel = document.getElementById('detailPanel');
  panel.innerHTML = '<div class="loading" style="padding-top:100px"><div class="spinner"></div>Načítavam detail…</div>';
  const data = await fetchJson(`/api/detail/${id}`);
  if (!data || data.error) { panel.innerHTML = '<div class="detail-empty"><div>Chyba pri načítaní</div></div>'; return; }
  renderDetail(data);
}

// ==================== RENDER TABLE ====================

function renderTable() {
  const tbody = document.getElementById('tableBody');
  const thead = document.querySelector('.table-panel thead tr');
  const showDist = locationActive && currentResults.length > 0 && currentResults[0].vzdialenost_km !== undefined;
  const hasDetail = document.getElementById('mainLayout').classList.contains('has-detail');

  function buildPoistTags(item) {
    const p = item.poistovne || [];
    return p.length ? p.map(x => `<span class="tag tag-poist">${x}</span>`).join('') : '<span style="color:var(--text3)">-</span>';
  }

  if (currentResults.length === 0) {
    if (hasDetail) {
      thead.innerHTML = showDist
        ? '<th>Názov</th><th>Adresa</th><th style="text-align:right">Vzd.</th>'
        : '<th>Názov</th><th>Adresa</th>';
    } else {
      thead.innerHTML = showDist
        ? '<th>Názov</th><th class="col-tags">Obor / Oddelenie</th><th class="col-tags">Poisťovne</th><th>Adresa</th><th style="text-align:right">Vzdialenosť</th>'
        : '<th>Názov</th><th class="col-tags">Obor / Oddelenie</th><th class="col-tags">Poisťovne</th><th>Adresa</th>';
    }
    tbody.innerHTML = `<tr><td colspan="5"><div class="loading" style="padding:60px"><div style="font-size:36px;margin-bottom:10px">🔎</div>Žiadne výsledky. Skús iný výraz.</div></td></tr>`;
    document.getElementById('pagination').innerHTML = '';
    return;
  }

  if (hasDetail) {
    thead.innerHTML = showDist
      ? '<th>Názov</th><th>Adresa</th><th style="text-align:right">Vzd.</th>'
      : '<th>Názov</th><th>Adresa</th>';
  } else {
    thead.innerHTML = showDist
      ? '<th>Názov</th><th class="col-tags">Obor / Oddelenie</th><th class="col-tags">Poisťovne</th><th>Adresa</th><th style="text-align:right">Vzdialenosť</th>'
      : '<th>Názov</th><th class="col-tags">Obor / Oddelenie</th><th class="col-tags">Poisťovne</th><th>Adresa</th>';
  }

  tbody.innerHTML = currentResults.map(item => {
    const allTags = item.oddelenia || [];
    const shown = allTags.slice(0, 3).map(o => `<span class="tag tag-obor">${o}</span>`).join('');
    const more = allTags.length > 3 ? `<span class="tag tag-more">+${allTags.length - 3}</span>` : '';
    const druh = item.druh_zarizeni && item.druh_zarizeni !== '-' ? `<span class="tag tag-druh">${item.druh_zarizeni}</span>` : '';
    
    if (hasDetail) {
      const distCol = showDist ? `<td style="text-align:right"><span class="dist-badge">${item.vzdialenost_km} km</span></td>` : '';
      return `<tr data-id="${item.id}" class="${item.id === selectedId ? 'active' : ''}" onclick="selectRow(${item.id})">
        <td>${item.nazov}</td>
        <td style="font-size:12px">${item.adresa}</td>
        ${distCol}
      </tr>`;
    } else {
      const distCol = showDist ? `<td style="text-align:right"><span class="dist-badge">${item.vzdialenost_km} km</span></td>` : '';
      return `<tr data-id="${item.id}" class="${item.id === selectedId ? 'active' : ''}" onclick="selectRow(${item.id})">
        <td>${item.nazov}</td>
        <td class="col-tags">${shown}${more}${druh}</td>
        <td class="col-tags">${buildPoistTags(item)}</td>
        <td>${item.adresa}</td>
        ${distCol}
      </tr>`;
    }
  }).join('');

  const totalPages = Math.ceil(totalResults / PAGE_SIZE);
  const pag = document.getElementById('pagination');
  if (totalPages <= 1) { pag.innerHTML = ''; return; }
  pag.innerHTML = `
    <button onclick="goPage(0)" ${currentPage===0?'disabled':''}>⟨⟨</button>
    <button onclick="goPage(${currentPage-1})" ${currentPage===0?'disabled':''}>⟨</button>
    <span class="page-info">${currentPage+1} / ${totalPages}</span>
    <button onclick="goPage(${currentPage+1})" ${currentPage>=totalPages-1?'disabled':''}>⟩</button>
    <button onclick="goPage(${totalPages-1})" ${currentPage>=totalPages-1?'disabled':''}>⟩⟩</button>`;
}

// ==================== RENDER DETAIL ====================

function renderDetail(item) {
  const panel = document.getElementById('detailPanel');
  const days = ['Po', 'Út', 'St', 'Čt', 'Pá', 'So', 'Ne'];

  const allDetailTags = item.oddelenia || [];
  const shownTags = allDetailTags.map(o => `<span class="tag tag-obor">${o}</span>`).join(' ');
  const moreTags = '';
  const druhTag = item.druh_zarizeni && item.druh_zarizeni !== '-' ? `<span class="tag tag-druh">${item.druh_zarizeni}</span>` : '';

  // Kontakt — vždy zobrazíme, s pomlčkami kde chýba
  const telVal = item.telefon !== '-' ? item.telefon : '-';
  const emailVal = item.email !== '-'
    ? `<a href="mailto:${item.email}">${item.email}</a>`
    : '<span class="dash">-</span>';
  const webVal = item.web !== '-'
    ? `<a href="${item.web.startsWith('http') ? item.web : 'http://' + item.web}" target="_blank">${item.web}</a>`
    : '<span class="dash">-</span>';

  const contact = `<div class="detail-section"><h3>Kontakt</h3>
    <div class="contact-grid">
      <span class="label">Telefón:</span><span class="value ${telVal==='-'?'dash':''}">${telVal}</span>
      <span class="label">Email:</span><span class="value">${emailVal}</span>
      <span class="label">Web:</span><span class="value">${webVal}</span>
    </div></div>`;

  // Prístupnosť a WC
  let accessHtml = '';
  const hasPristup = item.pristup !== null && item.pristup !== undefined;
  const hasWc = item.wc !== null && item.wc !== undefined;
  if (hasPristup || hasWc) {
    accessHtml = '<div class="detail-section"><h3>Prístupnosť</h3><div class="access-row">';
    if (hasPristup) {
      let icon, cls;
      if (item.pristup === 'přístupné') { icon = '♿'; cls = 'access-yes'; }
      else if (item.pristup === 'přístupné s asistencí') { icon = '🤝'; cls = 'access-partial'; }
      else { icon = '🚫'; cls = 'access-no'; }
      accessHtml += `<span class="access-badge ${cls}">${icon} ${item.pristup}</span>`;
    }
    if (hasWc) {
      if (item.wc === 1) {
        accessHtml += '<span class="access-badge access-yes">🚻 WC k dispozícii</span>';
      } else {
        accessHtml += '<span class="access-badge access-no">🚻 WC nie je k dispozícii</span>';
      }
    }
    accessHtml += '</div></div>';
  }

  // Ordinačné hodiny
  let hoursHtml = '<div class="detail-section"><h3>Ordinačné hodiny</h3>';

  if (item.hodiny_status === 'nedostupne' || item.hodiny_status === 'ziadne') {
    hoursHtml += `<div class="hours-unavailable">
      <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><path d="M12 8v4M12 16h.01"/></svg>
      Otváracie hodiny: NEDOSTUPNÉ
    </div>`;
  } else if (item.otvaracie_hodiny && item.otvaracie_hodiny.length > 0) {
    item.otvaracie_hodiny.forEach(dept => {
      hoursHtml += '<div class="hours-dept">';
      if (item.otvaracie_hodiny.length > 1) hoursHtml += `<div class="dept-name">${dept.oddelenie}</div>`;
      hoursHtml += '<div class="hours-grid">';
      days.forEach(d => {
        const time = dept.hodiny ? dept.hodiny[d] : null;
        let cls = 'na';
        let display = 'NEDOSTUPNÉ';
        if (time === null || time === undefined) {
          cls = 'na'; display = 'NEDOSTUPNÉ';
        } else if (time === 'zavřeno' || time === 'zavreno') {
          cls = 'closed'; display = 'zavřeno';
        } else {
          cls = 'open'; display = time;
        }
        hoursHtml += `<div class="day">${d}</div><div class="time ${cls}">${display}</div>`;
      });
      hoursHtml += '</div></div>';
    });
  }
  hoursHtml += '</div>';

  // Lekárne
  let pharmHtml = '<div class="detail-section"><h3>💊 Najbližšie lekárne</h3>';
  if (item.najblizsia_lekaren && item.najblizsia_lekaren.length > 0) {
    item.najblizsia_lekaren.forEach((p, i) => {
      pharmHtml += `<div class="pharm-item">
        <div class="pharm-num">${i + 1}</div>
        <div class="pharm-info">
          <div class="pname">${p.nazov}</div>
          <div class="paddr">${p.adresa}</div>
        </div>
        <div class="pharm-dist">${p.vzdialenost_km} km</div>
      </div>`;
    });
  } else {
    pharmHtml += '<div style="font-size:12px;color:var(--text3)">-</div>';
  }
  pharmHtml += '</div>';

  // MHD zastávky
  let mhdHtml = '<div class="detail-section"><h3>🚌 Najbližšie MHD zastávky</h3>';
  if (item.najblizsia_mhd && item.najblizsia_mhd.length > 0) {
    item.najblizsia_mhd.forEach((s, i) => {
      const wheelchair = s.wheelchair ? ' ♿' : '';
      mhdHtml += `<div class="mhd-item">
        <div class="mhd-num">${i + 1}</div>
        <div class="mhd-info">
          <div class="mname">${s.nazov}${wheelchair}</div>
          <div class="mdetail">Zóna: ${s.zona}</div>
        </div>
        <div class="mhd-dist">${s.vzdialenost_m} m</div>
      </div>`;
    });
  } else {
    mhdHtml += '<div style="font-size:12px;color:var(--text3)">-</div>';
  }
  mhdHtml += '</div>';

  // Poisťovne pre detail
  const poistDetail = (item.poistovne && item.poistovne.length > 0)
    ? item.poistovne.map(p => `<span class="tag tag-poist">${p}</span>`).join(' ')
    : '<span style="color:var(--text3);font-size:12px">-</span>';

  panel.innerHTML = `
    <div class="detail-header">
      <button class="detail-close" onclick="closeDetail()" title="Zavrieť detail">✕</button>
      <h2>${item.nazov}</h2>
      <div>${shownTags} ${moreTags} ${druhTag}</div>
      <div style="margin-top:6px"><span style="font-size:10px;text-transform:uppercase;letter-spacing:.5px;color:var(--text3);font-weight:600">Poisťovne:</span> ${poistDetail}</div>
      <div class="meta">
        <span>📍 ${item.adresa}</span>
        <span>🏢 IČO: ${item.ico}</span>
        <span>🩺 ${item.forma_pece}</span>
      </div>
    </div>
    <div class="detail-body">
      <div class="detail-left">
        ${contact}
        ${accessHtml}
        ${hoursHtml}
        ${mhdHtml}
        ${pharmHtml}
      </div>
      <div class="detail-right">
        <div id="map"></div>
      </div>
    </div>`;

  setTimeout(() => initMap(item), 50);
}

function showEmptyDetail(noResults) {
  document.getElementById('detailPanel').innerHTML = `
    <div class="detail-empty"><div>
      <div style="font-size:36px;margin-bottom:10px">${noResults ? '😕' : '🔍'}</div>
      <p>${noResults ? 'Žiadne výsledky pre tento výraz' : 'Klikni na riadok pre zobrazenie detailu'}</p>
    </div></div>`;
}

// ==================== MAP ====================

function initMap(item) {
  if (map) { map.remove(); map = null; }
  const el = document.getElementById('map');
  if (!el || !item.lat || !item.lon) return;

  map = L.map('map', { zoomControl: false }).setView([item.lat, item.lon], 15);
  L.control.zoom({ position: 'topright' }).addTo(map);

  // Svetlá mapa — CartoDB Positron
  L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', {
    attribution: '©<a href="https://www.openstreetmap.org/copyright">OSM</a> ©<a href="https://carto.com/">CARTO</a>',
    maxZoom: 19,
    subdomains: 'abcd'
  }).addTo(map);

  // Lekárne — ružové markery (added FIRST = lower layer)
  const bounds = [[item.lat, item.lon]];
  (item.najblizsia_lekaren || []).forEach(p => {
    const pIcon = L.divIcon({
      html: '<div style="background:#b83280;width:16px;height:16px;border-radius:50%;border:2.5px solid #fff;box-shadow:0 2px 8px rgba(0,0,0,.25)"></div>',
      iconSize: [16, 16], iconAnchor: [8, 8], className: ''
    });
    L.marker([p.lat, p.lon], { icon: pIcon, zIndexOffset: 100 }).addTo(map)
      .bindPopup(`<b>💊 ${p.nazov}</b><br>${p.adresa}<br><span style="color:#16864e;font-weight:600">${p.vzdialenost_km} km</span>`);
    bounds.push([p.lat, p.lon]);
  });

  // MHD zastávky — oranžové markery
  (item.najblizsia_mhd || []).forEach(s => {
    const sIcon = L.divIcon({
      html: '<div style="background:#c27317;width:16px;height:16px;border-radius:4px;border:2.5px solid #fff;box-shadow:0 2px 8px rgba(0,0,0,.25)"></div>',
      iconSize: [16, 16], iconAnchor: [8, 8], className: ''
    });
    L.marker([s.lat, s.lon], { icon: sIcon, zIndexOffset: 100 }).addTo(map)
      .bindPopup(`<b>🚌 ${s.nazov}</b><br><span style="color:#c27317;font-weight:600">${s.vzdialenost_m} m</span>`);
    bounds.push([s.lat, s.lon]);
  });

  // Zariadenie — modrý marker (added LAST with highest zIndex = always on top)
  const facIcon = L.divIcon({
    html: '<div style="background:#1a82c4;width:22px;height:22px;border-radius:50%;border:3px solid #fff;box-shadow:0 3px 12px rgba(0,0,0,.3)"></div>',
    iconSize: [22, 22], iconAnchor: [11, 11], className: ''
  });
  L.marker([item.lat, item.lon], { icon: facIcon, zIndexOffset: 1000 }).addTo(map)
    .bindPopup(`<b>${item.nazov}</b><br>${item.adresa}`);

  if (bounds.length > 1) map.fitBounds(bounds, { padding: [30, 30] });
}

// ==================== INTERACTIONS ====================

function selectRow(id) {
  selectedId = id;
  document.getElementById('mainLayout').classList.add('has-detail');
  renderTable();
  loadDetail(id);
}

function closeDetail() {
  selectedId = null;
  document.getElementById('mainLayout').classList.remove('has-detail');
  document.getElementById('detailPanel').innerHTML = '';
  renderTable();
}

function goPage(p) {
  const totalPages = Math.ceil(totalResults / PAGE_SIZE);
  currentPage = Math.max(0, Math.min(p, totalPages - 1));
  doSearch(currentQuery);
  document.getElementById('tablePanel').scrollTop = 0;
}

function showSuggestions(q, box) {
  const norm = q.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
  const matches = suggestionsData.filter(s =>
    s.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().includes(norm)
  ).slice(0, 8);
  if (!matches.length) { box.classList.remove('active'); return; }
  const re = new RegExp(`(${q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
  box.innerHTML = matches.map(m =>
    `<div data-val="${m}">${m.replace(re, '<mark>$1</mark>')}</div>`
  ).join('');
  box.classList.add('active');
  box.querySelectorAll('div').forEach(d => {
    d.addEventListener('mousedown', (e) => {
      e.preventDefault();
      document.getElementById('searchInput').value = d.dataset.val;
      box.classList.remove('active');
      currentPage = 0;
      doSearch(d.dataset.val);
    });
  });
}

function updateSel(items, idx) {
  items.forEach((el, i) => el.classList.toggle('sel', i === idx));
}

// ==================== LOCATION FILTER ====================

function setLocationStatus(cls, text, autohide) {
  const el = document.getElementById('addressStatus');
  el.className = 'address-status show ' + cls;
  el.textContent = text;
  if (autohide) setTimeout(() => { el.className = 'address-status'; }, 3000);
}

function activateLocation(lat, lon, label) {
  locationLat = lat;
  locationLon = lon;
  locationActive = true;
  const inp = document.getElementById('addressInput');
  inp.classList.add('active-filter');
  document.getElementById('addressClear').style.display = 'block';
  if (label) inp.value = label;
  setLocationStatus('success', '📍 ' + label, true);
  currentPage = 0;
  selectedId = null;
  doSearch(currentQuery);
}

function clearLocation() {
  locationLat = null;
  locationLon = null;
  locationActive = false;
  const inp = document.getElementById('addressInput');
  inp.value = '';
  inp.classList.remove('active-filter');
  document.getElementById('addressClear').style.display = 'none';
  document.getElementById('addressStatus').className = 'address-status';
  document.getElementById('gpsBtn').classList.remove('active');
  currentPage = 0;
  doSearch(currentQuery);
}

async function geocodeAddress(address) {
  setLocationStatus('loading', 'Hľadám adresu…', false);
  try {
    const q = encodeURIComponent(address + ', Jihomoravský kraj, Česko');
    const resp = await fetch(`https://nominatim.openstreetmap.org/search?format=json&q=${q}&limit=1&countrycodes=cz`);
    if (resp.ok) {
      const ct = resp.headers.get('content-type') || '';
      if (ct.includes('json')) {
        const data = await resp.json();
        if (data && data.length > 0) {
          const name = data[0].display_name.split(',').slice(0, 2).join(',').trim();
          activateLocation(parseFloat(data[0].lat), parseFloat(data[0].lon), name);
          document.getElementById('gpsBtn').classList.remove('active');
          return;
        }
      }
    }
  } catch (e) { console.warn('Nominatim error:', e); }
  setLocationStatus('error', 'Adresa nenájdená', true);
}

function useMyLocation() {
  const btn = document.getElementById('gpsBtn');
  if (!navigator.geolocation) {
    setLocationStatus('error', 'Geolokácia nie je podporovaná', true);
    return;
  }
  btn.classList.add('loading');
  setLocationStatus('loading', 'Zisťujem polohu…', false);

  navigator.geolocation.getCurrentPosition(
    (pos) => {
      btn.classList.remove('loading');
      btn.classList.add('active');
      const lat = pos.coords.latitude;
      const lon = pos.coords.longitude;
      activateLocation(lat, lon, 'Moja poloha');
    },
    (err) => {
      btn.classList.remove('loading');
      let msg = 'Nepodarilo sa zistiť polohu';
      if (err.code === 1) msg = 'Prístup k polohe bol zamietnutý';
      else if (err.code === 2) msg = 'Poloha nie je dostupná';
      else if (err.code === 3) msg = 'Časový limit vypršal';
      setLocationStatus('error', msg, true);
    },
    { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 }
  );
}

// ==================== FILTERS ====================

function toggleFilter(btn) {
  const filter = btn.dataset.filter;
  const value = btn.dataset.value;

  if (filter === 'wc') {
    if (btn.classList.contains('active-green')) {
      btn.classList.remove('active-green');
      activeFilters.wc = null;
    } else {
      btn.classList.add('active-green');
      activeFilters.wc = value;
    }
  } else {
    btn.classList.toggle('active');
    const arr = activeFilters[filter];
    const idx = arr.indexOf(value);
    if (idx >= 0) arr.splice(idx, 1);
    else arr.push(value);
  }

  updateFilterClearBtn();
  currentPage = 0;
  doSearch(currentQuery);
}

function clearAllFilters() {
  activeFilters = { pristup: [], poistovna: [], wc: null };
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active', 'active-green'));
  updateFilterClearBtn();
  currentPage = 0;
  doSearch(currentQuery);
}

function updateFilterClearBtn() {
  const hasAny = activeFilters.pristup.length > 0 || activeFilters.poistovna.length > 0 || activeFilters.wc !== null;
  document.getElementById('filterClear').classList.toggle('show', hasAny);
}

document.addEventListener('DOMContentLoaded', init);

// ==================== AI CHAT ====================

let chatOpen = false;

function toggleChat() {
  chatOpen = !chatOpen;
  document.getElementById('chatPanel').classList.toggle('open', chatOpen);
  document.getElementById('chatFab').classList.toggle('hidden', chatOpen);
  if (chatOpen) document.getElementById('chatInput').focus();
}

function sendExample(btn) {
  const text = btn.textContent.replace(/^[^\s]+\s/, ''); // Remove emoji prefix
  document.getElementById('chatInput').value = text;
  sendChat();
}

async function sendChat() {
  const input = document.getElementById('chatInput');
  const msg = input.value.trim();
  if (!msg) return;

  const messages = document.getElementById('chatMessages');
  const sendBtn = document.getElementById('chatSend');

  // Remove welcome if present
  const welcome = messages.querySelector('.chat-welcome');
  if (welcome) welcome.remove();

  // Add user message
  messages.innerHTML += `<div class="chat-msg user">${escHtml(msg)}</div>`;
  input.value = '';
  sendBtn.disabled = true;

  // Add typing indicator
  messages.innerHTML += `<div class="chat-typing" id="chatTyping"><span></span><span></span><span></span></div>`;
  messages.scrollTop = messages.scrollHeight;

  try {
    const resp = await fetch('/api/ai_chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: msg })
    });
    const data = await resp.json();

    // Remove typing
    const typing = document.getElementById('chatTyping');
    if (typing) typing.remove();

    // Build AI response
    let html = `<div class="chat-msg ai">`;
    html += `<div class="ai-text">${escHtml(data.ai_response)}</div>`;

    // Show applied filters
    const filters = data.filters || {};
    const filterKeys = Object.keys(filters);
    if (filterKeys.length > 0) {
      html += `<div class="chat-filters">`;
      const labels = {
        oddelenie: '🏥', obec: '📍', poistovna: '💳',
        pristup: '♿', wc: '🚻', druh_zarizeni: '🏢'
      };
      for (const [k, v] of Object.entries(filters)) {
        html += `<span class="chat-filter-tag">${labels[k] || '🔍'} ${v}</span>`;
      }
      html += `</div>`;
    }

    // Show results
    if (data.results && data.results.length > 0) {
      html += `<div class="ai-results">`;
      html += `<div style="font-size:11px;color:var(--text3);margin-bottom:4px">Nájdených: ${data.total} výsledkov</div>`;
      data.results.slice(0, 5).forEach((r, i) => {
        const poist = (r.poistovne || []).map(p => `<span class="tag tag-poist">${p}</span>`).join('');
        const pristupTag = r.pristup ? `<span class="tag" style="background:var(--green-bg);color:var(--green)">♿ ${r.pristup}</span>` : '';
        html += `<div class="chat-result-item" onclick="chatOpenDetail(${r.id})">
          <div class="chat-result-num">${i + 1}</div>
          <div class="chat-result-info">
            <div class="cr-name">${escHtml(r.nazov)}</div>
            <div class="cr-addr">${escHtml(r.adresa)}</div>
            <div class="cr-tags">${poist} ${pristupTag}</div>
          </div>
        </div>`;
      });
      if (data.total > 5) {
        html += `<div style="font-size:11px;color:var(--text3);text-align:center;margin-top:4px">… a ďalších ${data.total - 5}</div>`;
      }
      html += `</div>`;
    }

    html += `</div>`;
    messages.innerHTML += html;

  } catch (e) {
    const typing = document.getElementById('chatTyping');
    if (typing) typing.remove();
    messages.innerHTML += `<div class="chat-msg ai">Chyba: nepodarilo sa spojiť s AI asistentom.</div>`;
  }

  sendBtn.disabled = false;
  messages.scrollTop = messages.scrollHeight;
}

function chatOpenDetail(id) {
  // Open detail in main dashboard
  selectRow(id);
  // Optionally minimize chat
  // toggleChat();
}

function escHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

// Chat keyboard shortcut
document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('chatInput').addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChat(); }
    if (e.key === 'Escape') toggleChat();
  });
});
