#!/usr/bin/env python3
"""Smoke test for the resume toolchain. Run from the repo root:

    python resume-workspace/smoke_test.py                    # uses your profile.json if present
    python resume-workspace/smoke_test.py --example-profile  # pins profile.resume.example.json

1. runs the render gate (.claude/hooks/verify_render.py) on the example config,
2. renders it with node into resume-workspace/example-output/Alex_Example_Tailored.docx,
3. runs the output checks (.claude/hooks/check_output.py) on the rendered file,
4. prints SMOKE TEST: PASS, or SMOKE TEST: FAIL with the reasons.

Node is called directly here, not through Claude's Bash tool, so the render hooks do not fire
twice; step 1 is the same gate those hooks run. Needs `npm install` in resume-workspace/ once."""
import json, os, subprocess, sys, zipfile, re

WS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(WS)
CFG = os.path.join(WS, "resume-configs", "example-tailored.json")
OUT_DIR = os.path.join(WS, "example-output")
OUT = os.path.join(OUT_DIR, "Alex_Example_Tailored.docx")
GATE = os.path.join(ROOT, ".claude", "hooks", "verify_render.py")
CHECK = os.path.join(ROOT, ".claude", "hooks", "check_output.py")
RENDER = os.path.join(WS, "render_our_template.js")


def run(cmd, env, stdin=None):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", env=env, cwd=ROOT,
                       input=stdin)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def main():
    env = dict(os.environ, CLAUDE_PROJECT_DIR=ROOT, PYTHONIOENCODING="utf-8")
    if "--example-profile" in sys.argv:
        env["JOB_KIT_PROFILE"] = os.path.join(ROOT, "profile.resume.example.json")
    fails = []

    sys.path.insert(0, WS)
    import profile_lib
    try:
        prof, path = profile_lib.load_profile_optional(ROOT) if "JOB_KIT_PROFILE" not in env else (
            json.load(open(env["JOB_KIT_PROFILE"], encoding="utf8")), env["JOB_KIT_PROFILE"])
    except Exception as e:
        prof, path = None, "UNREADABLE (%s)" % e
    print("profile: %s" % (path or "none found, built-in gate defaults"))
    if prof and (prof.get("summaryLock") or {}).get("enabled"):
        print("note: your profile enables summaryLock. The example config was not written to your "
              "lock, so a lock failure below is expected. Use --example-profile to test the "
              "toolchain alone.")

    print("\n[1/3] render gate on %s" % os.path.relpath(CFG, ROOT))
    code, out = run([sys.executable, GATE, CFG], env)
    print(out.rstrip())
    if code != 0:
        fails.append("render gate blocked the example config (exit %d)" % code)

    if not fails:
        print("\n[2/3] render with node")
        if not os.path.exists(os.path.join(WS, "node_modules", "docx")):
            fails.append("node_modules/docx missing: run `npm install` in resume-workspace/")
        else:
            os.makedirs(OUT_DIR, exist_ok=True)
            headline = json.load(open(CFG, encoding="utf8")).get("headline", "")
            code, out = run(["node", RENDER, CFG, OUT, headline], env)
            print(out.rstrip())
            if code != 0 or not os.path.exists(OUT):
                fails.append("render failed (exit %d)" % code)

    if not fails:
        print("\n[3/3] output checks on %s" % os.path.relpath(OUT, ROOT))
        code, out = run([sys.executable, CHECK], env,
                        stdin=json.dumps({"tool_input": {"file_path": OUT}}))
        print(out.rstrip() or "  clean")
        if code != 0:
            fails.append("output checks failed on the rendered docx (exit %d)" % code)
        # The page must carry what the config says, not just exist.
        xml = zipfile.ZipFile(OUT).read("word/document.xml").decode("utf8")
        text = re.sub(r"<[^>]+>", "", xml).replace("&amp;", "&")
        cfg = json.load(open(CFG, encoding="utf8"))
        want = [cfg["candidate"]["name"].upper(), cfg["summary"]["text"]] + \
               [b for s in cfg["experienceSections"] for j in s["jobs"] for b in j["bullets"]]
        missing = [w[:60] for w in want if w not in text]
        if missing:
            fails.append("rendered docx is missing config text: %s" % "; ".join(missing[:3]))

    print()
    if fails:
        print("SMOKE TEST: FAIL")
        for f in fails:
            print("  - " + f)
        sys.exit(1)
    print("SMOKE TEST: PASS")


if __name__ == "__main__":
    main()
