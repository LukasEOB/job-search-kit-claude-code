# Resume format spec

Resume conventions differ by field, level and country: a US engineering manager, a German UX designer and a UK nurse are judged on different page counts, sections and headers. So the kit does not hand you a format. Claude researches current best practice for YOUR target and writes the decisions into this file. Every build then follows it (`Resume_Process.md`, Step 6).

## How to fill this in

Ask Claude:

> *"Research current resume best practices for [your role] at [your level] in [your target countries], applying to [company types]. Use recent sources from recruiters and hiring managers in that field, not generic career blogs. Then fill in docs/Resume_Format.md: each decision, the choice, and one line of reasoning with the source. Flag anything where sources disagree and ask me."*

Check the result against two or three real resumes from people who landed the kind of job you want (ask your network). Then lock it: from that point on, change it only on purpose.

## Decisions to make

| Decision | Your choice | Why (source) |
|---|---|---|
| Page count (1 or 2) | | |
| Section order | | |
| Section headers (use standard words ATS parsers know: SUMMARY, EXPERIENCE, SKILLS, EDUCATION, CERTIFICATIONS) | | |
| Header: name, contact lines, LinkedIn URL | | |
| Location in the header (city, country, or nothing) | | |
| Photo, date of birth, nationality (usual in some countries, a risk in others such as the US and UK) | | |
| Work authorization line | | |
| Headline under the name (title plus focus) | | |
| Summary (yes or no, length) | | |
| Bullets per role (ceilings) | | |
| Skills section shape | | |
| Portfolio, publications or project links (common for design, research, engineering) | | |
| Date format | | |
| Spelling standard (US or UK English) | | |
| File type sent (.docx or PDF) and file naming | | |
| Font and size | | |

## ATS rules that hold everywhere

- Single column, no tables, text boxes, headers or footers holding content, icons or graphics.
- Standard fonts.
- Standard section headers.
- Keywords appear in context inside bullets, not as a stuffed list.
- Check the page count on the rendered file; never assume it.

## The renderer

`resume-workspace/render_our_template.js` produces a plain, ATS-safe, single-column .docx: name, contact line, summary, experience, skills, education. If your spec needs something different (another section, a different font, a portfolio line), ask Claude to change the renderer to match this spec, then run `python resume-workspace/smoke_test.py` to prove the gates still pass.
