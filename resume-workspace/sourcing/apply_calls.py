# -*- coding: utf-8 -*-
"""apply_calls.py: the ONE sanctioned writer for reader judgments.

Reads a reader-calls JSON file (the established schema the reader pass already writes:
[{jobId, company, title, call, why, quote?, lane?}, ...]) and stamps call/callWhy/lane
onto EXISTING pool rows only. Never creates rows. Idempotent: re-applying the same file
changes nothing. Refuses calls outside the closed vocabulary.

Usage (repo root): python resume-workspace/sourcing/apply_calls.py <reader-calls-file.json>
"""
import json, os, sys, io
from collections import Counter
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sweep_lib import ROOT, stamp_lane

VOCAB = {"TAILOR", "MAYBE", "GENERIC", "SKIP", "NEEDS-YOU", "VERIFY"}

if len(sys.argv) < 2:
    print("usage: apply_calls.py <reader-calls-file.json>"); sys.exit(2)
calls = json.load(open(sys.argv[1], encoding="utf8"))
POOL = os.path.join(ROOT, "sourced-jobs.json")
pool = json.load(open(POOL, encoding="utf8"))
by_id = {str(j["jobId"]): j for j in pool}

stats = Counter()
for c in calls:
    jid = str(c.get("jobId") or "")
    call = (c.get("call") or "").upper()
    j = by_id.get(jid)
    if not j:
        stats["NOT-IN-POOL"] += 1
        print("NOT IN POOL (refused, no row creation):", jid, c.get("company"), c.get("title"))
        continue
    if call == "KEEP":
        # ANNOTATION-ONLY update: keep the row's existing call and stamp only
        # lane / comp / mission - e.g. mission judgments on already-called or built rows.
        if "mission" in c:
            if c.get("mission"):
                j["mission"] = str(c["mission"])[:220]
            else:
                j.pop("mission", None)
        if c.get("comp"):
            j["comp"] = c["comp"]
        if c.get("lane") in ("TAC", "STRAT"):
            j["lane"] = c["lane"]
        stats["annotated"] += 1
        continue
    if call not in VOCAB:
        stats["BAD-CALL"] += 1
        print("CALL OUTSIDE VOCABULARY (refused):", jid, repr(c.get("call")))
        continue
    changed = not (j.get("call") == call and c.get("why", "") in (j.get("callWhy") or ""))
    if changed:
        j["call"] = call
        why = c.get("why") or ""
        if why and why not in (j.get("callWhy") or ""):
            j["callWhy"] = ((j.get("callWhy") or "") + " || " + why).strip(" |")
    # Field annotations apply even when the call itself is unchanged (mission stamping on
    # already-called rows was once silently skipped by the unchanged short-circuit).
    if c.get("lane") in ("TAC", "STRAT"):
        j["lane"] = c["lane"]
    elif changed and call not in ("SKIP",):
        stamp_lane(j)
    # comp stamping (board P-tags read the comp FIELD; whys carrying
    # "$190K" while the field stayed empty made real P1 rows render as P3). The reader
    # records the JD's stated band; harvest comp is never overwritten by an empty call.
    if c.get("comp"):
        j["comp"] = c["comp"]
    # MISSION axis: reader judgment of the company's stated mission, per the
    # SOP "MISSION" definition. Non-empty string = M (the string is the one-line reason);
    # an explicit empty string clears it.
    if "mission" in c:
        if c.get("mission"):
            j["mission"] = str(c["mission"])[:220]
        else:
            j.pop("mission", None)
    if call == "SKIP":
        j.pop("lane", None)
    stats[call if changed else "unchanged"] += 1

json.dump(pool, open(POOL, "w", encoding="utf8"), indent=1, ensure_ascii=False)
print("applied:", dict(stats))
