#!/usr/bin/env python3
"""Regression gate (PIPELINE_SPEC.md, owner mandate): after any Edit/Write to a
pipeline file (resume-workspace/sourcing/*.py or *.js), run pipeline_selftest.py. A failure
BLOCKS with the feature name, so adding one feature can no longer silently break another."""
import sys, json, re, os, subprocess

try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)
p = (data.get("tool_input") or {}).get("file_path", "")
if not re.search(r"sourcing[\\/][^\\/]+\.(py|js)$", p or ""):
    sys.exit(0)
proj = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
st = os.path.join(proj, "resume-workspace", "sourcing", "pipeline_selftest.py")
if not os.path.exists(st):
    print("selftest_gate: pipeline_selftest.py MISSING - the regression harness itself was "
          "deleted. Restore it (PIPELINE_SPEC.md).", file=sys.stderr)
    sys.exit(2)
r = subprocess.run([sys.executable, st], capture_output=True, text=True, timeout=120)
if r.returncode != 0:
    print((r.stdout or "")[-1500:], file=sys.stderr)
    print("PIPELINE SELFTEST FAILED after editing %s: a registered feature broke. "
          "Fix it before proceeding. See resume-workspace/sourcing/PIPELINE_SPEC.md."
          % os.path.basename(p), file=sys.stderr)
    sys.exit(2)
sys.exit(0)
