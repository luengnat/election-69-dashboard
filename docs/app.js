const els = {
  kpiGrid: document.getElementById('kpiGrid'),
  generatedAt: document.getElementById('generatedAt'),
  tableBody: document.getElementById('tableBody'),
  rowCount: document.getElementById('rowCount'),
  search: document.getElementById('searchInput'),
  province: document.getElementById('provinceSelect'),
  form: document.getElementById('formSelect'),
  quality: document.getElementById('qualitySelect'),
  rowTemplate: document.getElementById('rowTemplate'),
  viewTabs: document.getElementById('viewTabs'),
  detailTitle: document.getElementById('detailTitle'),
  detailMeta: document.getElementById('detailMeta'),
  detailBody: document.getElementById('detailBody'),
  skewBody: document.getElementById('skewBody'),
  skewCount: document.getElementById('skewCount')
};

let state = { items: [], filtered: [], view: 'all', selected: null };

function numOrNull(v) {
  if (v === null || v === undefined || v === '') return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function resolveDriveUrl(row) {
  const raw = String(row?.drive_url || '').trim();
  if (raw && raw !== '#' && raw.includes('drive.google.com')) return raw;
  const did = String(row?.drive_id || '').trim();
  if (/^[A-Za-z0-9_-]{20,}$/.test(did)) {
    return `https://drive.google.com/file/d/${did}/view`;
  }
  return '';
}

function kpi(label, value) {
  const card = document.createElement('div');
  card.className = 'kpi';
  card.innerHTML = `<div class="label">${label}</div><div class="value">${value}</div>`;
  return card;
}

function makeChip(text, cls) {
  const s = document.createElement('span');
  s.className = cls;
  s.textContent = text;
  return s;
}

function renderKPIs(summary) {
  const skewRows = computeSkewRows(state.items);
  els.kpiGrid.innerHTML = '';
  els.kpiGrid.append(
    kpi('Total Files', summary.total_files ?? 0),
    kpi('Strong Summaries', (summary.total_files ?? 0) - (summary.weak_summaries ?? 0)),
    kpi('Weak Summaries', summary.weak_summaries ?? 0),
    kpi('With Valid Votes', summary.with_valid_votes ?? 0),
    kpi('OCR Exact', summary.ocr_exact_matches ?? 0),
    kpi('Skew Districts', skewRows.length)
  );
}

function renderRows(rows) {
  els.tableBody.innerHTML = '';
  rows.forEach((r) => {
    const node = els.rowTemplate.content.cloneNode(true);
    const tr = node.querySelector('tr');
    const locCell = node.querySelector('.loc');
    tr.classList.add('clickable-row');
    if (state.selected && state.selected.drive_id === r.drive_id) tr.classList.add('selected');
    const locText = `${r.province || '-'} เขต ${r.district_number || '-'}`;
    const driveUrl = resolveDriveUrl(r);
    if (driveUrl) {
      const a = document.createElement('a');
      a.href = driveUrl;
      a.target = '_blank';
      a.rel = 'noopener noreferrer';
      a.className = 'loc-link';
      a.textContent = locText;
      a.title = 'Open source document on Google Drive';
      a.addEventListener('click', (e) => e.stopPropagation());
      locCell.append(a);
    } else {
      locCell.textContent = locText;
    }
    const form = node.querySelector('.form');
    form.append(makeChip(r.form_type === 'party_list' ? 'Party List' : 'Constituency', `form-chip ${r.form_type}`));
    node.querySelector('.valid').textContent = r.valid_votes_extracted ?? '-';

    tr.addEventListener('click', () => {
      state.selected = r;
      renderRows(state.filtered);
      renderDetail(r);
    });
    els.tableBody.append(node);
  });
  els.rowCount.textContent = `${rows.length} rows`;
}

function renderDetail(row) {
  if (!row) {
    els.detailTitle.textContent = 'District Detail';
    els.detailMeta.textContent = 'Select a row';
    els.detailBody.innerHTML = '';
    return;
  }
  const label = row.form_type === 'party_list' ? '(Party List)' : '(Constituency)';
  els.detailTitle.textContent = `${row.province || '-'} เขต ${row.district_number || '-'} ${label}`;
  els.detailMeta.textContent = `Valid votes: ${row.valid_votes_extracted ?? '-'}`;
  els.detailBody.innerHTML = '';

  const votes = row.votes || {};
  const names = row.form_type === 'party_list' ? (row.party_names || {}) : (row.candidate_names || {});
  const parties = row.candidate_parties || {};

  const rows = Object.entries(votes)
    .map(([number, score]) => ({ number, score: Number(score) || 0 }))
    .sort((a, b) => b.score - a.score || Number(a.number) - Number(b.number));

  rows.forEach(({ number, score }) => {
    const tr = document.createElement('tr');
    const no = document.createElement('td');
    no.className = 'mono';
    no.textContent = number;
    const nm = document.createElement('td');
    const baseName = names[number] || '-';
    if (row.form_type === 'constituency' && parties[number]) {
      nm.textContent = `${baseName} (${parties[number]})`;
    } else {
      nm.textContent = baseName;
    }
    const sc = document.createElement('td');
    sc.className = 'mono';
    sc.textContent = score.toLocaleString();
    tr.append(no, nm, sc);
    els.detailBody.append(tr);
  });
}

function rowTotals(row) {
  const valid = numOrNull(row?.valid_votes_extracted ?? row?.valid_votes ?? row?.sources?.read?.valid_votes);
  const invalid = numOrNull(row?.invalid_votes ?? row?.sources?.read?.invalid_votes);
  const blank = numOrNull(row?.blank_votes ?? row?.sources?.read?.blank_votes);
  if (valid === null || invalid === null || blank === null) {
    return { valid, invalid, blank, total: null };
  }
  return { valid, invalid, blank, total: valid + invalid + blank };
}

function computeSkewRows(items) {
  const byKey = new Map();
  items.forEach((r) => {
    const p = r.province || '';
    const d = r.district_number;
    const t = r.form_type;
    if (!p || d === null || d === undefined || !t) return;
    const key = `${p}||${d}`;
    if (!byKey.has(key)) byKey.set(key, { province: p, district_number: d });
    byKey.get(key)[t] = r;
  });

  const out = [];
  byKey.forEach((g) => {
    if (!g.constituency || !g.party_list) return;
    const ct = rowTotals(g.constituency);
    const pt = rowTotals(g.party_list);
    if (ct.total === null || pt.total === null) return;
    const diff = ct.total - pt.total;
    if (diff === 0) return;
    out.push({
      province: g.province,
      district_number: g.district_number,
      c_total: ct.total,
      p_total: pt.total,
      diff,
      c_invalid: ct.invalid,
      c_blank: ct.blank,
      p_invalid: pt.invalid,
      p_blank: pt.blank,
      c_url: resolveDriveUrl(g.constituency),
      p_url: resolveDriveUrl(g.party_list)
    });
  });

  return out.sort((a, b) => Math.abs(b.diff) - Math.abs(a.diff) || a.province.localeCompare(b.province, 'th') || Number(a.district_number) - Number(b.district_number));
}

function renderSkewTable(items) {
  if (!els.skewBody || !els.skewCount) return;
  const rows = computeSkewRows(items);
  els.skewBody.innerHTML = '';
  rows.forEach((r) => {
    const tr = document.createElement('tr');
    const loc = document.createElement('td');
    const text = `${r.province} เขต ${r.district_number}`;
    if (r.c_url || r.p_url) {
      const c = document.createElement('a');
      c.href = r.c_url || '#';
      c.target = '_blank';
      c.rel = 'noopener noreferrer';
      c.className = 'loc-link';
      c.textContent = text;
      c.title = 'Open constituency source';
      const sep = document.createElement('span');
      sep.textContent = ' ';
      const p = document.createElement('a');
      p.href = r.p_url || '#';
      p.target = '_blank';
      p.rel = 'noopener noreferrer';
      p.className = 'loc-link';
      p.textContent = '[บช]';
      p.title = 'Open party-list source';
      loc.append(c, sep, p);
    } else {
      loc.textContent = text;
    }
    const cTotal = document.createElement('td');
    cTotal.className = 'mono';
    cTotal.textContent = r.c_total.toLocaleString();
    const pTotal = document.createElement('td');
    pTotal.className = 'mono';
    pTotal.textContent = r.p_total.toLocaleString();
    const diff = document.createElement('td');
    diff.className = 'mono';
    diff.textContent = r.diff.toLocaleString();
    const cInv = document.createElement('td');
    cInv.className = 'mono';
    cInv.textContent = r.c_invalid.toLocaleString();
    const cBlk = document.createElement('td');
    cBlk.className = 'mono';
    cBlk.textContent = r.c_blank.toLocaleString();
    const pInv = document.createElement('td');
    pInv.className = 'mono';
    pInv.textContent = r.p_invalid.toLocaleString();
    const pBlk = document.createElement('td');
    pBlk.className = 'mono';
    pBlk.textContent = r.p_blank.toLocaleString();
    tr.append(loc, cTotal, pTotal, diff, cInv, cBlk, pInv, pBlk);
    els.skewBody.append(tr);
  });
  els.skewCount.textContent = `${rows.length} rows`;
}

function applyFilters() {
  const q = (els.search.value || '').trim().toLowerCase();
  const province = els.province.value;
  const form = els.form.value;
  const forcedForm = state.view === 'all' ? '' : state.view;
  const quality = els.quality.value;

  state.filtered = state.items.filter((r) => {
    if (province && r.province !== province) return false;
    if (forcedForm && r.form_type !== forcedForm) return false;
    if (form && r.form_type !== form) return false;
    if (quality === 'strong' && r.weak_summary) return false;
    if (quality === 'weak' && !r.weak_summary) return false;
    if (quality === 'ocr_exact' && !(r.ocr_check && r.ocr_check.exact)) return false;
    if (!q) return true;
    const hay = `${r.name || ''} ${r.province || ''} ${r.district_number || ''} ${r.drive_id || ''}`.toLowerCase();
    return hay.includes(q);
  });

  renderRows(state.filtered);
  if (state.selected) {
    const selectedInView = state.filtered.find((x) => x.drive_id === state.selected.drive_id);
    renderDetail(selectedInView || state.filtered[0] || null);
    state.selected = selectedInView || state.filtered[0] || null;
  } else {
    state.selected = state.filtered[0] || null;
    renderDetail(state.selected);
  }
}

function setupTabs() {
  if (!els.viewTabs) return;
  const tabs = [...els.viewTabs.querySelectorAll('[data-view]')];
  tabs.forEach((btn) => {
    btn.addEventListener('click', () => {
      state.view = btn.dataset.view || 'all';
      tabs.forEach((x) => x.classList.toggle('active', x === btn));
      if (state.view === 'all') {
        els.form.value = '';
      } else {
        els.form.value = state.view;
      }
      applyFilters();
    });
  });
}

async function init() {
  const res = await fetch('./data/district_dashboard_data.json');
  const data = await res.json();
  state.items = data.items || [];

  els.generatedAt.textContent = `Generated: ${data.generated_at || '-'} • Source: OCR extraction pipeline`;
  renderKPIs(data.summary || {});
  renderSkewTable(state.items);

  const provinces = [...new Set(state.items.map((x) => x.province).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'th'));
  provinces.forEach((p) => {
    const o = document.createElement('option');
    o.value = p;
    o.textContent = p;
    els.province.append(o);
  });

  [els.search, els.province, els.form, els.quality].forEach((el) => el.addEventListener('input', applyFilters));
  [els.province, els.form, els.quality].forEach((el) => el.addEventListener('change', applyFilters));
  setupTabs();
  applyFilters();
}

init().catch((err) => {
  els.generatedAt.textContent = `Failed to load data: ${err.message}`;
});
