const els = {
  kpiGrid: document.getElementById('kpiGrid'),
  generatedAt: document.getElementById('generatedAt'),
  tableBody: document.getElementById('tableBody'),
  rowCount: document.getElementById('rowCount'),
  search: document.getElementById('searchInput'),
  province: document.getElementById('provinceSelect'),
  form: document.getElementById('formSelect'),
  quality: document.getElementById('qualitySelect'),
  rowTemplate: document.getElementById('rowTemplate')
};

let state = { items: [], filtered: [] };

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
    node.querySelector('.loc').textContent = `${r.province || '-'} เขต ${r.district_number || '-'}`;
    const form = node.querySelector('.form');
    form.append(makeChip(r.form_type === 'party_list' ? 'Party List' : 'Constituency', `form-chip ${r.form_type}`));
    node.querySelector('.valid').textContent = r.valid_votes_extracted ?? '-';

    const checks = node.querySelector('.checks');
    checks.append(makeChip(r.weak_summary ? 'Weak summary' : 'Strong summary', `check-chip ${r.weak_summary ? 'warn' : 'ok'}`));
    if (r.ocr_check) {
      checks.append(makeChip(r.ocr_check.exact ? 'OCR exact' : `OCR delta ${r.ocr_check.delta}`, `check-chip ${r.ocr_check.exact ? 'ok' : 'bad'}`));
    }

    const preview = node.querySelector('.preview');
    const a = document.createElement('a');
    a.href = r.drive_url || '#';
    a.target = '_blank';
    a.rel = 'noopener noreferrer';
    a.textContent = r.name || r.drive_id;
    preview.append(a);
    const div = document.createElement('div');
    div.textContent = r.summary_preview || '-';
    preview.append(div);

    els.tableBody.append(node);
  });
  els.rowCount.textContent = `${rows.length} rows`;
}

function applyFilters() {
  const q = (els.search.value || '').trim().toLowerCase();
  const province = els.province.value;
  const form = els.form.value;
  const quality = els.quality.value;

  state.filtered = state.items.filter((r) => {
    if (province && r.province !== province) return false;
    if (form && r.form_type !== form) return false;
    if (quality === 'strong' && r.weak_summary) return false;
    if (quality === 'weak' && !r.weak_summary) return false;
    if (quality === 'ocr_exact' && !(r.ocr_check && r.ocr_check.exact)) return false;
    if (!q) return true;
    const hay = `${r.name || ''} ${r.province || ''} ${r.district_number || ''} ${r.drive_id || ''}`.toLowerCase();
    return hay.includes(q);
  });

  renderRows(state.filtered);
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
  applyFilters();
}

init().catch((err) => {
  els.generatedAt.textContent = `Failed to load data: ${err.message}`;
});
