# -*- coding: utf-8 -*-
"""Stamp APPLIED/CLOSED onto pool rows from the tracker and board-state, BEFORE any call is stamped
or any row is saved to LinkedIn.

Why: the daily sweep once read a repost as TAILOR and would have told the owner to apply to the
exact role they already had a recruiter screen for. board_gen cross-references the tracker for
the badge, but the stamping step never did. Reposts get new job ids, so id-matching alone is not enough:
match on company + normalized title too.

Run after ingest_harvest.py and before stamping reader calls."""
import json, os, re, sys, io, datetime
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
WS = os.path.dirname(HERE)
POOL = os.path.join(HERE, "sourced-jobs.json")

# REPOST MATCH: an old private key was company[:8] + the first 25 letters of the title in any
# region, so nine different "Senior Technical Program Manager ..." teams of one employer and a closed
# US req matched one tracked application each and were hidden as APPLIED/SKIP (29 rows, 4 of them
# true reposts). A repost now needs the shared dedupe_key AND the tracked req's region.
sys.path.insert(0, HERE)
from sweep_lib import dedupe_key, stamp_lane, region_of

pool = json.load(open(POOL, encoding="utf8"))
try:
    st = json.load(open(os.path.join(HERE, "board-state.json"), encoding="utf8"))
    applied_ids = set(st.get("applied", []))
except Exception:
    applied_ids = set()
TRK = os.path.join(WS, "roles.tracked.json")
try:
    _raw = open(TRK, encoding="utf8").read()
    trk = json.loads(_raw)
    _ind = re.search(r"\n( +)\{", _raw)
    TRK_INDENT = len(_ind.group(1)) if _ind else 1
except Exception:
    trk = []

# APPLIED STATE -> TRACKER. The Job Tracker scrape and board ticks put ids into board-state applied,
# but only a board-tick ingest ever flipped roles.tracked.json. Seven built resumes already sent
# stayed built-unsent: stale "Send it" notes, a SEND BUILT row for a sent application, and no
# check_output freeze on the sent docx. A tracked or built-unsent entry whose job id is in
# board-state applied is applied, dated by the first commit that recorded the id.
def first_recorded(jid):
    try:
        import subprocess
        out = subprocess.run(["git", "log", "--reverse", "--format=%ad", "--date=short", "-S" + jid, "--",
                              "board-state.json"], cwd=HERE, capture_output=True, text=True, timeout=60).stdout.split()
        return out[0] if out else None
    except Exception:
        return None

n_trk = 0
for r in trk:
    if (r.get("status") or "") not in ("built-unsent", "tracked"):
        continue
    urls = r.get("urls") if isinstance(r.get("urls"), dict) else {}
    hit = [m.group(1) for m in (re.search(r"/jobs/view/(\d+)", str(u)) for u in urls.values()) if m and m.group(1) in applied_ids]
    if not hit:
        continue
    when = first_recorded(hit[0]) or ("on or before " + datetime.date.today().isoformat())
    r["status"] = "applied"
    r["applied"] = r.get("applied") or ("%s (first recorded in board-state applied: LinkedIn Job Tracker or board tick)" % when)
    r["application"] = {"status": "submitted"}
    n_trk += 1
    print("tracker: %s | %s -> applied (%s)" % (r.get("company"), r.get("title"), when))
if n_trk:
    json.dump(trk, open(TRK, "w", encoding="utf8"), indent=TRK_INDENT, ensure_ascii=False)

by_key, by_id = {}, {}
pool_by_id = {str(j["jobId"]): j for j in pool}
for r in trk:
    status = r.get("status") or ""
    if status not in ("applied", "closed-before-apply", "built-unsent"):
        continue
    ids = []
    for u in (r.get("urls") or {}).values() if isinstance(r.get("urls"), dict) else []:
        m = re.search(r"/jobs/view/(\d+)", str(u))
        if m:
            by_id[m.group(1)] = (status, r)
            ids.append(m.group(1))
    regions = {region_of(pool_by_id.get(i)) for i in ids} - {None}
    by_key.setdefault(dedupe_key(r.get("company"), r.get("title")), []).append((status, r, regions))

def repost_of(j):
    for status, r, regions in by_key.get(dedupe_key(j.get("company"), j.get("title")), []):
        if not regions or region_of(j) in regions:
            return status, r
    return None

n_app = n_closed = n_built = n_stale = n_unstamped = 0
for j in pool:
    if j["jobId"] in applied_ids and "BUILT unsent" in (j.get("callWhy") or ""):
        fixed = re.sub(r"BUILT unsent: (.*?)\. Send it\.", r"Applied (board-state). Resume sent: \1.", j["callWhy"])
        if fixed != j["callWhy"]:
            j["callWhy"] = fixed
            n_stale += 1
    if (j.get("callWhy") or "").startswith("REPOST of the tracked req.") and str(j["jobId"]) not in by_id \
            and j["jobId"] not in applied_ids and not repost_of(j):
        j.pop("call", None)
        j["callWhy"] = ("Un-stamped %s: had been marked a repost of a tracked req on the old loose title match "
                        "(first 25 letters, any region). Different req; needs a reader call." % datetime.date.today().isoformat())
        stamp_lane(j)
        n_unstamped += 1
        continue
    if j.get("call") in ("APPLIED",):
        continue
    hit = by_id.get(str(j["jobId"])) or repost_of(j)
    if j["jobId"] in applied_ids:
        if j.get("call") != "APPLIED":
            j["call"] = "APPLIED"; j.pop("lane", None); n_app += 1
        continue
    if not hit:
        continue
    status, r = hit
    same_id = str(j["jobId"]) in by_id
    tag = "" if same_id else "REPOST of the tracked req. "
    if status == "applied":
        j["call"] = "APPLIED"; j.pop("lane", None)
        j["callWhy"] = tag + "Already applied (tracker: %s). Do not re-apply." % (r.get("applied") or "date unrecorded"); n_app += 1
    elif status == "closed-before-apply":
        j["call"] = "SKIP"; j.pop("lane", None)
        j["callWhy"] = tag + "Tracked as closed before applying."; n_closed += 1
    elif status == "built-unsent":
        res = (r.get("output") or {}).get("resume", "")
        j["call"] = "NEEDS-YOU"; j["lane"] = j.get("lane") or "STRAT"
        j["callWhy"] = tag + "BUILT unsent: %s. Send it." % (res or "resume on disk"); n_built += 1

json.dump(pool, open(POOL, "w", encoding="utf8"), indent=1, ensure_ascii=False)
print("sync_applied: %d marked APPLIED, %d CLOSED, %d NEEDS-YOU (built-unsent); tracker %d flipped to applied, %d stale 'Send it' notes cleared, %d false reposts un-stamped"
      % (n_app, n_closed, n_built, n_trk, n_stale, n_unstamped))
