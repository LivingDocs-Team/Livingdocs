// LD-183 Documentation diff & comparison, browser side.
// The same rows as the AI service's /compare (ai-service/app/doc_diff.py), for texts that only
// exist in the page (the editor and the versions kept in this session):
//   unchanged | added | removed | modified (with the changed words marked)

const MODIFIED_SIMILARITY = 0.5;
const MAX_CELLS = 4_000_000; // above this the middle block is not aligned line by line
const TOKEN = /\s+|[\p{L}\p{N}_]+|[^\p{L}\p{N}_\s]/gu;
const HEADING = /^(#{1,2})\s+(.+?)\s*#*\s*$/;
export const NO_SECTION = '(top of document)';

function lines(text) {
  if (!text) return [];
  return text.replace(/\r\n?/g, '\n').replace(/\n$/, '').split('\n');
}

// Longest common subsequence of two arrays: list of [i, j] index pairs, in order.
function lcsPairs(a, b, equal = (x, y) => x === y) {
  const n = a.length;
  const m = b.length;
  if (!n || !m || n * m > MAX_CELLS) return [];
  const table = Array.from({ length: n + 1 }, () => new Uint32Array(m + 1));
  for (let i = n - 1; i >= 0; i -= 1) {
    for (let j = m - 1; j >= 0; j -= 1) {
      table[i][j] = equal(a[i], b[j])
        ? table[i + 1][j + 1] + 1
        : Math.max(table[i + 1][j], table[i][j + 1]);
    }
  }
  const pairs = [];
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (equal(a[i], b[j])) {
      pairs.push([i, j]);
      i += 1;
      j += 1;
    } else if (table[i + 1][j] >= table[i][j + 1]) {
      i += 1;
    } else {
      j += 1;
    }
  }
  return pairs;
}

function tokens(text) {
  return text.match(TOKEN) || [];
}

function similarity(oldLine, newLine) {
  if (!oldLine.trim() || !newLine.trim()) return 0;
  const a = tokens(oldLine);
  const b = tokens(newLine);
  const matched = lcsPairs(a, b).reduce((sum, [i]) => sum + a[i].length, 0);
  return (2 * matched) / (oldLine.length + newLine.length);
}

function pushSegment(parts, text, changed) {
  if (!text) return;
  const last = parts[parts.length - 1];
  if (last && last.changed === changed) last.text += text;
  else parts.push({ text, changed });
}

// Word-level difference of two lines (LD-187): which parts of each side changed.
export function inlineSegments(oldLine, newLine) {
  const a = tokens(oldLine);
  const b = tokens(newLine);
  const pairs = lcsPairs(a, b);
  const oldParts = [];
  const newParts = [];
  let i = 0;
  let j = 0;
  for (const [pi, pj] of [...pairs, [a.length, b.length]]) {
    pushSegment(oldParts, a.slice(i, pi).join(''), true);
    pushSegment(newParts, b.slice(j, pj).join(''), true);
    if (pi < a.length) {
      pushSegment(oldParts, a[pi], false);
      pushSegment(newParts, b[pj], false);
    }
    i = pi + 1;
    j = pj + 1;
  }
  return [oldParts, newParts];
}

function replaceRows(oldLines, newLines, i0, j0) {
  const rows = [];
  let i = 0;
  let j = 0;
  const similar = (x, y) => similarity(x, y) >= MODIFIED_SIMILARITY;
  while (i < oldLines.length || j < newLines.length) {
    if (i < oldLines.length && j < newLines.length && similar(oldLines[i], newLines[j])) {
      const [oldSegments, newSegments] = inlineSegments(oldLines[i], newLines[j]);
      rows.push({
        kind: 'modified', old_number: i0 + i + 1, new_number: j0 + j + 1,
        old_text: oldLines[i], new_text: newLines[j], old_segments: oldSegments, new_segments: newSegments,
      });
      i += 1;
      j += 1;
    } else if (i < oldLines.length
      && (j >= newLines.length || !newLines.slice(j, j + 3).some((line) => similar(oldLines[i], line)))) {
      rows.push({ kind: 'removed', old_number: i0 + i + 1, new_number: null, old_text: oldLines[i], new_text: null });
      i += 1;
    } else {
      rows.push({ kind: 'added', old_number: null, new_number: j0 + j + 1, old_text: null, new_text: newLines[j] });
      j += 1;
    }
  }
  return rows;
}

function heading(line) {
  const match = HEADING.exec(line || '');
  return match ? match[2].trim() : null;
}

function withSections(rows) {
  let oldSection = NO_SECTION;
  let newSection = NO_SECTION;
  for (const row of rows) {
    if (row.old_text !== null) oldSection = heading(row.old_text) || oldSection;
    if (row.new_text !== null) newSection = heading(row.new_text) || newSection;
    row.section = row.kind === 'removed' ? oldSection : newSection;
  }
  const oldHeads = new Set(rows.filter((r) => r.old_text !== null).map((r) => heading(r.old_text)).filter(Boolean));
  const newHeads = new Set(rows.filter((r) => r.new_text !== null).map((r) => heading(r.new_text)).filter(Boolean));
  const sections = new Map();
  for (const row of rows) {
    if (!sections.has(row.section)) {
      sections.set(row.section, { section: row.section, status: 'unchanged', added: 0, removed: 0, modified: 0 });
    }
    const section = sections.get(row.section);
    if (row.kind !== 'unchanged') section[row.kind] += 1;
  }
  for (const section of sections.values()) {
    const named = section.section !== NO_SECTION;
    if (named && newHeads.has(section.section) && !oldHeads.has(section.section)) section.status = 'added';
    else if (named && oldHeads.has(section.section) && !newHeads.has(section.section)) section.status = 'removed';
    else if (section.added || section.removed || section.modified) section.status = 'modified';
  }
  return [...sections.values()];
}

// Side-by-side difference of two texts (older first), shaped like the AI service's comparison.
export function diffTexts(oldText, newText) {
  const a = lines(oldText);
  const b = lines(newText);
  let start = 0;
  while (start < a.length && start < b.length && a[start] === b[start]) start += 1;
  let endA = a.length;
  let endB = b.length;
  while (endA > start && endB > start && a[endA - 1] === b[endB - 1]) {
    endA -= 1;
    endB -= 1;
  }
  const middle = lcsPairs(a.slice(start, endA), b.slice(start, endB))
    .map(([i, j]) => [i + start, j + start]);
  const anchors = [
    ...Array.from({ length: start }, (_, k) => [k, k]),
    ...middle,
    ...Array.from({ length: a.length - endA }, (_, k) => [endA + k, endB + k]),
  ];

  const rows = [];
  let i = 0;
  let j = 0;
  for (const [ai, bj] of [...anchors, [a.length, b.length]]) {
    if (ai > i || bj > j) rows.push(...replaceRows(a.slice(i, ai), b.slice(j, bj), i, j));
    if (ai < a.length) {
      rows.push({ kind: 'unchanged', old_number: ai + 1, new_number: bj + 1, old_text: a[ai], new_text: b[bj] });
    }
    i = ai + 1;
    j = bj + 1;
  }
  const stats = { added: 0, removed: 0, modified: 0, unchanged: 0 };
  rows.forEach((row) => { stats[row.kind] += 1; });
  return {
    identical: a.length === b.length && a.every((line, k) => line === b[k]),
    stats,
    sections: withSections(rows),
    rows,
  };
}
