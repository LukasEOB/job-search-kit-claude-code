# -*- coding: utf-8 -*-
"""Apply Voyager workplace-verification results to the pool (the "proper fix": verify BEFORE
reading, save the keepers to LinkedIn).

Input: a JSON file shaped like voyager_verify.js output:
  {"verified": {"<jobId>": {"wt": 1|2|3|null, "closed": bool}, ...},
   "saved": {"<jobId>": true|"...", ...}, "errors": {...}}

Effects on sourced-jobs.json (existing rows only, never adds rows):
  wt=2 -> workplace REMOTE (verified)
  wt=3 -> workplace HYBRID; any non-SKIP call flips to SKIP (remote-only search)
  wt=1 -> workplace ONSITE; any non-SKIP call flips to SKIP
  EXCEPT local markets (profile search.localMarkets): hybrid/onsite is allowed there, so the
  row takes a market token (CODE-HYB / CODE-ONSITE) and keeps its call.
  closed -> workplace GONE
  saved=true -> row gets savedToLinkedIn: date
Also appends saved ids to saved-<date>.json for audit.

Usage: python resume-workspace/sourcing/verify_workplace.py <results.json>
"""
import json, os, sys, io, datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from sweep_lib import local_token
POOL = os.path.join(HERE, "sourced-jobs.json")
TODAY = datetime.date.today().isoformat()

res = json.load(open(sys.argv[1], encoding="utf8"))
pool = json.load(open(POOL, encoding="utf8"))
by_id = {str(j["jobId"]): j for j in pool}

WT = {1: "ONSITE", 2: "REMOTE", 3: "HYBRID"}
n = {"REMOTE": 0, "HYBRID": 0, "ONSITE": 0, "LOCAL": 0, "GONE": 0, "unknown": 0, "flipped": 0, "saved": 0}

for jid, v in (res.get("verified") or {}).items():
    j = by_id.get(str(jid))
    if not j:
        continue
    if v.get("closed"):
        j["workplace"] = "GONE"; n["GONE"] += 1; continue
    wt = v.get("wt")
    if wt not in WT:
        n["unknown"] += 1; continue
    if wt in (1, 3):
        tok = local_token(j, wt)
        if tok:
            j["workplace"] = tok
            n["LOCAL"] += 1
            continue
    j["workplace"] = WT[wt]
    n[WT[wt]] += 1
    if wt in (1, 3) and j.get("call") not in (None, "", "SKIP", "APPLIED"):
        old = j.get("callWhy") or ""
        j["call"] = "SKIP"
        j["callWhy"] = "Workplace verified %s via Voyager %s (remote-only search). Prior call: %s" % (WT[wt], TODAY, old[:160])
        j.pop("lane", None)
        n["flipped"] += 1

# Save success = True (legacy) or the verified page-flow states
# "SAVED"/"ALREADY" from voyager_verify.js pageSave(). Anything else is a failure.
# Save rule C1: LinkedIn Saved is the Easy Apply queue ONLY, so a save stamp on a
# non-easyApply row is a rule violation and is refused loudly.
saved_ids = []
for jid, ok in (res.get("saved") or {}).items():
    if ok is True or ok in ("SAVED", "ALREADY") or (isinstance(ok, str) and ok.split(":")[-1] in ("SAVED", "ALREADY")):
        saved_ids.append(jid)
stamped = []
for jid in saved_ids:
    j = by_id.get(str(jid))
    if not j:
        continue
    if not j.get("easyApply"):
        print("SAVE REFUSED (not easyApply, rule C1): %s %s | %s" % (jid, (j.get("company") or "")[:20], (j.get("title") or "")[:40]))
        continue
    j["savedToLinkedIn"] = TODAY
    stamped.append(jid)
    n["saved"] += 1

json.dump(pool, open(POOL, "w", encoding="utf8"), indent=1, ensure_ascii=False)
if stamped:
    p = os.path.join(HERE, "saved-%s.json" % TODAY)
    prev = json.load(open(p, encoding="utf8")) if os.path.exists(p) else []
    json.dump(sorted(set(prev) | set(stamped)), open(p, "w", encoding="utf8"), indent=1)
errs = res.get("errors") or {}
print("verify_workplace: %s | errors: %d %s" % (n, len(errs), list(errs.items())[:5]))
