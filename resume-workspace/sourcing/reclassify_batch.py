# -*- coding: utf-8 -*-
"""Re-run the real pipeline (sweep_lib classifier + evaluate()) over rows from named batches.

Imports sweep_lib (never a private copy of the rules) and scores EVERY non-SKIP row
(GENERIC-B included) per the score-at-birth rule, so this path and the daily path apply
identical walls.

Usage (from project root): python resume-workspace/sourcing/reclassify_batch.py <batch> [<batch>...] [--eu]
"""
import json, os, sys, io
from collections import Counter
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sweep_lib import ROOT, classify, score_rows

args = [a for a in sys.argv[1:] if not a.startswith("--")]
REGION = "EU" if "--eu" in sys.argv else "US"
if not args:
    print("usage: reclassify_batch.py <batch> [<batch>...] [--eu]   (batch names: see sourcing/batches.json)")
    sys.exit(2)
batches = set(args)
pool = json.load(open(os.path.join(ROOT, "sourced-jobs.json"), encoding="utf8"))
rows = [j for j in pool if j.get("batch") in batches and j.get("region", "US") == REGION
        and j.get("call") not in ("APPLIED", "SKIP", "NEEDS-YOU", "VERIFY")]
print("rows to reclassify: %d (batches: %s)" % (len(rows), ", ".join(sorted(batches))))

changed = Counter()
for j in rows:
    d, r = classify(j)
    old = j.get("decision")
    j["decision"] = d
    j["flags"] = [r] + [f for f in j.get("flags", []) if f != r][:2]
    if d != old: changed[(old, d)] += 1
print("decision changes:", dict(changed))

to_score = [j for j in rows if j["decision"] != "SKIP"]
print("score-at-birth: fetching + evaluating %d rows (cached JDs are free)..." % len(to_score))
stats = score_rows(rows)
print("scored: %(scored)d | no-JD: %(no_jd)d | wall-skipped: %(skipped)d" % stats)

json.dump(pool, open(os.path.join(ROOT, "sourced-jobs.json"), "w", encoding="utf8"), indent=1, ensure_ascii=False)
print("\nverdicts on scored rows:", dict(Counter(j.get("verdict", "") for j in to_score)))
print("\nAPPLY verdicts (the real shortlist), by score:")
for j in sorted([j for j in to_score if j.get("verdict") == "APPLY"], key=lambda x: -x.get("score", 0)):
    print("  %2d  %-28s %-55s %s" % (j.get("score", 0), (j.get("company") or "")[:28], (j.get("title") or "")[:55], (j.get("why") or "")[:50]))
print("\nFLAG verdicts (watchlist co with a hard-fail, you decide):")
for j in to_score:
    if j.get("verdict") == "FLAG":
        print("  %-28s %-55s %s" % ((j.get("company") or "")[:28], (j.get("title") or "")[:55], (j.get("why") or "")[:60]))
