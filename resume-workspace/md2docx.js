const fs = require('fs');
const path = require('path');
const { Document, Packer, Paragraph, TextRun, HeadingLevel, Table, TableRow, TableCell, WidthType, ShadingType, BorderStyle, AlignmentType } = require('docx');

const TABLE_W = 9360; // 6.5" in DXA

function inlineRuns(text, base = {}) {
  const runs = [];
  // split on **bold** and `code`
  const re = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let last = 0, m;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) runs.push(new TextRun({ text: text.slice(last, m.index), ...base }));
    const tok = m[0];
    if (tok.startsWith('**')) runs.push(new TextRun({ text: tok.slice(2, -2), bold: true, ...base }));
    else runs.push(new TextRun({ text: tok.slice(1, -1), font: 'Consolas', size: 19, ...base }));
    last = m.index + tok.length;
  }
  if (last < text.length) runs.push(new TextRun({ text: text.slice(last), ...base }));
  return runs.length ? runs : [new TextRun({ text: '', ...base })];
}

function cellPara(text, bold) {
  return new Paragraph({ spacing: { before: 40, after: 40 }, children: inlineRuns(text, bold ? { bold: true, size: 19 } : { size: 19 }) });
}

function buildTable(rows) {
  const cols = rows[0].length;
  const colW = Math.floor(TABLE_W / cols);
  const widths = Array(cols).fill(colW);
  widths[cols - 1] = TABLE_W - colW * (cols - 1);
  return new Table({
    columnWidths: widths,
    width: { size: TABLE_W, type: WidthType.DXA },
    rows: rows.map((cells, ri) => new TableRow({
      tableHeader: ri === 0,
      children: cells.map((c, ci) => new TableCell({
        width: { size: widths[ci], type: WidthType.DXA },
        shading: ri === 0 ? { type: ShadingType.CLEAR, fill: 'E8EDF3' } : undefined,
        margins: { top: 60, bottom: 60, left: 100, right: 100 },
        children: [cellPara(c, ri === 0)],
      })),
    })),
  });
}

function convert(mdPath, outPath, title) {
  const lines = fs.readFileSync(mdPath, 'utf8').split(/\r?\n/);
  const children = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const t = line.trim();
    if (!t) { i++; continue; }

    if (/^\|/.test(t) && i + 1 < lines.length && /^\|[\s:|-]+\|$/.test(lines[i + 1].trim())) {
      const rows = [];
      const parse = (l) => l.trim().replace(/^\||\|$/g, '').split('|').map(s => s.trim());
      rows.push(parse(lines[i])); i += 2;
      while (i < lines.length && /^\|/.test(lines[i].trim())) { rows.push(parse(lines[i])); i++; }
      children.push(buildTable(rows));
      children.push(new Paragraph({ spacing: { after: 120 }, children: [] }));
      continue;
    }
    if (/^---+$/.test(t)) {
      children.push(new Paragraph({ spacing: { before: 120, after: 120 }, border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: 'BBBBBB' } }, children: [] }));
      i++; continue;
    }
    const h = t.match(/^(#{1,4})\s+(.*)$/);
    if (h) {
      const lvl = h[1].length;
      children.push(new Paragraph({
        heading: lvl === 1 ? HeadingLevel.HEADING_1 : lvl === 2 ? HeadingLevel.HEADING_2 : HeadingLevel.HEADING_3,
        spacing: { before: lvl === 1 ? 0 : 240, after: 120 },
        children: inlineRuns(h[2]),
      }));
      i++; continue;
    }
    const bullet = t.match(/^[-*]\s+(.*)$/);
    if (bullet) {
      children.push(new Paragraph({ bullet: { level: 0 }, spacing: { after: 60 }, children: inlineRuns(bullet[1]) }));
      i++; continue;
    }
    const num = t.match(/^(\d+)\.\s+(.*)$/);
    if (num) {
      children.push(new Paragraph({ numbering: { reference: 'nums', level: 0 }, spacing: { after: 60 }, children: inlineRuns(num[2]) }));
      i++; continue;
    }
    const quote = t.match(/^>\s?(.*)$/);
    if (quote) {
      children.push(new Paragraph({ indent: { left: 360 }, spacing: { after: 80 }, border: { left: { style: BorderStyle.SINGLE, size: 12, color: '2D6CDF', space: 8 } }, children: inlineRuns(quote[1], { italics: true }) }));
      i++; continue;
    }
    children.push(new Paragraph({ spacing: { after: 120 }, children: inlineRuns(t) }));
    i++;
  }

  const doc = new Document({
    styles: { default: { document: { run: { font: 'Calibri', size: 22 }, paragraph: { spacing: { line: 276 } } } },
      paragraphStyles: [
        { id: 'Heading1', name: 'Heading 1', basedOn: 'Normal', next: 'Normal', quickFormat: true, run: { size: 34, bold: true, color: '1F3864', font: 'Calibri' } },
        { id: 'Heading2', name: 'Heading 2', basedOn: 'Normal', next: 'Normal', quickFormat: true, run: { size: 27, bold: true, color: '2D6CDF', font: 'Calibri' } },
        { id: 'Heading3', name: 'Heading 3', basedOn: 'Normal', next: 'Normal', quickFormat: true, run: { size: 23, bold: true, color: '333333', font: 'Calibri' } },
      ] },
    numbering: { config: [{ reference: 'nums', levels: [{ level: 0, format: 'decimal', text: '%1.', alignment: AlignmentType.START, style: { paragraph: { indent: { left: 460, hanging: 260 } } } }] }] },
    sections: [{ properties: { page: { size: { width: 12240, height: 15840 }, margin: { top: 1080, bottom: 1080, left: 1080, right: 1080 } } }, children }],
  });
  return Packer.toBuffer(doc).then(b => { fs.writeFileSync(outPath, b); console.log('wrote', outPath, b.length, 'bytes'); });
}

const jobs = process.argv.slice(2);
(async () => { for (let k = 0; k < jobs.length; k += 2) await convert(jobs[k], jobs[k + 1]); })();
