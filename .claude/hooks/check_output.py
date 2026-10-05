#!/usr/bin/env python3
"""Blocking quality gate for resume deliverables.
Exit 2 = block the write and tell Claude why. Exit 0 = pass.
Reads Claude Code hook JSON on stdin.

Scope: files under resume-workspace/ (configs, rendered resumes, notes) and any file whose name
says resume, cover, answer or letter. Word limits come from profile.json `gates` when present."""
import sys, json, re, os, zipfile

BANNED = ["hardworking","team player","passionate about","responsible for","detail-oriented",
          "results-driven","self-starter","dynamic","proven track record","synergy",
          "rigorous scale","perfectly aligns","actually trusted","seamlessly",
          "leverage my","I am writing to express","I am excited to apply"]
AI_TELLS = ["having delivered","having run","having built","not just shipping","not just deploying"]
EM = "\u2014"

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()

# What this gate scans. The original filter matched (Resume|Cover|Answer|Letter) anywhere in the
# path, which in a project folder named "Resumes" meant EVERY file, rulebooks included. Scope is
# now deliberate: the resume workspace, plus deliverables named for what they are.
SCOPE_DIR = re.compile(r'(^|[\\/])resume-workspace[\\/]', re.I)
SCOPE_NAME = re.compile(r'(resume|cover|answer|letter)', re.I)
# Rulebook exemption (2026-09-01): the process docs QUOTE the banned phrases and use em-dashes as
# documentation punctuation; they can never pass a scan of their own ban list. Same for the kit's
# docs/ folder and CLAUDE.md.
RULEBOOKS = {"resume_process.md", "career_bank.md", "sourcing_process.md", "board_spec.md",
             "claude.md"}
TRACKER = os.path.join("resume-workspace", "roles.tracked.json")


def gate_settings():
    """profile.json `gates` over the built-in defaults. Missing profile = defaults."""
    for root in (os.path.dirname(os.path.dirname(HERE)), ROOT):
        ws = os.path.join(root, "resume-workspace")
        if os.path.exists(os.path.join(ws, "profile_lib.py")):
            sys.path.insert(0, ws)
            import profile_lib
            profile, _ = profile_lib.load_profile_optional(ROOT)
            return profile_lib.gates(profile)
    return {"summaryWords": {"targetMin": 50, "targetMax": 70, "hardMax": 75},
            "coverLetterMaxWords": 220, "answerMaxWords": 110}


def docx_text(p):
    x = zipfile.ZipFile(p).read('word/document.xml').decode('utf8')
    return re.sub(r'<[^>]+>','', x.replace('</w:p>','\n'))

def check(path, G=None):
    G = G or gate_settings()
    SW = G["summaryWords"]
    errs, warns = [], []
    if not os.path.exists(path): return errs, warns
    ext = os.path.splitext(path)[1].lower()
    if ext == '.docx':
        text = docx_text(path)
        lines = [l for l in text.split('\n') if l.strip()]
        # em-dash outside "Company <em-dash> Title" headers
        for l in lines:
            if EM in l and not re.match(r'^[A-Z][A-Za-z0-9 .,()&/-]+ \u2014 ', l.replace(chr(9),' ')):
                errs.append(f"EM-DASH in body text: {l[:80]}")
        if '\\$' in text or '\\\\' in text:
            errs.append("ESCAPE ARTIFACT (\\$ or \\\\) rendered into the document")
        # summary length
        try:
            i = [n for n,l in enumerate(lines) if l.strip().upper()=='SUMMARY'][0]
            w = len(lines[i+1].split())
            if w > SW["hardMax"]:
                errs.append(f"SUMMARY IS {w} WORDS. Limit is {SW['targetMin']}-{SW['targetMax']}. Cut it.")
            elif w < 40: warns.append(f"summary only {w} words")
        except Exception: pass
    elif ext in ('.md','.txt'):
        text = open(path, encoding='utf8').read()
        body = "\n".join(l for l in text.split('\n') if not l.startswith('#') and not l.startswith('*('))
        if EM in body:
            for l in body.split('\n'):
                if EM in l: errs.append(f"EM-DASH: {l.strip()[:80]}")
        # cover letter / answer length per section
        cover_max, answer_max = int(G["coverLetterMaxWords"]), int(G["answerMaxWords"])
        for sec in re.split(r'\n## ', text)[1:]:
            name = sec.split('\n')[0].strip()
            prose = "\n".join(l for l in sec.split('\n')[1:]
                              if l.strip() and not l.startswith(('-','#','*','|','`')))
            w = len(prose.split())
            if 'cover' in path.lower() and w > cover_max:
                errs.append(f"COVER LETTER '{name}' IS {w} WORDS. Limit is 150-200 (hard fail above {cover_max}).")
            if 'answer' in path.lower() and w > answer_max:
                errs.append(f"ANSWER '{name}' IS {w} WORDS. 3-4 sentences max (~90, hard fail above {answer_max}).")
    else:
        return errs, warns
    low = text.lower()
    # Compare lowercase to lowercase: two banned phrases start with a capital "I" and could
    # never match the lowercased text before this fix.
    for b in BANNED:
        if b.lower() in low: errs.append(f"BANNED PHRASE: '{b}'")
    for a in AI_TELLS:
        if a in low: errs.append(f"AI TELL: '{a}'")
    return errs, warns

def frozen_targets():
    """Read the tracker and return what must not be touched.

    Freezes by EXACT OUTPUT FILENAME where the tracker records one, and only falls back to
    company-name matching for applied roles with no recorded file. Company-level matching alone
    was too coarse: two roles at one employer (one submitted, one still open) share a company
    name, so freezing by company would have locked the live application too.
    Returns (filenames, companies, problem). No tracker yet = nothing frozen. A tracker that
    exists but cannot be read returns a problem string, and the caller blocks: a bad JSON edit
    must never silently unlock a submitted role."""
    p = os.path.join(ROOT, TRACKER)
    if not os.path.exists(p):
        return set(), set(), None
    try:
        rows = json.load(open(p, encoding="utf8"))
        applied = [r for r in rows
                   if (r.get("application") or {}).get("status") in ("applied", "submitted")]
        files = {os.path.basename((r.get("output") or {}).get("resume", "")).lower()
                 for r in applied if (r.get("output") or {}).get("resume")}
        cos = {r["company"] for r in applied if not (r.get("output") or {}).get("resume")}
        return {f for f in files if f}, cos, None
    except Exception as e:
        return set(), set(), "%s exists but cannot be read (%s)" % (TRACKER, e)

def in_scope(p):
    return bool(SCOPE_DIR.search(p) or SCOPE_NAME.search(os.path.basename(p)))

def exempt(p):
    base = os.path.basename(p).lower()
    if base in RULEBOOKS:
        return True
    try:
        rel = os.path.relpath(os.path.abspath(p), os.path.abspath(ROOT)) if os.path.isabs(p) else p
    except ValueError:  # different drive on Windows
        rel = p
    if re.match(r'docs[\\/]', rel, re.I):
        return True
    # JD evidence exemption (2026-09-04): files under sourcing/jds/ are verbatim job postings
    # saved as evidence. The de-echo gate depends on them keeping the JD's own words, banned
    # phrases included ("dynamic", "proven track record"); scanning them against our own ban
    # list either blocks the save or pressures an edit that corrupts the evidence.
    if re.search(r'sourcing[\\/]+jds[\\/]', p):
        return True
    # Harvest evidence exemption (2026-09-08): sourcing/*harvest*.txt are raw job-board harvest
    # rows (id|title|company|location|easyApply). The titles are the employer's own text and
    # legitimately contain em-dashes (one employer posted the same em-dash title across ~10 metro
    # reposts). Same reasoning as jds/ above: this is evidence, not our prose. Editing the
    # em-dash out would corrupt the title, break company+title dedupe in ingest_harvest.py, and
    # break matching against the live posting. They reach this gate because they live under
    # resume-workspace/.
    if re.search(r'sourcing[\\/]+[^\\/]*harvest[^\\/]*\.txt$', p, re.I):
        return True
    return False

def main():
    try: data = json.load(sys.stdin)
    except Exception: sys.exit(0)
    p = (data.get("tool_input") or {}).get("file_path", "")
    if not p or not in_scope(p) or exempt(p): sys.exit(0)
    base = os.path.basename(p).lower()
    files, companies, problem = frozen_targets()
    if problem:
        # The tracker itself stays editable, so the fix is always possible.
        if os.path.normcase(os.path.abspath(p)) == os.path.normcase(os.path.abspath(os.path.join(ROOT, TRACKER))):
            sys.exit(0)
        print(f"BLOCKED: {problem}. Until it parses, this gate cannot tell which applications "
              f"were already sent, so resume writes are held rather than silently unlocked. "
              f"Fix the tracker JSON first.", file=sys.stderr)
        sys.exit(2)
    stem = os.path.splitext(base)[0]
    for f in files:
        if stem == os.path.splitext(f)[0]:
            print(f"BLOCKED: {os.path.basename(p)} was already submitted. Do not edit or re-render "
                  f"a sent application. See resume-workspace/roles.tracked.json.", file=sys.stderr)
            sys.exit(2)
    # Compare letters and digits only: "Adventure Works" must also freeze adventure-works-*.json
    # and Alex_Example_AdventureWorks_*.docx (a plain substring test never matched a
    # multi-word company name against a hyphenated or CamelCase file name).
    squash = lambda s: re.sub(r'[^a-z0-9]', '', s.lower())
    for co in companies:
        if squash(co) and squash(co) in squash(base):
            print(f"BLOCKED: {co} was already applied to and the tracker records no specific file, "
                  f"so every {co} file is frozen. See resume-workspace/roles.tracked.json.",
                  file=sys.stderr)
            sys.exit(2)
    try:
        errs, warns = check(p)
    except Exception as e:
        print(f"QUALITY GATE could not run on {os.path.basename(p)} ({e}). If profile.json is "
              f"broken, fix it first.", file=sys.stderr)
        sys.exit(2)
    if errs:
        print("QUALITY GATE FAILED for " + os.path.basename(p) + ":\n" +
              "\n".join(" - " + e for e in errs) +
              "\nFix these before continuing. See Resume_Process.md.", file=sys.stderr)
        sys.exit(2)
    if warns: print("warnings: " + "; ".join(warns))
    sys.exit(0)

if __name__ == "__main__":
    main()
