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
  detailCompareMeta: document.getElementById('detailCompareMeta'),
  detailBody: document.getElementById('detailBody'),
  skewBody: document.getElementById('skewBody'),
  skewCount: document.getElementById('skewCount'),
  mismatchBody: document.getElementById('mismatchBody'),
  mismatchCount: document.getElementById('mismatchCount'),
  coverageBody: document.getElementById('coverageBody'),
  coverageCount: document.getElementById('coverageCount'),
  irregularityBody: document.getElementById('irregularityBody'),
  irregularityCount: document.getElementById('irregularityCount'),
  heatmapBody: document.getElementById('heatmapBody'),
  heatmapCount: document.getElementById('heatmapCount')
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
  const mismatchRows = computeMismatchRows(state.items);
  const coverageRows = computeCoverageRows(state.items);
  const irregularityRows = computeIrregularityRows(state.items);
  const withEct = state.items.filter((r) => numOrNull(r?.sources?.ect?.valid_votes) !== null).length;
  const withVote62 = state.items.filter((r) => numOrNull(r?.sources?.vote62?.valid_votes) !== null).length;
  const withKillernay = state.items.filter((r) => numOrNull(r?.sources?.killernay?.valid_votes) !== null).length;
  const withRead = state.items.filter((r) => numOrNull(r?.valid_votes_extracted) !== null).length;
  els.kpiGrid.innerHTML = '';
  els.kpiGrid.append(
    kpi('Total Files', summary.total_files ?? 0),
    kpi('Strong Summaries', (summary.total_files ?? 0) - (summary.weak_summaries ?? 0)),
    kpi('Weak Summaries', summary.weak_summaries ?? 0),
    kpi('With Valid Votes', summary.with_valid_votes ?? 0),
    kpi('OCR Exact', summary.ocr_exact_matches ?? 0),
    kpi('Skew Districts', skewRows.length),
    kpi('Top Mismatch Rows', mismatchRows.length),
    kpi('Coverage Gaps', coverageRows.length),
    kpi('Irregularity Signals', irregularityRows.length),
    kpi('With Read', withRead),
    kpi('With ECT', withEct),
    kpi('With vote62', withVote62),
    kpi('With killernay', withKillernay)
  );
}

function sourceValidValues(row) {
  const read = numOrNull(row?.valid_votes_extracted ?? row?.sources?.read?.valid_votes);
  const ect = numOrNull(row?.sources?.ect?.valid_votes);
  const vote62 = numOrNull(row?.sources?.vote62?.valid_votes);
  const killernay = numOrNull(row?.sources?.killernay?.valid_votes);
  return { read, ect, vote62, killernay };
}

function sourceSpread(row) {
  const vals = Object.values(sourceValidValues(row)).filter((v) => v !== null);
  if (!vals.length) return null;
  return Math.max(...vals) - Math.min(...vals);
}

function valueStatusChip(ok) {
  if (ok) return makeChip('Yes', 'form-chip constituency');
  return makeChip('No', 'form-chip party_list');
}

function winnerNumber(votesObj) {
  const entries = Object.entries(votesObj || {}).map(([k, v]) => [String(k), numOrNull(v)]).filter(([, v]) => v !== null);
  if (!entries.length) return null;
  entries.sort((a, b) => b[1] - a[1] || Number(a[0]) - Number(b[0]));
  return entries[0][0];
}

function winnerDisagreement(row) {
  const src = row?.sources || {};
  const wins = [
    winnerNumber(row?.votes || {}),
    winnerNumber(src?.ect?.votes || {}),
    winnerNumber(src?.vote62?.votes || {}),
    winnerNumber(src?.killernay?.votes || {})
  ].filter((x) => x !== null);
  if (wins.length < 2) return false;
  return new Set(wins).size > 1;
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
    const vals = sourceValidValues(r);
    node.querySelector('.readValid').textContent = vals.read === null ? '-' : vals.read.toLocaleString();
    node.querySelector('.ectValid').textContent = vals.ect === null ? '-' : vals.ect.toLocaleString();
    node.querySelector('.vote62Valid').textContent = vals.vote62 === null ? '-' : vals.vote62.toLocaleString();
    node.querySelector('.killernayValid').textContent = vals.killernay === null ? '-' : vals.killernay.toLocaleString();
    const spread = sourceSpread(r);
    node.querySelector('.spread').textContent = spread === null ? '-' : spread.toLocaleString();
    const flagsCell = node.querySelector('.flags');
    if (spread !== null && spread >= 1000) {
      flagsCell.append(makeChip('High spread', 'form-chip party_list'));
    } else if (spread !== null && spread >= 100) {
      flagsCell.append(makeChip('Spread', 'form-chip constituency'));
    }
    if (winnerDisagreement(r)) {
      flagsCell.append(makeChip('Winner mismatch', 'form-chip party_list'));
    }
    if (!flagsCell.hasChildNodes()) {
      flagsCell.append(makeChip('OK', 'form-chip constituency'));
    }

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
    if (els.detailCompareMeta) els.detailCompareMeta.innerHTML = '';
    els.detailBody.innerHTML = '';
    return;
  }
  const label = row.form_type === 'party_list' ? '(Party List)' : '(Constituency)';
  els.detailTitle.textContent = `${row.province || '-'} เขต ${row.district_number || '-'} ${label}`;
  els.detailMeta.textContent = `Valid votes: ${row.valid_votes_extracted ?? '-'}`;
  if (els.detailCompareMeta) {
    const readValid = numOrNull(row.valid_votes_extracted);
    const ectValid = numOrNull(row?.sources?.ect?.valid_votes);
    const vote62Valid = numOrNull(row?.sources?.vote62?.valid_votes);
    const killernayValid = numOrNull(row?.sources?.killernay?.valid_votes);
    const readInvalid = numOrNull(row?.invalid_votes ?? row?.sources?.read?.invalid_votes);
    const readBlank = numOrNull(row?.blank_votes ?? row?.sources?.read?.blank_votes);
    const ectInvalid = numOrNull(row?.sources?.ect?.invalid_votes);
    const ectBlank = numOrNull(row?.sources?.ect?.blank_votes);
    const deltaEct = readValid !== null && ectValid !== null ? readValid - ectValid : null;
    const deltaVote62 = readValid !== null && vote62Valid !== null ? readValid - vote62Valid : null;
    const deltaKillernay = readValid !== null && killernayValid !== null ? readValid - killernayValid : null;
    const pieces = [
      `Read valid: <span class="mono">${readValid === null ? '-' : readValid.toLocaleString()}</span>`,
      `Read invalid: <span class="mono">${readInvalid === null ? '-' : readInvalid.toLocaleString()}</span>`,
      `Read blank: <span class="mono">${readBlank === null ? '-' : readBlank.toLocaleString()}</span>`,
      `ECT: <span class="mono">${ectValid === null ? '-' : ectValid.toLocaleString()}</span>`,
      `ECT invalid: <span class="mono">${ectInvalid === null ? '-' : ectInvalid.toLocaleString()}</span>`,
      `ECT blank: <span class="mono">${ectBlank === null ? '-' : ectBlank.toLocaleString()}</span>`,
      `ΔECT: <span class="mono">${deltaEct === null ? '-' : deltaEct.toLocaleString()}</span>`,
      `vote62: <span class="mono">${vote62Valid === null ? '-' : vote62Valid.toLocaleString()}</span>`,
      `Δvote62: <span class="mono">${deltaVote62 === null ? '-' : deltaVote62.toLocaleString()}</span>`,
      `killernay: <span class="mono">${killernayValid === null ? '-' : killernayValid.toLocaleString()}</span>`,
      `Δkillernay: <span class="mono">${deltaKillernay === null ? '-' : deltaKillernay.toLocaleString()}</span>`
    ];
    els.detailCompareMeta.innerHTML = pieces.map((x) => `<span class="meta-pill">${x}</span>`).join('');
  }
  els.detailBody.innerHTML = '';

  const readVotes = row.votes || {};
  const ectVotes = row?.sources?.ect?.votes || {};
  const vote62Votes = row?.sources?.vote62?.votes || {};
  const killernayVotes = row?.sources?.killernay?.votes || {};
  const names = row.form_type === 'party_list' ? (row.party_names || {}) : (row.candidate_names || {});
  const parties = row.candidate_parties || {};
  const allNumbers = new Set([
    ...Object.keys(readVotes),
    ...Object.keys(ectVotes),
    ...Object.keys(vote62Votes),
    ...Object.keys(killernayVotes)
  ]);

  const rows = [...allNumbers]
    .map((number) => {
      const read = numOrNull(readVotes[number]);
      const ect = numOrNull(ectVotes[number]);
      const vote62 = numOrNull(vote62Votes[number]);
      const killernay = numOrNull(killernayVotes[number]);
      return { number, read, ect, vote62, killernay };
    })
    .sort((a, b) => (b.read ?? -1) - (a.read ?? -1) || Number(a.number) - Number(b.number));

  rows.forEach(({ number, read, ect, vote62, killernay }) => {
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
    const readCell = document.createElement('td');
    readCell.className = 'mono';
    readCell.textContent = read === null ? '-' : read.toLocaleString();
    const ectCell = document.createElement('td');
    ectCell.className = 'mono';
    ectCell.textContent = ect === null ? '-' : ect.toLocaleString();
    const v62Cell = document.createElement('td');
    v62Cell.className = 'mono';
    v62Cell.textContent = vote62 === null ? '-' : vote62.toLocaleString();
    const kCell = document.createElement('td');
    kCell.className = 'mono';
    kCell.textContent = killernay === null ? '-' : killernay.toLocaleString();
    tr.append(no, nm, readCell, ectCell, v62Cell, kCell);
    els.detailBody.append(tr);
  });
}

function rowTotals(row) {
  const valid = numOrNull(row?.valid_votes_extracted ?? row?.valid_votes ?? row?.sources?.read?.valid_votes);
  const invalid = numOrNull(
    row?.invalid_votes ??
    row?.sources?.read?.invalid_votes ??
    row?.sources?.ect?.invalid_votes ??
    row?.sources?.vote62?.invalid_votes
  );
  const blank = numOrNull(
    row?.blank_votes ??
    row?.sources?.read?.blank_votes ??
    row?.sources?.ect?.blank_votes ??
    row?.sources?.vote62?.blank_votes
  );
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

function computeMismatchRows(items) {
  const out = [];
  items.forEach((r) => {
    const read = numOrNull(r.valid_votes_extracted);
    const ect = numOrNull(r?.sources?.ect?.valid_votes);
    const vote62 = numOrNull(r?.sources?.vote62?.valid_votes);
    if (read === null) return;
    const dE = ect === null ? null : read - ect;
    const dV = vote62 === null ? null : read - vote62;
    const score = Math.max(Math.abs(dE ?? 0), Math.abs(dV ?? 0));
    if (score === 0) return;
    out.push({
      province: r.province,
      district_number: r.district_number,
      form_type: r.form_type,
      drive_url: resolveDriveUrl(r),
      read,
      ect,
      vote62,
      delta_ect: dE,
      delta_vote62: dV,
      score
    });
  });
  return out.sort((a, b) => b.score - a.score || a.province.localeCompare(b.province, 'th') || Number(a.district_number) - Number(b.district_number));
}

function computeCoverageRows(items) {
  return items
    .map((r) => {
      const vals = sourceValidValues(r);
      return {
        row: r,
        hasRead: vals.read !== null,
        hasEct: vals.ect !== null,
        hasVote62: vals.vote62 !== null,
        hasKillernay: vals.killernay !== null
      };
    })
    .filter((x) => !(x.hasRead && x.hasEct && x.hasVote62 && x.hasKillernay))
    .sort((a, b) =>
      String(a.row.province || '').localeCompare(String(b.row.province || ''), 'th')
      || Number(a.row.district_number || 0) - Number(b.row.district_number || 0)
      || String(a.row.form_type || '').localeCompare(String(b.row.form_type || ''), 'en')
    );
}

function renderCoverageTable(items, limit = 300) {
  if (!els.coverageBody || !els.coverageCount) return;
  const rows = computeCoverageRows(items).slice(0, limit);
  els.coverageBody.innerHTML = '';
  rows.forEach(({ row, hasRead, hasEct, hasVote62, hasKillernay }) => {
    const tr = document.createElement('tr');
    const loc = document.createElement('td');
    const text = `${row.province || '-'} เขต ${row.district_number || '-'}${resolveDriveUrl(row) ? '' : ' (no file)'}`;
    loc.textContent = text;
    const form = document.createElement('td');
    form.textContent = row.form_type === 'party_list' ? 'Party List' : 'Constituency';
    const read = document.createElement('td');
    read.append(valueStatusChip(hasRead));
    const ect = document.createElement('td');
    ect.append(valueStatusChip(hasEct));
    const v62 = document.createElement('td');
    v62.append(valueStatusChip(hasVote62));
    const k = document.createElement('td');
    k.append(valueStatusChip(hasKillernay));
    tr.append(loc, form, read, ect, v62, k);
    els.coverageBody.append(tr);
  });
  els.coverageCount.textContent = `${rows.length} rows`;
}

function computeIrregularityRows(items) {
  const rows = [];
  items.forEach((r) => {
    const vals = sourceValidValues(r);
    const spread = sourceSpread(r);
    const inv = numOrNull(r?.invalid_votes ?? r?.sources?.read?.invalid_votes);
    const blank = numOrNull(r?.blank_votes ?? r?.sources?.read?.blank_votes);
    const read = vals.read;
    const badRate = (read !== null && inv !== null && blank !== null && read > 0) ? ((inv + blank) / read) : null;
    const winMismatch = winnerDisagreement(r);
    const flags = [];
    let severity = 0;

    if (spread !== null && spread >= 1000) {
      flags.push('high_source_spread');
      severity += 3;
    } else if (spread !== null && spread >= 200) {
      flags.push('source_spread');
      severity += 2;
    }
    if (badRate !== null && badRate >= 0.10) {
      flags.push('high_invalid_blank_ratio');
      severity += 2;
    }
    if (winMismatch) {
      flags.push('winner_disagreement');
      severity += 2;
    }
    if (!flags.length) return;
    let tier = 'P3';
    if (severity >= 5) tier = 'P1';
    else if (severity >= 3) tier = 'P2';
    rows.push({
      row: r,
      severity,
      tier,
      spread,
      badRate,
      flags
    });
  });
  return rows.sort((a, b) =>
    b.severity - a.severity
    || (b.spread ?? 0) - (a.spread ?? 0)
    || String(a.row.province || '').localeCompare(String(b.row.province || ''), 'th')
    || Number(a.row.district_number || 0) - Number(b.row.district_number || 0)
  );
}

function renderIrregularityTable(items, limit = 200) {
  if (!els.irregularityBody || !els.irregularityCount) return;
  const rows = computeIrregularityRows(items).slice(0, limit);
  els.irregularityBody.innerHTML = '';
  rows.forEach(({ row, severity, tier, spread, badRate, flags }) => {
    const tr = document.createElement('tr');
    const loc = document.createElement('td');
    loc.textContent = `${row.province || '-'} เขต ${row.district_number || '-'}`;
    const form = document.createElement('td');
    form.textContent = row.form_type === 'party_list' ? 'Party List' : 'Constituency';
    const sev = document.createElement('td');
    sev.className = 'mono';
    sev.innerHTML = `<span class="severity-chip ${tier.toLowerCase()}">${tier}</span> <span class="mono">${severity}</span>`;
    const sp = document.createElement('td');
    sp.className = 'mono';
    sp.textContent = spread === null ? '-' : spread.toLocaleString();
    const br = document.createElement('td');
    br.className = 'mono';
    br.textContent = badRate === null ? '-' : `${(badRate * 100).toFixed(2)}%`;
    const fg = document.createElement('td');
    flags.forEach((f) => fg.append(makeChip(f, 'form-chip party_list')));
    tr.append(loc, form, sev, sp, br, fg);
    els.irregularityBody.append(tr);
  });
  els.irregularityCount.textContent = `${rows.length} rows`;
}

function computeProvinceHeatmap(items) {
  const irr = computeIrregularityRows(items);
  const byProv = new Map();
  irr.forEach((x) => {
    const p = String(x?.row?.province || '').trim() || '-';
    if (!byProv.has(p)) byProv.set(p, { province: p, total: 0, p1: 0, p2: 0, p3: 0 });
    const agg = byProv.get(p);
    agg.total += 1;
    if (x.tier === 'P1') agg.p1 += 1;
    else if (x.tier === 'P2') agg.p2 += 1;
    else agg.p3 += 1;
  });
  return [...byProv.values()].sort((a, b) =>
    b.total - a.total || b.p1 - a.p1 || a.province.localeCompare(b.province, 'th')
  );
}

function renderProvinceHeatmap(items, limit = 100) {
  if (!els.heatmapBody || !els.heatmapCount) return;
  const rows = computeProvinceHeatmap(items).slice(0, limit);
  els.heatmapBody.innerHTML = '';
  rows.forEach((r) => {
    const tr = document.createElement('tr');
    const p = document.createElement('td');
    p.textContent = r.province;
    const total = document.createElement('td');
    total.className = 'mono';
    total.textContent = r.total.toLocaleString();
    const p1 = document.createElement('td');
    p1.className = 'mono';
    p1.textContent = r.p1.toLocaleString();
    const p2 = document.createElement('td');
    p2.className = 'mono';
    p2.textContent = r.p2.toLocaleString();
    const p3 = document.createElement('td');
    p3.className = 'mono';
    p3.textContent = r.p3.toLocaleString();
    tr.append(p, total, p1, p2, p3);
    els.heatmapBody.append(tr);
  });
  els.heatmapCount.textContent = `${rows.length} provinces`;
}

function renderMismatchTable(items, limit = 120) {
  if (!els.mismatchBody || !els.mismatchCount) return;
  const rows = computeMismatchRows(items).slice(0, limit);
  els.mismatchBody.innerHTML = '';
  rows.forEach((r) => {
    const tr = document.createElement('tr');
    const loc = document.createElement('td');
    const text = `${r.province} เขต ${r.district_number}`;
    if (r.drive_url) {
      const a = document.createElement('a');
      a.href = r.drive_url;
      a.target = '_blank';
      a.rel = 'noopener noreferrer';
      a.className = 'loc-link';
      a.textContent = text;
      loc.append(a);
    } else {
      loc.textContent = text;
    }
    const form = document.createElement('td');
    form.textContent = r.form_type === 'party_list' ? 'Party List' : 'Constituency';
    const read = document.createElement('td');
    read.className = 'mono';
    read.textContent = r.read.toLocaleString();
    const ect = document.createElement('td');
    ect.className = 'mono';
    ect.textContent = r.ect === null ? '-' : r.ect.toLocaleString();
    const de = document.createElement('td');
    de.className = 'mono';
    de.textContent = r.delta_ect === null ? '-' : r.delta_ect.toLocaleString();
    const v62 = document.createElement('td');
    v62.className = 'mono';
    v62.textContent = r.vote62 === null ? '-' : r.vote62.toLocaleString();
    const dv = document.createElement('td');
    dv.className = 'mono';
    dv.textContent = r.delta_vote62 === null ? '-' : r.delta_vote62.toLocaleString();
    tr.append(loc, form, read, ect, de, v62, dv);
    els.mismatchBody.append(tr);
  });
  els.mismatchCount.textContent = `${rows.length} rows`;
}

function applyFilters() {
  const q = (els.search.value || '').trim().toLowerCase();
  const province = els.province.value;
  const form = els.form.value;
  const forcedForm = (state.view === 'all' || state.view === 'missing_ect') ? '' : state.view;
  const quality = els.quality.value;

  state.filtered = state.items.filter((r) => {
    if (province && r.province !== province) return false;
    if (forcedForm && r.form_type !== forcedForm) return false;
    if (state.view === 'missing_ect' && numOrNull(r?.sources?.ect?.valid_votes) !== null) return false;
    if (form && r.form_type !== form) return false;
    if (quality === 'strong' && r.weak_summary) return false;
    if (quality === 'weak' && !r.weak_summary) return false;
    if (quality === 'ocr_exact' && !(r.ocr_check && r.ocr_check.exact)) return false;
    if (!q) return true;
    const hay = `${r.name || ''} ${r.province || ''} ${r.district_number || ''} ${r.drive_id || ''}`.toLowerCase();
    return hay.includes(q);
  }).sort((a, b) => {
    const ap = String(a.province || '');
    const bp = String(b.province || '');
    const pcmp = ap.localeCompare(bp, 'th');
    if (pcmp !== 0) return pcmp;
    const ad = Number(a.district_number || 0);
    const bd = Number(b.district_number || 0);
    if (ad !== bd) return ad - bd;
    return String(a.form_type || '').localeCompare(String(b.form_type || ''), 'en');
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
  const dataVersion = '20260221-k3';
  const res = await fetch(`./data/district_dashboard_data.json?v=${dataVersion}`);
  const data = await res.json();
  state.items = data.items || [];

  els.generatedAt.textContent = `Generated: ${data.generated_at || '-'} • Source: OCR extraction pipeline`;
  renderKPIs(data.summary || {});
  renderCoverageTable(state.items);
  renderIrregularityTable(state.items);
  renderProvinceHeatmap(state.items);
  renderSkewTable(state.items);
  renderMismatchTable(state.items);

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
