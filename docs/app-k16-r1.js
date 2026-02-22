console.info('[Election69 Dashboard] app-k16 loaded', new Date().toISOString());

const els = {
  kpiGrid: document.getElementById('kpiGrid'),
  generatedAt: document.getElementById('generatedAt'),
  tableBody: document.getElementById('tableBody'),
  rowCount: document.getElementById('rowCount'),
  search: document.getElementById('searchInput'),
  province: document.getElementById('provinceSelect'),
  form: document.getElementById('formSelect'),
  quality: document.getElementById('qualitySelect'),
  seatMode: document.getElementById('seatMode'),
  rowTemplate: document.getElementById('rowTemplate'),
  viewTabs: document.getElementById('viewTabs'),
  sectionTabs: document.getElementById('sectionTabs'),
  detailTitle: document.getElementById('detailTitle'),
  detailMeta: document.getElementById('detailMeta'),
  detailCompareMeta: document.getElementById('detailCompareMeta'),
  detailBody: document.getElementById('detailBody'),
  skewBody: document.getElementById('skewBody'),
  skewCount: document.getElementById('skewCount'),
  skewSummary: document.getElementById('skewSummary'),
  mismatchBody: document.getElementById('mismatchBody'),
  mismatchCount: document.getElementById('mismatchCount'),
  coverageBody: document.getElementById('coverageBody'),
  coverageCount: document.getElementById('coverageCount'),
  irregularityBody: document.getElementById('irregularityBody'),
  irregularityCount: document.getElementById('irregularityCount'),
  heatmapBody: document.getElementById('heatmapBody'),
  heatmapCount: document.getElementById('heatmapCount'),
  skewMap: document.getElementById('skewMap'),
  skewMapCount: document.getElementById('skewMapCount'),
  winnerMismatchEctBody: document.getElementById('winnerMismatchEctBody'),
  winnerMismatchEctCount: document.getElementById('winnerMismatchEctCount'),
  winnerMismatchVote62Body: document.getElementById('winnerMismatchVote62Body'),
  winnerMismatchVote62Count: document.getElementById('winnerMismatchVote62Count'),
  seatSummaryBody: document.getElementById('seatSummaryBody'),
  seatSummaryMeta: document.getElementById('seatSummaryMeta'),
  closeRaceBody: document.getElementById('closeRaceBody'),
  closeRaceCount: document.getElementById('closeRaceCount'),
  qualityBody: document.getElementById('qualityBody'),
  qualityCount: document.getElementById('qualityCount')
};

let state = { items: [], filtered: [], view: 'all', section: 'overview', selected: null, partyMap: {} };
let skewMapInstance = null;
let skewGeoLayer = null;
let skewGeoPromise = null;
const sectionPanes = [...document.querySelectorAll('[data-section-pane]')];

const PARTY_MAP_FALLBACK = {"1": "ไทยทรัพย์ทวี", "10": "ทางเลือกใหม่", "11": "เศรษฐกิจ", "12": "เสรีรวมไทย", "13": "รวมพลังประชาชน", "14": "ท้องที่ไทย", "15": "อนาคตไทย", "16": "พลังเพื่อไทย", "17": "ไทยชนะ", "18": "พลังสังคมใหม่", "19": "สังคมประชาธิปไตยไทย", "2": "เพื่อชาติไทย", "20": "ฟิวชัน", "21": "ไทรวมพลัง", "22": "ก้าวอิสระ", "23": "ปวงชนไทย", "24": "วิชชั่นใหม่", "25": "เพื่อชีวิตใหม่", "26": "คลองไทย", "27": "ประชาธิปัตย์", "28": "ไทยก้าวหน้า", "29": "ไทยภักดี", "3": "ใหม่", "30": "แรงงานสร้างชาติ", "31": "ประชากรไทย", "32": "ครูไทยเพื่อประชาชน", "33": "ประชาชาติ", "34": "สร้างอนาคตไทย", "35": "รักชาติ", "36": "ไทยพร้อม", "37": "ภูมิใจไทย", "38": "พลังธรรมใหม่", "39": "กรีน", "4": "มิติใหม่", "40": "ไทยธรรม", "41": "แผ่นดินธรรม", "42": "กล้าธรรม", "43": "พลังประชารัฐ", "44": "โอกาสใหม่", "45": "เป็นธรรม", "46": "ประชาชน", "47": "ประชาไทย", "48": "ไทยสร้างไทย", "49": "ไทยก้าวใหม่", "5": "รวมใจไทย", "50": "ประชาอาสาชาติ", "51": "พร้อม", "52": "เครือข่ายชาวนาแห่งประเทศไทย", "53": "ไทยพิทักษ์ธรรม", "54": "ความหวังใหม่", "55": "ไทยรวมไทย", "56": "เพื่อบ้านเมือง", "57": "พลังไทยรักชาติ", "6": "รวมไทยสร้างชาติ", "7": "พลวัต", "8": "ประชาธิปไตยใหม่", "9": "เพื่อไทย"};

const NO_FILE_REASON_MAP = new Map([
  ['กรุงเทพมหานคร|15', 'กกต. ยังไม่ประกาศ'],
  ['ลพบุรี|4', 'กกต. อัพโหลด PDF ผิด (เป็นเอกสารเขต 1)'],
  ['นครพนม|2', 'รอตรวจสอบ'],
  ['บุรีรัมย์|1', 'ไม่มี PDF จาก กกต.'],
  ['บุรีรัมย์|2', 'ไม่มี PDF จาก กกต.'],
  ['บุรีรัมย์|3', 'ไม่มี PDF จาก กกต.'],
  ['บุรีรัมย์|4', 'ไม่มี PDF จาก กกต.'],
  ['บุรีรัมย์|5', 'ไม่มี PDF จาก กกต.'],
  ['บุรีรัมย์|6', 'ไม่มี PDF จาก กกต.'],
  ['บุรีรัมย์|7', 'ไม่มี PDF จาก กกต.'],
  ['บุรีรัมย์|8', 'ไม่มี PDF จาก กกต.'],
  ['บุรีรัมย์|9', 'ไม่มี PDF จาก กกต.'],
  ['บุรีรัมย์|10', 'ไม่มี PDF จาก กกต.'],
  ['ปราจีนบุรี|2', 'รอตรวจสอบ'],
  ['อุดรธานี|6', 'กกต. ยังไม่ประกาศ']
]);

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

function noFileReason(row) {
  const key = `${String(row?.province || '').trim()}|${Number(row?.district_number || 0)}`;
  return NO_FILE_REASON_MAP.get(key) || 'ยังไม่มีไฟล์ในชุดข้อมูล';
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

function irregularityFlagLabel(flag) {
  const map = {
    high_delta_killernay: 'ต่างจาก killernay สูง',
    delta_killernay: 'ต่างจาก killernay',
    high_invalid_blank_ratio: 'สัดส่วนบัตรเสีย+ไม่เลือกสูง',
    winner_disagreement: 'ผู้ชนะไม่ตรงกัน',
    vote62_far_from_read: 'ต่างจาก vote62 มาก'
  };
  return map[flag] || String(flag || '-');
}

function renderKPIs(summary) {
  const skewRows = computeSkewRows(state.items);
  const mismatchRows = computeMismatchRows(state.items);
  const coverageRows = computeCoverageRows(state.items);
  const irregularityRows = computeIrregularityRows(state.items);
  const totalRows = state.items.length;
  const realFileIds = new Set(
    state.items
      .map((r) => String(r?.drive_id || '').trim())
      .filter((id) => id && !id.startsWith('missing::'))
  );
  const totalFiles = realFileIds.size;
  const withEct = state.items.filter((r) => numOrNull(r?.sources?.ect?.valid_votes) !== null).length;
  const withVote62 = state.items.filter((r) => numOrNull(r?.sources?.vote62?.valid_votes) !== null).length;
  const withKillernay = state.items.filter((r) => numOrNull(r?.sources?.killernay?.valid_votes) !== null).length;
  const withRead = state.items.filter((r) => numOrNull(r?.valid_votes_extracted) !== null).length;
  const weakRead = state.items.filter((r) => numOrNull(r?.valid_votes_extracted) !== null && !!r.weak_summary).length;
  els.kpiGrid.innerHTML = '';
  els.kpiGrid.append(
    kpi('จำนวนไฟล์ทั้งหมด', totalFiles),
    kpi('จำนวนแถวข้อมูล', totalRows),
    kpi('สรุปชัดเจน', withRead - weakRead),
    kpi('สรุปอ่อน', weakRead),
    kpi('มีบัตรดี', summary.with_valid_votes ?? 0),
    kpi('OCR ตรงเป๊ะ', summary.ocr_exact_matches ?? 0),
    kpi('เขตที่เขย่ง', skewRows.length),
    kpi('แถวต่างสูงสุด', mismatchRows.length),
    kpi('ช่องว่างข้อมูล', coverageRows.length),
    kpi('สัญญาณผิดปกติ', irregularityRows.length),
    kpi('มีข้อมูลอ่านได้', withRead),
    kpi('มีข้อมูล ECT', withEct),
    kpi('มีข้อมูล vote62', withVote62),
    kpi('มีข้อมูล killernay', withKillernay)
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
  // Primary spread excludes vote62 because it is volunteer-sourced and can be noisy.
  const s = sourceValidValues(row);
  const vals = [s.read, s.ect, s.killernay].filter((v) => v !== null);
  if (!vals.length) return null;
  return Math.max(...vals) - Math.min(...vals);
}

function sourceSpreadAll(row) {
  const vals = Object.values(sourceValidValues(row)).filter((v) => v !== null);
  if (!vals.length) return null;
  return Math.max(...vals) - Math.min(...vals);
}

function vote62Gap(row) {
  const s = sourceValidValues(row);
  if (s.read === null || s.vote62 === null) return null;
  return s.read - s.vote62;
}

function killernayGap(row) {
  const s = sourceValidValues(row);
  if (s.read === null || s.killernay === null) return null;
  return s.read - s.killernay;
}

function valueStatusChip(ok) {
  if (ok) return makeChip('มี', 'form-chip constituency');
  return makeChip('ไม่มี', 'form-chip party_list');
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
    winnerNumber(src?.killernay?.votes || {})
  ].filter((x) => x !== null);
  if (wins.length < 2) return false;
  return new Set(wins).size > 1;
}

function sourceVotes(row, sourceKey) {
  if (sourceKey === 'latest') return row?.votes || {};
  return row?.sources?.[sourceKey]?.votes || {};
}

function normalizePartyNo(row, sourceKey, num) {
  const n = Number(num);
  if (!Number.isFinite(n)) return String(num);
  if (row?.form_type !== 'party_list') return String(n);
  if (sourceKey !== 'latest' && sourceKey !== 'killernay') return String(n);
  const ectVotes = row?.sources?.ect?.votes || {};
  const srcVotes = sourceVotes(row, sourceKey);
  const ectKeys = new Set(Object.keys(ectVotes || {}).filter((k) => /^\d+$/.test(String(k))).map((k) => Number(k)));
  const srcKeys = Object.keys(srcVotes || {}).filter((k) => /^\d+$/.test(String(k))).map((k) => Number(k));
  if (!ectKeys.size || !srcKeys.length) return String(n);
  const srcWinner = Number(winnerNumber(srcVotes));
  const ectWinner = Number(winnerNumber(ectVotes));
  if (
    Number.isFinite(srcWinner) &&
    Number.isFinite(ectWinner) &&
    srcWinner === ectWinner + 1 &&
    srcKeys.includes(58) &&
    !ectKeys.has(58) &&
    n > 1
  ) {
    return String(n - 1);
  }
  const srcSet = new Set(srcKeys);
  const minSrc = Math.min(...srcKeys);
  const maxSrc = Math.max(...srcKeys);
  // Common shifted encoding in some latest/killernay rows: party keys become 2..58 instead of 1..57.
  if (srcKeys.length >= 50 && minSrc === 2 && maxSrc === 58 && !srcSet.has(1) && srcSet.has(58) && n > 1) {
    return String(n - 1);
  }
  const direct = srcKeys.reduce((acc, k) => acc + (ectKeys.has(k) ? 1 : 0), 0);
  const minus1 = srcKeys.reduce((acc, k) => acc + (ectKeys.has(k - 1) ? 1 : 0), 0);
  if (minus1 >= direct + 2 && minus1 >= 3 && n > 1) return String(n - 1);
  return String(n);
}

function partyOrNameLabel(row, num, sourceKey = 'latest') {
  const key = normalizePartyNo(row, sourceKey, num);
  if (row?.form_type === 'party_list') {
    return state.partyMap[key] || PARTY_MAP_FALLBACK[key] || row?.candidate_parties?.[key] || row?.candidate_names?.[key] || '';
  }
  return row?.candidate_parties?.[key] || row?.candidate_names?.[key] || '';
}

function displayLabel(row, num, sourceKey = 'latest') {
  const key = normalizePartyNo(row, sourceKey, num);
  const raw = partyOrNameLabel(row, num, sourceKey);
  if (row?.form_type === 'party_list') {
    if (!raw) return `หมายเลข ${key}`;
    return String(raw).startsWith('พรรค') ? String(raw) : `พรรค${raw}`;
  }
  return raw ? `${key} ${raw}` : `หมายเลข ${key}`;
}

function winnerInfo(row, sourceKey) {
  const rawNum = winnerNumber(sourceVotes(row, sourceKey));
  const num = rawNum ? normalizePartyNo(row, sourceKey, rawNum) : null;
  if (!num) return null;
  const label = partyOrNameLabel(row, num, sourceKey);
  const display = displayLabel(row, num, sourceKey);
  return { num, label: `${num}${label ? ` ${label}` : ''}`, display };
}

function topTwo(votesObj) {
  const entries = Object.entries(votesObj || {})
    .map(([k, v]) => [String(k), numOrNull(v)])
    .filter(([, v]) => v !== null)
    .sort((a, b) => b[1] - a[1] || Number(a[0]) - Number(b[0]));
  return entries.slice(0, 2);
}

function latestMarginInfo(row) {
  const tt = topTwo(sourceVotes(row, 'latest'));
  if (!tt.length) return { diff: null, pct: null, first: null, second: null };
  const first = tt[0];
  const second = tt[1] || [null, 0];
  const diff = first[1] - second[1];
  const pct = first[1] > 0 ? (diff / first[1]) * 100 : null;
  return { diff, pct, first: first[0], second: second[0] };
}

function confidenceScore(row) {
  let score = 50;
  if (numOrNull(row?.valid_votes_extracted) !== null) score += 20;
  if (numOrNull(row?.sources?.ect?.valid_votes) !== null) score += 10;
  if (numOrNull(row?.sources?.vote62?.valid_votes) !== null) score += 10;
  if (numOrNull(row?.sources?.killernay?.valid_votes) !== null) score += 10;
  if (row?.weak_summary) score -= 15;
  const kGap = killernayGap(row);
  if (kGap !== null && Math.abs(kGap) >= 1000) score -= 20;
  else if (kGap !== null && Math.abs(kGap) >= 200) score -= 10;
  return Math.max(0, Math.min(100, score));
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
      a.title = 'เปิดไฟล์ต้นทางบน Google Drive';
      a.addEventListener('click', (e) => e.stopPropagation());
      locCell.append(a);
    } else {
      locCell.textContent = locText;
    }
    const form = node.querySelector('.form');
    form.append(makeChip(r.form_type === 'party_list' ? 'บัญชีรายชื่อ' : 'แบ่งเขต', `form-chip ${r.form_type}`));
    const vals = sourceValidValues(r);
    node.querySelector('.readValid').textContent = vals.read === null ? '-' : vals.read.toLocaleString();
    node.querySelector('.ectValid').textContent = vals.ect === null ? '-' : vals.ect.toLocaleString();
    node.querySelector('.vote62Valid').textContent = vals.vote62 === null ? '-' : vals.vote62.toLocaleString();
    node.querySelector('.killernayValid').textContent = vals.killernay === null ? '-' : vals.killernay.toLocaleString();
    const kGap = killernayGap(r);
    const spreadAll = sourceSpreadAll(r);
    const v62Gap = vote62Gap(r);
    node.querySelector('.spread').textContent = kGap === null ? '-' : Math.abs(kGap).toLocaleString();
    const flagsCell = node.querySelector('.flags');
    if (kGap !== null && Math.abs(kGap) >= 1000) {
      flagsCell.append(makeChip('ต่างจาก killernay สูง', 'form-chip party_list'));
    } else if (kGap !== null && Math.abs(kGap) >= 100) {
      flagsCell.append(makeChip('ต่างจาก killernay', 'form-chip constituency'));
    }
    if (winnerDisagreement(r)) {
      flagsCell.append(makeChip('ผู้ชนะไม่ตรงกัน', 'form-chip party_list'));
    }
    if (v62Gap !== null && Math.abs(v62Gap) >= 5000) {
      flagsCell.append(makeChip('ต่างจาก vote62 มาก', 'form-chip constituency'));
    }
    if (spreadAll !== null && kGap !== null && spreadAll > Math.abs(kGap)) {
      flagsCell.append(makeChip('ช่วงต่างรวม vote62 สูง', 'form-chip constituency'));
    }
    if (!flagsCell.hasChildNodes()) {
      flagsCell.append(makeChip('ปกติ', 'form-chip constituency'));
    }

    tr.addEventListener('click', () => {
      state.selected = r;
      renderRows(state.filtered);
      renderDetail(r);
    });
    els.tableBody.append(node);
  });
  els.rowCount.textContent = `${rows.length} รายการ`;
}

function renderDetail(row) {
  if (!row) {
    els.detailTitle.textContent = 'รายละเอียดรายเขต';
    els.detailMeta.textContent = 'เลือกหนึ่งรายการเพื่อดูรายละเอียด';
    if (els.detailCompareMeta) els.detailCompareMeta.innerHTML = '';
    els.detailBody.innerHTML = '';
    return;
  }
  const label = row.form_type === 'party_list' ? '(บัญชีรายชื่อ)' : '(แบ่งเขต)';
  els.detailTitle.textContent = `${row.province || '-'} เขต ${row.district_number || '-'} ${label}`;
  els.detailMeta.textContent = `บัตรดี (อ่านได้): ${row.valid_votes_extracted ?? '-'}`;
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
      `บัตรดี (อ่านได้): <span class="mono">${readValid === null ? '-' : readValid.toLocaleString()}</span>`,
      `บัตรเสีย (อ่านได้): <span class="mono">${readInvalid === null ? '-' : readInvalid.toLocaleString()}</span>`,
      `บัตรไม่เลือก (อ่านได้): <span class="mono">${readBlank === null ? '-' : readBlank.toLocaleString()}</span>`,
      `บัตรดี (ECT): <span class="mono">${ectValid === null ? '-' : ectValid.toLocaleString()}</span>`,
      `บัตรเสีย (ECT): <span class="mono">${ectInvalid === null ? '-' : ectInvalid.toLocaleString()}</span>`,
      `บัตรไม่เลือก (ECT): <span class="mono">${ectBlank === null ? '-' : ectBlank.toLocaleString()}</span>`,
      `ΔECT: <span class="mono">${deltaEct === null ? '-' : deltaEct.toLocaleString()}</span>`,
      `บัตรดี (vote62): <span class="mono">${vote62Valid === null ? '-' : vote62Valid.toLocaleString()}</span>`,
      `Δบัตรดี (vote62): <span class="mono">${deltaVote62 === null ? '-' : deltaVote62.toLocaleString()}</span>`,
      `บัตรดี (killernay): <span class="mono">${killernayValid === null ? '-' : killernayValid.toLocaleString()}</span>`,
      `Δบัตรดี (killernay): <span class="mono">${deltaKillernay === null ? '-' : deltaKillernay.toLocaleString()}</span>`
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
  // For skew logic, always keep a single-source equation:
  // total_used_ballots = valid + invalid + blank from the same "latest/read" source.
  // Do not mix ECT/vote62 fallback fields into this equation.
  const valid = numOrNull(row?.valid_votes_extracted ?? row?.sources?.read?.valid_votes);
  const invalid = numOrNull(row?.invalid_votes ?? row?.sources?.read?.invalid_votes);
  const blank = numOrNull(row?.blank_votes ?? row?.sources?.read?.blank_votes);
  if (valid === null || invalid === null || blank === null) {
    return { valid, invalid, blank, total: null };
  }
  return { valid, invalid, blank, total: valid + invalid + blank };
}

function _collectSkewDistrictRows(items, includeZero = false) {
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
    if (!includeZero && diff === 0) return;
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

function computeSkewRows(items) {
  return _collectSkewDistrictRows(items, false);
}

function computeSkewDistrictRows(items) {
  return _collectSkewDistrictRows(items, true);
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
      c.title = 'เปิดไฟล์ต้นทางแบบแบ่งเขต';
      const sep = document.createElement('span');
      sep.textContent = ' ';
      const p = document.createElement('a');
      p.href = r.p_url || '#';
      p.target = '_blank';
      p.rel = 'noopener noreferrer';
      p.className = 'loc-link';
      p.textContent = '[บช]';
      p.title = 'เปิดไฟล์ต้นทางแบบบัญชีรายชื่อ';
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
    const diffPct = r.p_total > 0 ? (r.diff / r.p_total) * 100 : null;
    diff.textContent = r.diff > 0 ? `+${r.diff.toLocaleString()}` : r.diff.toLocaleString();
    diff.classList.add(r.diff > 0 ? 'diff-pos' : 'diff-neg');
    const diffPctCell = document.createElement('td');
    diffPctCell.className = 'mono';
    diffPctCell.textContent = diffPct === null ? '-' : `${diffPct > 0 ? '+' : ''}${diffPct.toFixed(2)}%`;
    diffPctCell.classList.add(r.diff > 0 ? 'diff-pos' : 'diff-neg');
    const dir = document.createElement('td');
    dir.className = 'mono';
    dir.textContent = r.diff > 0 ? 'เขต > บช' : 'บช > เขต';
    dir.classList.add(r.diff > 0 ? 'diff-pos' : 'diff-neg');
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
    tr.append(loc, cTotal, pTotal, diff, diffPctCell, dir, cInv, cBlk, pInv, pBlk);
    els.skewBody.append(tr);
  });
  els.skewCount.textContent = `${rows.length} รายการ`;
  if (els.skewSummary) {
    const net = rows.reduce((s, r) => s + Number(r.diff || 0), 0);
    const absSum = rows.reduce((s, r) => s + Math.abs(Number(r.diff || 0)), 0);
    const posRows = rows.filter((r) => Number(r.diff || 0) > 0);
    const negRows = rows.filter((r) => Number(r.diff || 0) < 0);
    const posSum = posRows.reduce((s, r) => s + Number(r.diff || 0), 0);
    const negSum = negRows.reduce((s, r) => s + Math.abs(Number(r.diff || 0)), 0);
    const cTotalSum = rows.reduce((s, r) => s + Number(r.c_total || 0), 0);
    const pTotalSum = rows.reduce((s, r) => s + Number(r.p_total || 0), 0);
    const netPct = pTotalSum > 0 ? (net / pTotalSum) * 100 : null;
    els.skewSummary.innerHTML =
      `<span><strong>รวมสุทธิ:</strong> ${net > 0 ? '+' : ''}${net.toLocaleString()}${netPct === null ? '' : ` (${netPct > 0 ? '+' : ''}${netPct.toFixed(2)}%)`}</span>` +
      `<span><strong>รวมค่าสัมบูรณ์:</strong> ${absSum.toLocaleString()}</span>` +
      `<span class="diff-pos"><strong>ฝั่ง +:</strong> ${posSum.toLocaleString()} (${posRows.length} เขต)</span>` +
      `<span class="diff-neg"><strong>ฝั่ง -:</strong> ${negSum.toLocaleString()} (${negRows.length} เขต)</span>` +
      `<span><strong>รวมเขต (บัตรใช้สิทธิ):</strong> ${cTotalSum.toLocaleString()}</span>` +
      `<span><strong>รวมบช (บัตรใช้สิทธิ):</strong> ${pTotalSum.toLocaleString()}</span>` +
      `<span><strong>เกณฑ์:</strong> ใช้ valid+invalid+blank จาก latest/read เท่านั้น</span>`;
  }
}

function computeMismatchRows(items) {
  const out = [];
  items.forEach((r) => {
    const read = numOrNull(r.valid_votes_extracted);
    const killernay = numOrNull(r?.sources?.killernay?.valid_votes);
    const ect = numOrNull(r?.sources?.ect?.valid_votes);
    const vote62 = numOrNull(r?.sources?.vote62?.valid_votes);
    if (read === null) return;
    const dE = ect === null ? null : read - ect;
    const dV = vote62 === null ? null : read - vote62;
    const dK = killernay === null ? null : read - killernay;
    // Primary mismatch list is anchored on killernay (official-style OCR reference).
    if (dK === null || dK === 0) return;
    const score = Math.abs(dK);
    out.push({
      province: r.province,
      district_number: r.district_number,
      form_type: r.form_type,
      drive_url: resolveDriveUrl(r),
      read,
      ect,
      vote62,
      killernay,
      delta_killernay: dK,
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
    const text = resolveDriveUrl(row)
      ? `${row.province || '-'} เขต ${row.district_number || '-'}`
      : `${row.province || '-'} เขต ${row.district_number || '-'} (ไม่มีไฟล์: ${noFileReason(row)})`;
    loc.textContent = text;
    const form = document.createElement('td');
    form.textContent = row.form_type === 'party_list' ? 'บัญชีรายชื่อ' : 'แบ่งเขต';
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
  els.coverageCount.textContent = `${rows.length} รายการ`;
}

function computeIrregularityRows(items) {
  const rows = [];
  items.forEach((r) => {
    const vals = sourceValidValues(r);
    const kGap = killernayGap(r);
    const spreadAll = sourceSpreadAll(r);
    const v62Gap = vote62Gap(r);
    const inv = numOrNull(r?.invalid_votes ?? r?.sources?.read?.invalid_votes);
    const blank = numOrNull(r?.blank_votes ?? r?.sources?.read?.blank_votes);
    const read = vals.read;
    const badRate = (read !== null && inv !== null && blank !== null && read > 0) ? ((inv + blank) / read) : null;
    const winMismatch = (() => {
      const src = r?.sources || {};
      const a = winnerNumber(r?.votes || {});
      const b = winnerNumber(src?.killernay?.votes || {});
      if (a === null || b === null) return false;
      return a !== b;
    })();
    const flags = [];
    let severity = 0;

    if (kGap !== null && Math.abs(kGap) >= 1000) {
      flags.push('high_delta_killernay');
      severity += 3;
    } else if (kGap !== null && Math.abs(kGap) >= 200) {
      flags.push('delta_killernay');
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
    if (v62Gap !== null && Math.abs(v62Gap) >= 5000) {
      // Informational only: vote62 can diverge from official-style sources.
      flags.push('vote62_far_from_read');
    }
    if (severity <= 0) return;
    let tier = 'P3';
    if (severity >= 5) tier = 'P1';
    else if (severity >= 3) tier = 'P2';
    rows.push({
      row: r,
      severity,
      tier,
      spread: kGap === null ? null : Math.abs(kGap),
      spreadAll,
      v62Gap,
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
    form.textContent = row.form_type === 'party_list' ? 'บัญชีรายชื่อ' : 'แบ่งเขต';
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
    flags.forEach((f) => fg.append(makeChip(irregularityFlagLabel(f), 'form-chip party_list')));
    tr.append(loc, form, sev, sp, br, fg);
    els.irregularityBody.append(tr);
  });
  els.irregularityCount.textContent = `${rows.length} รายการ`;
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

function computeSkewProvinceHeatmap(items) {
  const byProv = new Map();
  computeSkewRows(items).forEach((r) => {
    const p = String(r.province || '').trim();
    if (!p) return;
    if (!byProv.has(p)) {
      byProv.set(p, { province: p, skew_rows: 0, abs_diff_sum: 0, max_abs_diff: 0 });
    }
    const agg = byProv.get(p);
    const absDiff = Math.abs(Number(r.diff || 0));
    agg.skew_rows += 1;
    agg.abs_diff_sum += absDiff;
    if (absDiff > agg.max_abs_diff) agg.max_abs_diff = absDiff;
  });
  return [...byProv.values()].sort((a, b) =>
    b.abs_diff_sum - a.abs_diff_sum
    || b.skew_rows - a.skew_rows
    || a.province.localeCompare(b.province, 'th')
  );
}

function decodeThaiMojibake(s) {
  const text = String(s || '');
  if (!text.includes('à')) return text;
  // Convert CP1252-misdecoded UTF-8 back to real UTF-8 bytes.
  const cp1252 = new Map([
    [8364, 0x80], [8218, 0x82], [402, 0x83], [8222, 0x84], [8230, 0x85],
    [8224, 0x86], [8225, 0x87], [710, 0x88], [8240, 0x89], [352, 0x8a],
    [8249, 0x8b], [338, 0x8c], [381, 0x8e], [8216, 0x91], [8217, 0x92],
    [8220, 0x93], [8221, 0x94], [8226, 0x95], [8211, 0x96], [8212, 0x97],
    [732, 0x98], [8482, 0x99], [353, 0x9a], [8250, 0x9b], [339, 0x9c],
    [382, 0x9e], [376, 0x9f]
  ]);
  try {
    const bytes = [];
    for (const ch of text) {
      const code = ch.codePointAt(0);
      if (code <= 255) {
        bytes.push(code);
      } else if (cp1252.has(code)) {
        bytes.push(cp1252.get(code));
      } else {
        return text;
      }
    }
    return new TextDecoder('utf-8', { fatal: false }).decode(Uint8Array.from(bytes));
  } catch (_e) {
    return text;
  }
}

function colorByRatio(ratio) {
  const t = Math.max(0, Math.min(1, ratio));
  // Strong red ramp.
  if (t <= 0.2) return '#fdd9d3';
  if (t <= 0.4) return '#fca082';
  if (t <= 0.6) return '#fb6a4a';
  if (t <= 0.8) return '#de2d26';
  return '#99000d';
}

function colorBySignedRatio(ratio) {
  const t = Math.max(-1, Math.min(1, ratio));
  if (Math.abs(t) < 1e-6) return '#d9d2c6';
  const hexToRgb = (hex) => {
    const m = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
    if (!m) return [0, 0, 0];
    return [parseInt(m[1], 16), parseInt(m[2], 16), parseInt(m[3], 16)];
  };
  const rgbToHex = (r, g, b) =>
    `#${[r, g, b].map((x) => Math.max(0, Math.min(255, Math.round(x))).toString(16).padStart(2, '0')).join('')}`;
  const lerp = (a, b, p) => a + (b - a) * p;

  // Continuous diverging ramp:
  // negative: blue -> neutral, positive: neutral -> red
  const neutral = hexToRgb('#d9d2c6');
  const negDeep = hexToRgb('#0b4f8a');
  const posDeep = hexToRgb('#a50f15');
  const a = Math.abs(t);
  const gamma = 0.72; // boost mid-range contrast
  const p = Math.pow(a, gamma);
  const from = t < 0 ? neutral : neutral;
  const to = t < 0 ? negDeep : posDeep;
  return rgbToHex(lerp(from[0], to[0], p), lerp(from[1], to[1], p), lerp(from[2], to[2], p));
}

function ensureSkewMapBase() {
  if (!els.skewMap || typeof window.L === 'undefined') return null;
  if (skewMapInstance) return skewMapInstance;

  skewMapInstance = window.L.map(els.skewMap, {
    zoomControl: true,
    attributionControl: true
  }).setView([13.2, 101.1], 6);

  // Intentionally no dark tile layer: keep a neutral background for clear heat colors.
  skewMapInstance.getContainer().style.background = '#eef3f7';

  const legend = window.L.control({ position: 'bottomright' });
  legend.onAdd = () => {
    const div = window.L.DomUtil.create('div', 'map-legend');
    div.innerHTML = `
      <div><strong>เขย่งรายเขต (ลงสีพื้นที่)</strong></div>
      <div>แดง: เขต &gt; บช | น้ำเงิน: บช &gt; เขต</div>
      <div class="row"><span class="swatch" style="background:${colorBySignedRatio(-1)}"></span><span>- สูง</span></div>
      <div class="row"><span class="swatch" style="background:${colorBySignedRatio(-0.5)}"></span><span>- กลาง</span></div>
      <div class="row"><span class="swatch" style="background:${colorBySignedRatio(-0.2)}"></span><span>- ต่ำ</span></div>
      <div class="row"><span class="swatch" style="background:${colorBySignedRatio(0)}"></span><span>ปกติ (ไม่เขย่ง)</span></div>
      <div class="row"><span class="swatch" style="background:${colorBySignedRatio(0.2)}"></span><span>+ ต่ำ</span></div>
      <div class="row"><span class="swatch" style="background:${colorBySignedRatio(0.5)}"></span><span>+ กลาง</span></div>
      <div class="row"><span class="swatch" style="background:${colorBySignedRatio(1)}"></span><span>+ สูง</span></div>
      <div class="row"><span class="swatch" style="background:#b7b7b7"></span><span>ไม่มีข้อมูล</span></div>
    `;
    return div;
  };
  legend.addTo(skewMapInstance);
  return skewMapInstance;
}

function loadSkewGeoJson() {
  if (skewGeoPromise) return skewGeoPromise;
  skewGeoPromise = fetch('./data/constituencies_optimized_4dp.geojson')
    .then((res) => {
      if (!res.ok) throw new Error(`geojson_http_${res.status}`);
      return res.json();
    })
    .catch(() => null);
  return skewGeoPromise;
}

async function renderSkewMap(items) {
  if (!els.skewMap || !els.skewMapCount) return;
  const map = ensureSkewMapBase();
  if (!map) {
    els.skewMapCount.textContent = 'ไม่สามารถโหลดแผนที่ได้';
    return;
  }

  const allRows = computeSkewDistrictRows(items);
  const skewRows = allRows.filter((r) => Number(r.diff || 0) !== 0);
  const maxAbsDiff = skewRows.reduce((m, r) => Math.max(m, Math.abs(Number(r.diff || 0))), 0) || 1;
  els.skewMapCount.textContent = `${allRows.length} เขต (ปกติ ${allRows.length - skewRows.length} · เขย่ง ${skewRows.length})`;
  const byDistrict = new Map(allRows.map((r) => [`${String(r.province || '').trim()}|${Number(r.district_number || 0)}`, r]));

  const geo = await loadSkewGeoJson();
  if (!geo || !Array.isArray(geo.features)) {
    els.skewMapCount.textContent = `${allRows.length} เขต (โหลด topology ไม่สำเร็จ)`;
    return;
  }

  if (skewGeoLayer) {
    skewGeoLayer.remove();
    skewGeoLayer = null;
  }

  skewGeoLayer = window.L.geoJSON(geo, {
    style: (feature) => {
      const province = decodeThaiMojibake(feature?.properties?.P_name || '');
      const district = Number(feature?.properties?.CONS_no || 0);
      const hit = byDistrict.get(`${province}|${district}`);
      if (!hit) {
        return {
          color: '#8a8a8a',
          weight: 0.4,
          opacity: 0.9,
          fillColor: '#b7b7b7',
          fillOpacity: 0.72
        };
      }
      const diffVal = Number(hit.diff || 0);
      if (diffVal === 0) {
        return {
          color: '#a8957f',
          weight: 0.5,
          opacity: 0.9,
          fillColor: colorBySignedRatio(0),
          fillOpacity: 0.88
        };
      }
      const signed = diffVal / maxAbsDiff;
      return {
        color: '#5c4630',
        weight: 0.55,
        opacity: 0.95,
        fillColor: colorBySignedRatio(signed),
        fillOpacity: 0.92
      };
    },
    onEachFeature: (feature, layer) => {
      const province = decodeThaiMojibake(feature?.properties?.P_name || '');
      const district = Number(feature?.properties?.CONS_no || 0);
      const hit = byDistrict.get(`${province}|${district}`);
      if (hit) {
        const diffPct = hit.p_total > 0 ? (Number(hit.diff || 0) / Number(hit.p_total)) * 100 : null;
        layer.bindTooltip(
          `${province} เขต ${district}<br>` +
          `ส่วนต่าง: ${hit.diff > 0 ? '+' : ''}${Number(hit.diff || 0).toLocaleString()}<br>` +
          `ส่วนต่าง%: ${diffPct === null ? '-' : `${diffPct > 0 ? '+' : ''}${diffPct.toFixed(2)}%`}<br>` +
          `${Number(hit.diff || 0) === 0 ? 'ปกติ (ไม่เขย่ง)' : (hit.diff > 0 ? 'เขต > บช' : 'บช > เขต')}`,
          { sticky: true }
        );
      } else {
        layer.bindTooltip(`${province} เขต ${district}<br>ไม่มีข้อมูลเขย่ง`, { sticky: true });
      }
      layer.on('mouseover', () => {
        layer.setStyle({ weight: 1.0, opacity: 0.98, fillOpacity: 0.95 });
      });
      layer.on('mouseout', () => {
        skewGeoLayer.resetStyle(layer);
      });
      layer.on('click', () => {
        if (!els.province || !els.search) return;
        els.province.value = province;
        els.search.value = `${district}`;
        applyFilters();
      });
    }
  }).addTo(map);
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
  els.heatmapCount.textContent = `${rows.length} จังหวัด`;
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
    form.textContent = r.form_type === 'party_list' ? 'บัญชีรายชื่อ' : 'แบ่งเขต';
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
  els.mismatchCount.textContent = `${rows.length} รายการ`;
}

function renderWinnerMismatchTable(sourceKey, bodyEl, countEl, includeCoverage = false) {
  if (!bodyEl || !countEl) return;
  const rows = state.filtered
    .map((row) => {
      const wLatest = winnerInfo(row, 'latest');
      const wOther = winnerInfo(row, sourceKey);
      if (!wLatest || !wOther || wLatest.num === wOther.num) return null;
      const margin = latestMarginInfo(row);
      const score = confidenceScore(row);
      const coverage = numOrNull(row?.sources?.vote62?.station_count);
      return { row, wLatest, wOther, margin, score, coverage };
    })
    .filter(Boolean)
    .sort((a, b) =>
      (b.margin.diff ?? 0) - (a.margin.diff ?? 0)
      || String(a.row.province || '').localeCompare(String(b.row.province || ''), 'th')
      || Number(a.row.district_number || 0) - Number(b.row.district_number || 0)
    );

  bodyEl.innerHTML = '';
  rows.slice(0, 300).forEach(({ row, wLatest, wOther, margin, score, coverage }) => {
    const tr = document.createElement('tr');
    const loc = document.createElement('td');
    loc.textContent = `${row.province || '-'} เขต ${row.district_number || '-'}`;
    const form = document.createElement('td');
    form.textContent = row.form_type === 'party_list' ? 'บัญชีรายชื่อ' : 'แบ่งเขต';
    const wl = document.createElement('td');
    wl.textContent = wLatest.display;
    const wo = document.createElement('td');
    wo.textContent = wOther.display;
    const mg = document.createElement('td');
    mg.className = 'mono';
    mg.textContent = margin.diff === null ? '-' : margin.diff.toLocaleString();

    const drive = document.createElement('td');
    const durl = resolveDriveUrl(row);
    if (durl) {
      const a = document.createElement('a');
      a.href = durl;
      a.target = '_blank';
      a.rel = 'noopener noreferrer';
      a.className = 'loc-link';
      a.textContent = 'เปิดไฟล์';
      drive.append(a);
    } else {
      drive.textContent = '-';
    }

    if (includeCoverage) {
      const cov = document.createElement('td');
      cov.className = 'mono';
      cov.textContent = coverage === null ? '-' : `${coverage.toLocaleString()} หน่วย`;
      const badge = document.createElement('td');
      if (coverage !== null && coverage < 20) {
        badge.append(makeChip('Low coverage', 'form-chip party_list'));
      }
      badge.append(makeChip('Volunteer source', 'form-chip constituency'));
      tr.append(loc, form, wl, wo, cov, badge, drive);
    } else {
      const cf = document.createElement('td');
      cf.className = 'mono';
      cf.textContent = `${score}`;
      tr.append(loc, form, wl, wo, mg, drive, cf);
    }

    bodyEl.append(tr);
  });
  countEl.textContent = `${rows.length} รายการ`;
}

function renderSeatSummary() {
  if (!els.seatSummaryBody || !els.seatSummaryMeta) return;
  const mode = (els.seatMode && els.seatMode.value) || 'latest';
  const sourceKey = mode === 'official' ? 'ect' : (mode === 'scenario' ? 'killernay' : 'latest');
  const byParty = new Map();

  const bump = (party, key) => {
    const name = String(party || '-').trim() || '-';
    if (!byParty.has(name)) byParty.set(name, { party: name, mp_zone: 0, party_lead: 0, total: 0 });
    byParty.get(name)[key] += 1;
  };

  state.filtered.forEach((row) => {
    const w = winnerInfo(row, sourceKey);
    if (!w) return;
    const party = partyOrNameLabel(row, w.num) || `หมายเลข ${w.num}`;
    if (row.form_type === 'constituency') bump(party, 'mp_zone');
    if (row.form_type === 'party_list') bump(party, 'party_lead');
  });

  const rows = [...byParty.values()]
    .map((x) => ({ ...x, total: x.mp_zone + x.party_lead }))
    .sort((a, b) => b.total - a.total || b.mp_zone - a.mp_zone || a.party.localeCompare(b.party, 'th'))
    .slice(0, 100);

  els.seatSummaryBody.innerHTML = '';
  rows.forEach((r) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${r.party}</td>
      <td class="mono">${r.mp_zone.toLocaleString()}</td>
      <td class="mono">${r.party_lead.toLocaleString()}</td>
      <td class="mono">${r.total.toLocaleString()}</td>
    `;
    els.seatSummaryBody.append(tr);
  });
  const modeLabel = mode === 'official' ? 'official (ECT)' : mode === 'scenario' ? 'scenario (killernay)' : 'latest verified';
  els.seatSummaryMeta.textContent = `โหมด: ${modeLabel} • หมายเหตุ: คอลัมน์ บช. เป็นจำนวนเขตที่นำคะแนน ไม่ใช่สูตรจัดสรรที่นั่งทางการ`;
}

function renderCloseRaces(limit = 200) {
  if (!els.closeRaceBody || !els.closeRaceCount) return;
  const rows = state.filtered
    .map((row) => {
      const m = latestMarginInfo(row);
      if (m.diff === null || m.second === null) return null;
      const valid = numOrNull(row?.valid_votes_extracted ?? row?.sources?.read?.valid_votes);
      const inv = numOrNull(row?.invalid_votes ?? row?.sources?.read?.invalid_votes);
      const blank = numOrNull(row?.blank_votes ?? row?.sources?.read?.blank_votes);
      const turnout = [valid, inv, blank].every((x) => x !== null) ? valid + inv + blank : null;
      return { row, m, turnout };
    })
    .filter(Boolean)
    .sort((a, b) => a.m.diff - b.m.diff)
    .slice(0, limit);

  els.closeRaceBody.innerHTML = '';
  rows.forEach(({ row, m, turnout }) => {
    const w1 = winnerInfo(row, 'latest');
    const n2 = displayLabel(row, m.second, 'latest');
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${row.province || '-'} เขต ${row.district_number || '-'}</td>
      <td>${row.form_type === 'party_list' ? 'บัญชีรายชื่อ' : 'แบ่งเขต'}</td>
      <td>${w1 ? w1.display : '-'}</td>
      <td>${n2}</td>
      <td class="mono">${m.diff.toLocaleString()}</td>
      <td class="mono">${m.pct === null ? '-' : `${m.pct.toFixed(2)}%`}</td>
      <td class="mono">${turnout === null ? '-' : turnout.toLocaleString()}</td>
    `;
    els.closeRaceBody.append(tr);
  });
  els.closeRaceCount.textContent = `${rows.length} รายการ`;
}

function renderQualityTable(limit = 400) {
  if (!els.qualityBody || !els.qualityCount) return;
  const rows = state.filtered
    .map((row) => ({
      row,
      score: confidenceScore(row),
      hasRead: numOrNull(row?.valid_votes_extracted ?? row?.sources?.read?.valid_votes) !== null,
      hasEct: numOrNull(row?.sources?.ect?.valid_votes) !== null,
      hasVote62: numOrNull(row?.sources?.vote62?.valid_votes) !== null,
      hasK: numOrNull(row?.sources?.killernay?.valid_votes) !== null
    }))
    .sort((a, b) => a.score - b.score || String(a.row.province).localeCompare(String(b.row.province), 'th'))
    .slice(0, limit);

  els.qualityBody.innerHTML = '';
  rows.forEach(({ row, score, hasRead, hasEct, hasVote62, hasK }) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${row.province || '-'} เขต ${row.district_number || '-'}</td>
      <td>${row.form_type === 'party_list' ? 'บัญชีรายชื่อ' : 'แบ่งเขต'}</td>
      <td>${hasRead ? 'มี' : 'ไม่มี'}</td>
      <td>${hasEct ? 'มี' : 'ไม่มี'}</td>
      <td>${hasVote62 ? 'มี' : 'ไม่มี'}</td>
      <td>${hasK ? 'มี' : 'ไม่มี'}</td>
      <td class="mono">${score}</td>
    `;
    els.qualityBody.append(tr);
  });
  els.qualityCount.textContent = `${rows.length} รายการ`;
}

function renderNewTabs() {
  renderWinnerMismatchTable('ect', els.winnerMismatchEctBody, els.winnerMismatchEctCount, false);
  renderWinnerMismatchTable('vote62', els.winnerMismatchVote62Body, els.winnerMismatchVote62Count, true);
  renderSeatSummary();
  renderCloseRaces();
  renderQualityTable();
}

function applyFilters() {
  const q = (els.search.value || '').trim().toLowerCase();
  const province = els.province.value;
  const form = els.form.value;
  const forcedForm = (state.view === 'all' || state.view === 'missing_read') ? '' : state.view;
  const quality = els.quality.value;

  state.filtered = state.items.filter((r) => {
    if (province && r.province !== province) return false;
    if (forcedForm && r.form_type !== forcedForm) return false;
    if (state.view === 'missing_read' && numOrNull(r?.valid_votes_extracted ?? r?.sources?.read?.valid_votes) !== null) return false;
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
  renderNewTabs();
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

function setupSectionTabs() {
  if (!els.sectionTabs) return;
  const tabs = [...els.sectionTabs.querySelectorAll('[data-section]')];
  const applySection = () => {
    tabs.forEach((btn) => btn.classList.toggle('active', btn.dataset.section === state.section));
    sectionPanes.forEach((pane) => {
      pane.hidden = pane.dataset.sectionPane !== state.section;
    });
  };
  tabs.forEach((btn) => {
    btn.addEventListener('click', () => {
      state.section = btn.dataset.section || 'overview';
      applySection();
    });
  });
  applySection();
}

async function init() {
  const dataVersion = '20260222-k8';
  const [res, pmRes] = await Promise.all([
    fetch(`./data/district_dashboard_data.json?v=${dataVersion}`),
    fetch(`./data/party_map.json?v=${dataVersion}`).catch(() => null)
  ]);
  const data = await res.json();
  if (pmRes && pmRes.ok) {
    const pm = await pmRes.json();
    state.partyMap = pm?.party_map || {};
  }
  state.items = (data.items || []).filter((r) =>
    r &&
    String(r.province || '').trim() &&
    Number(r.district_number || 0) > 0 &&
    (r.form_type === 'constituency' || r.form_type === 'party_list')
  );

  els.generatedAt.textContent = `อัปเดตเมื่อ: ${data.generated_at || '-'} • แหล่งข้อมูล: กระบวนการอ่าน OCR`;
  renderKPIs(data.summary || {});
  renderCoverageTable(state.items);
  renderIrregularityTable(state.items);
  renderProvinceHeatmap(state.items);
  renderSkewTable(state.items);
  await renderSkewMap(state.items);
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
  if (els.seatMode) els.seatMode.addEventListener('change', renderSeatSummary);
  setupTabs();
  setupSectionTabs();
  applyFilters();
}

init().catch((err) => {
  els.generatedAt.textContent = `โหลดข้อมูลไม่สำเร็จ: ${err.message}`;
});
