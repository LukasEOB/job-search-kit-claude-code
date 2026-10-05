# -*- coding: utf-8 -*-
"""Backfill so ZERO live rows are unscored (run whenever invariant G reports unscored rows).

Scores every live row with no verdict (decision != SKIP, call not APPLIED/SKIP, workplace
not GONE, not applied/tossed in board-state) using sweep_lib.fetch_jd + evaluate, then
stamps lanes on every live row still missing one. Run repeatedly until it prints
"remaining: 0". Timed wall-clock cap per run; checkpoints every 50 rows.

Usage (repo root): python resume-workspace/sourcing/backfill_score.py [max_seconds]
"""
import json, os, sys, io, time
from collections import Counter
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sweep_lib import ROOT, fetch_jd, evaluate, stamp_lane, comp_from_jd, WATCHLIST

CAP = int(sys.argv[1]) if len(sys.argv) > 1 else 480
POOL = os.path.join(ROOT, "sourced-jobs.json")
pool = json.load(open(POOL, encoding="utf8"))
st = json.load(open(os.path.join(ROOT, "board-state.json"), encoding="utf8"))
applied, tossed = set(st.get("applied", [])), set(st.get("tossed", []))

def live(j):
    return (str(j["jobId"]) not in applied and str(j["jobId"]) not in tossed
            and j.get("decision") != "SKIP" and j.get("call") not in ("APPLIED", "SKIP")
            and (j.get("workplace") or "") != "GONE")

todo = [j for j in pool if live(j) and not j.get("verdict")]
print("unscored live rows: %d (cap %ds this run)" % (len(todo), CAP))
t0, done, nojd = time.time(), 0, 0
for j in todo:
    if time.time() - t0 > CAP:
        print("wall-clock cap reached")
        break
    txt = fetch_jd(str(j["jobId"]))
    if not txt:
        j["verdict"], j["why"] = "NO-JD", ""
        nojd += 1
    else:
        v, why, sc = evaluate(txt, watch=any(w in (j.get("company") or "").lower() for w in WATCHLIST))
        j["verdict"], j["why"], j["score"] = v, why, sc
        done += 1
    stamp_lane(j)
    if (done + nojd) % 50 == 0:
        json.dump(pool, open(POOL, "w", encoding="utf8"), indent=1, ensure_ascii=False)

# lane backfill for every live row still laneless (kills the 294-row drift class)
lanes = 0
for j in pool:
    if live(j) and j.get("verdict") != "PASS" and not j.get("lane"):
        if stamp_lane(j):
            lanes += 1

# comp backfill from JDs already ON DISK (bands sit in JD text while
# LinkedIn's field is empty; board P-tags read the field, so P1 rows rendered as P3).
# Disk-only on purpose: no network, no re-fetch; new rows get comp at birth in score_rows.
comps = 0
for j in pool:
    if live(j) and not j.get("comp"):
        p = os.path.join(ROOT, "jds", "%s.txt" % j["jobId"])
        if os.path.exists(p):
            band = comp_from_jd(open(p, encoding="utf8", errors="replace").read())
            if band:
                j["comp"] = band
                comps += 1
print("comp bands mined from on-disk JDs: %d" % comps)

json.dump(pool, open(POOL, "w", encoding="utf8"), indent=1, ensure_ascii=False)
remaining = sum(1 for j in pool if live(j) and not j.get("verdict"))
print("scored this run: %d | no-JD: %d | lanes backfilled: %d" % (done, nojd, lanes))
print("verdicts among newly scored:", dict(Counter(j.get("verdict") for j in todo if j.get("verdict"))))
print("MEASURED remaining unscored live rows: %d" % remaining)
