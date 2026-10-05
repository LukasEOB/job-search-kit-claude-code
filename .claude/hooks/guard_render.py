#!/usr/bin/env python3
"""Blocks a render that would overwrite a .docx you edited by hand.
Compares the on-disk document text against the config it would be rendered from."""
import sys, json, re, os, zipfile, glob


def block_if_commented(out_path):
    """Never render over a .docx that carries review comments until a copy is archived.
    Claude rendered over commented files repeatedly on 2026-08-04; the comments survived by luck,
    not by process. This makes losing them impossible."""
    if not os.path.exists(out_path):
        return
    try:
        if "word/comments.xml" not in zipfile.ZipFile(out_path).namelist():
            return
    except Exception:
        return
    base = os.path.splitext(os.path.basename(out_path))[0]
    root = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    if glob.glob(os.path.join(root, "_archive", base + "*COMMENT*")):
        return
    print("BLOCKED: %s contains review comments and no archived copy exists. "
          "Copy it to _archive/%s_COMMENTS-<date>.docx first, then render."
          % (os.path.basename(out_path), base), file=sys.stderr)
    sys.exit(2)

def docx_text(p):
    x = zipfile.ZipFile(p).read('word/document.xml').decode('utf8')
    t = re.sub(r'<[^>]+>','', x.replace('</w:p>','\n'))
    return [l.strip() for l in t.split('\n') if l.strip()]

def main():
    try: data = json.load(sys.stdin)
    except Exception: sys.exit(0)
    cmd = (data.get("tool_input") or {}).get("command","")
    if "render_our_template" not in cmd: sys.exit(0)
    m = re.findall(r'(\S+\.json)\s+(\S+\.docx)', cmd)
    if not m: sys.exit(0)
    cfg_p, out_p = m[0]
    cfg_p, out_p = cfg_p.strip('"\''), out_p.strip('"\'')
    # CWD FIX 2026-09-09 (same defect as verify_render): renders run from resume-workspace,
    # so workspace-relative paths never resolved from the hook's own cwd and the overwrite
    # guard silently skipped. Resolve against project root and resume-workspace/ too.
    def _resolve(p):
        root = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
        for cand in (p, os.path.join(root, p), os.path.join(root, "resume-workspace", p)):
            if os.path.exists(cand):
                return cand
        return None
    out_r = _resolve(out_p)
    if out_r is None: sys.exit(0)   # no existing docx = nothing to protect
    out_p = out_r
    block_if_commented(out_p)
    cfg_r = _resolve(cfg_p)
    if cfg_r is None:
        print("RENDER BLOCKED: %s exists on disk but the guard cannot find config %r to "
              "compare against (tried project root and resume-workspace/). Refusing to let "
              "an unverifiable render overwrite it." % (os.path.basename(out_p), cfg_p),
              file=sys.stderr)
        sys.exit(2)
    cfg_p = cfg_r
    try:
        cfg = json.load(open(cfg_p, encoding="utf8"))
        disk = docx_text(out_p)
        want = [cfg["summary"]["text"]]
        for j in cfg["experienceSections"][0]["jobs"]: want += j["bullets"]
        want_set = {re.sub(r'\s+',' ',w).strip() for w in want}
        # Lines with an em-dash are role headers ("Company <em-dash> Title"), not prose.
        orphans = [d for d in disk if len(d) > 60 and '\u2014' not in d
                   and re.sub(r'\s+',' ',d).strip() not in want_set]
        if orphans:
            print("RENDER BLOCKED: " + os.path.basename(out_p) +
                  " contains text not in the config. It was likely edited by hand.\n" +
                  "\n".join("  ON DISK: " + o[:100] for o in orphans[:3]) +
                  "\nSync those edits into the config first, or render to a new filename.",
                  file=sys.stderr)
            sys.exit(2)
    except Exception: sys.exit(0)
    sys.exit(0)

# NOTE (found while building the kit, 2026-10-05): main() is deliberately NOT called, matching
# the original project, where this hook never ran because the call was missing. Calling it as
# written would block EVERY re-render: the headline, contact line and skills rows are never in
# `want`, and a bullet changed in the config since the last render looks like a hand edit. A
# working guard needs a fingerprint of the last rendered text to compare against. The
# comment-archive check (block_if_commented) has no such problem and is the part that is safe
# to enable first.
