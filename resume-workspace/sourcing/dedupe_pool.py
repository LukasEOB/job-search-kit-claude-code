# -*- coding: utf-8 -*-
"""Collapse multi-state reposts: same company + normalized title within a region keeps ONE row
(preferring a row that is applied / carries a call), the rest are removed from the pool.
Run from project root: python resume-workspace/sourcing/dedupe_pool.py"""
import json, re, os, io, sys
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.abspath(__file__))
POOL = os.path.join(ROOT, "sourced-jobs.json")
STATE = os.path.join(ROOT, "board-state.json")

sys.path.insert(0, ROOT)
from sweep_lib import dedupe_key

def key(j):
    return (j.get("region", "US"),) + dedupe_key(j.get("company"), j.get("title"))

# Rows the tracker references (a built resume or an application) always win the collapse and are
# never dropped: keeping the lower jobId would have deleted the row a built resume points to,
# and the board would then render the tracker entry as a second SEND row.
TRACKED = set()
try:
    for _e in json.load(open(os.path.join(os.path.dirname(ROOT), "roles.tracked.json"), encoding="utf8")):
        _m = re.search(r"/jobs/view/(\d+)", str((_e.get("urls") or {}).get("job", "")))
        if _m:
            TRACKED.add(_m.group(1))
except Exception:
    pass

pool = json.load(open(POOL, encoding="utf8"))
try:
    _st = json.load(open(STATE, encoding="utf8"))
    applied = set(_st.get("applied", []))
    WATCH = {str(w) for w in _st.get("watch", [])}
except Exception:
    applied, WATCH = set(), set()
# keeper preference among reposts: live calls outrank SKIP, which outranks no call (a dry run
# showed a SKIP row winning over two TAILOR rows and erasing the live call)
CALL_RANK = {"APPLIED": 0, "NEEDS-YOU": 0, "TAILOR": 1, "MAYBE": 2, "GENERIC": 3, "VERIFY": 4, "SKIP": 5}
groups = defaultdict(list)
for j in pool:
    groups[key(j)].append(j)
drop = set()
for k, rows in groups.items():
    if len(rows) < 2:
        continue
    rows.sort(key=lambda r: (0 if r["jobId"] in applied else 1, 0 if str(r["jobId"]) in TRACKED else 1,
                             0 if (r.get("workplace") or "") != "GONE" else 1,
                             CALL_RANK.get(r.get("call"), 6), 0 if r.get("verdict") else 1, r["jobId"]))
    keep = rows[0]
    keep.setdefault("alsoPostedAs", [])
    for r in rows[1:]:
        if r["jobId"] in applied or str(r["jobId"]) in TRACKED or str(r["jobId"]) in WATCH:
            continue   # never drop an application, a build, or a watched req
        if r.get("call") and r.get("call") != keep.get("call"):
            continue   # conflicting reads of the same role stay visible; dedupe never resolves a disagreement
        keep["alsoPostedAs"].append(r["jobId"])
        drop.add(r["jobId"])
pool = [j for j in pool if j["jobId"] not in drop]
json.dump(pool, open(POOL, "w", encoding="utf8"), indent=1, ensure_ascii=False)
print("dedupe_pool: removed %d repost rows, pool now %d" % (len(drop), len(pool)))
