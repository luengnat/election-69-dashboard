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
  detailBody: document.getElementById('detailBody')
};

let state = { items: [], filtered: [], view: 'all', selected: null };

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
  els.kpiGrid.innerHTML = '';
  els.kpiGrid.append(
    kpi('Total Files', summary.total_files ?? 0),
    kpi('Strong Summaries', (summary.total_files ?? 0) - (summary.weak_summaries ?? 0)),
    kpi('Weak Summaries', summary.weak_summaries ?? 0),
    kpi('With Valid Votes', summary.with_valid_votes ?? 0),
    kpi('OCR Exact', summary.ocr_exact_matches ?? 0)
  );
}

function renderRows(rows) {
  els.tableBody.innerHTML = '';
  rows.forEach((r) => {
    const node = els.rowTemplate.content.cloneNode(true);
    const tr = node.querySelector('tr');
    tr.classList.add('clickable-row');
    if (state.selected && state.selected.drive_id === r.drive_id) tr.classList.add('selected');
    node.querySelector('.loc').textContent = `${r.province || '-'} เขต ${r.district_number || '-'}`;
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
