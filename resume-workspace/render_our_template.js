// Renders a resume-builder config JSON through the kit's docx-js template (SKILLS header, ATS-safe).
// Usage: node render_our_template.js <config.json> <output.docx> [headline override]
// Headline: the optional argument, else the config's "headline". Certifications: the config's "certifications" list.
const fs = require('fs');
const { Document, Packer, Paragraph, TextRun, AlignmentType, LevelFormat, TabStopType, BorderStyle, ExternalHyperlink } = require('docx');
const [,, cfgPath, outPath, headline] = process.argv;
const cfg = JSON.parse(fs.readFileSync(cfgPath, 'utf8'));
const txt = (s, o = {}) => new TextRun({ text: s, size: 22, font: "Calibri", ...o });
const bullet = (s) => new Paragraph({ numbering: { reference: "bullets", level: 0 }, spacing: { after: 60 }, children: [(() => { const m = s.match(/^([^:]{10,90}?(?:\d[^ ]*)?(?: [-–] |: ))(.*)$/); return txt(s); })()] });
const sectionHeading = (s) => new Paragraph({ spacing: { before: 160, after: 60 }, border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: "888888", space: 2 } }, children: [txt(s, { bold: true, size: 24 })] });
const roleHeader = (company, title, dates) => [
  new Paragraph({ keepNext: true, spacing: { before: 100, after: 30 }, tabStops: [{ type: TabStopType.RIGHT, position: 10080 }], children: [ txt(company, { bold: true }), txt(" — "), txt(title, { italics: true }), txt("	" + dates, { bold: true }) ] })
];
const subline = (s) => new Paragraph({ keepNext: true, spacing: { after: 40 }, children: [txt(s, { italics: true, size: 20 })] });

const children = [
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 30 }, children: [txt(cfg.candidate.name.toUpperCase(), { bold: true, size: 36 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 30 }, children: [txt(headline || cfg.headline || "")] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 100 }, children:
    cfg.candidate.contact.flatMap((c, i) => {
      const runs = [];
      if (i > 0) runs.push(txt("  |  ", { size: 20 }));
      runs.push(c.link ? new ExternalHyperlink({ children: [txt(c.text, { size: 20, underline: {} })], link: c.link }) : txt(c.text, { size: 20 }));
      return runs;
    }) }),
  sectionHeading("SUMMARY"),
  new Paragraph({ spacing: { after: 80 }, children: [txt(cfg.summary.text)] }),
  sectionHeading("PROFESSIONAL EXPERIENCE"),
];
for (const sec of cfg.experienceSections) {
  for (const job of sec.jobs) {
    children.push(...roleHeader(job.company, job.title, job.dates));
    if (job.subHeader) children.push(subline(job.subHeader));
    for (const b of job.bullets) children.push(bullet(b));
  }
}
children.push(sectionHeading("SKILLS"));
for (const [cat, detail] of cfg.skills) {
  children.push(new Paragraph({ spacing: { after: 40 }, children: [txt(cat + ": ", { bold: true }), txt(detail)] }));
}
// Certifications come from the config's "certifications" list; each must also be in Career_Bank.md.
if ((cfg.certifications || []).length) {
  children.push(sectionHeading("CERTIFICATIONS"));
  for (const c of cfg.certifications) {
    children.push(new Paragraph({ numbering: { reference: "bullets", level: 0 }, spacing: { after: 60 }, children: [txt(c)] }));
  }
}
children.push(sectionHeading("EDUCATION"));
for (const e of cfg.education) {
  children.push(new Paragraph({ spacing: { after: 30 }, tabStops: [{ type: TabStopType.RIGHT, position: 10080 }], children: [ txt(e.institution, { bold: true }), txt(" — " + e.degree), txt("\t" + e.dates, { bold: true }) ] }));
}
const doc = new Document({
  styles: { default: { document: { run: { font: "Calibri", size: 22 } } } },
  numbering: { config: [{ reference: "bullets", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 360, hanging: 220 } } } }] }] },
  sections: [{ properties: { page: { size: { width: 12240, height: 15840 }, margin: { top: 720, right: 1080, bottom: 720, left: 1080 } } }, children }],
});
Packer.toBuffer(doc).then(buf => { fs.writeFileSync(outPath, buf); console.log("RENDERED", outPath); });
