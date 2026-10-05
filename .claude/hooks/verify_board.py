# -*- coding: utf-8 -*-
"""PreToolUse guard for the job board (sourcing side of the campaign).

Why this exists: three sourcing regressions, all the same failure mode: Claude improvised a
faster harvest path and silently dropped a pipeline stage:
  1. searched only one of the core keywords instead of all of them
  2. changed the workplace filter from remote to include hybrid/onsite
  3. skipped the JD-level evaluate() + repost dedupe, so factory planners and GPU-datacenter
     builds reached the TAILORED bucket on a title regex
Promises do not hold. This hook blocks `board_gen.py` (the only way rows reach the owner's eyes)
unless the pool passes every invariant below. Fix path is always printed.

Search rules come from profile.json: search.coreKeywords, and per region in search.regions
requireCoreKeywords / requiredWorkplace / gateChecksManifests (a local-market token from
search.localMarkets is also accepted for a batch of that market's own region).

Invariants (checked on rows that are not applied / skipped / tossed):
  A. PROVENANCE  every batch on the board is registered in sourcing/batches.json with its search
                 manifest, the manifest carries all core keywords where the region requires them,
                 and its workplace filter is the region's requiredWorkplace (e.g. remote-only).
  B. JD FILTER   every TAILORED / REVIEW / GENERIC row carries a verdict (evaluate() actually ran).
  C. WALLS       titles that hit the hard walls (healthcare, construction/datacenter-build, factory,
                 compensation/HR, clearance) must be decision SKIP.
  D. DEDUPE      no two live rows share company + normalized title within a region.
  E. LANES       every live row that is not PASS carries a resume lane (TAC / STRAT). The tactical /
                 strategic lane is a permanent column, not a feature that can be dropped.
  G. UNSCORED    every live non-SKIP row carries a machine verdict: nothing sits unread.
  H. SAVE RULE   savedToLinkedIn implies easyApply: the Saved list is the EZ queue only.
  I. HARVEST FRESHNESS (added after a harvester sat orphaned for 9 days unnoticed) the newest
     daily-harvest-*.txt must be under 48h old. The authenticated harvester is the only source
     of the trustworthy remote filter and the easyApply flag; when it stops, saves silently go
     to zero and verify burns its checks on non-remote rows. Staleness BLOCKS the board so the
     morning routine fails loudly instead of degrading quietly.
  J. APPLIED REACHES THE TRACKER  board-state applied ids must not sit built-unsent/tracked.
Gates board_gen_v2.py (matcher is the substring "board_gen").
"""
import json, os, re, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

PROJECT = os.environ.get("CLAUDE_PROJECT_DIR") or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC_DIR = os.path.join(PROJECT, "resume-workspace", "sourcing")
POOL = os.path.join(SRC_DIR, "sourced-jobs.json")
BATCHES = os.path.join(SRC_DIR, "batches.json")
STATE = os.path.join(SRC_DIR, "board-state.json")

# WALLS: imported from sweep_lib (single source of truth). The hook used to keep its own copy,
# which drifted from classify's (watchlist bypass; "top secret" missing) and blocked the board.
# If the import fails (no profile.json, broken rule set), the gate BLOCKS - a wall check that
# silently self-degrades is the failure mode this project keeps paying for.
sys.path.insert(0, os.path.join(PROJECT, "resume-workspace", "sourcing"))
try:
    from sweep_lib import HARD_WALL_RX as WALLS, dedupe_key
    from sweep_lib import PROFILE, LOCAL_TOKENS, local_market
    from profile_lib import get as pget
except Exception as _e:
    print("verify_board: cannot import HARD_WALL_RX from sweep_lib (%s). Blocking - the wall "
          "invariant cannot run without its rule set." % _e, file=sys.stderr)
    sys.exit(2)
CORE_KW = {k.lower() for k in (pget(PROFILE, "search.coreKeywords", []) or [])}
REGIONS = pget(PROFILE, "search.regions", {}) or {}
LIVE_EXCLUDE_CALLS = {"APPLIED", "SKIP", "NEEDS-YOU", "VERIFY"}

def norm_key(co, ti):
    # The SHARED repost key (sweep_lib.dedupe_key, imported above). This hook kept a private copy
    # that stripped digits, so after the 2026-09-14 shared key started keeping them it blocked the
    # board on reqs dedupe_pool correctly keeps apart (one employer's PM 4 vs PM 5). One key, no copies.
    return dedupe_key(co, ti)

def validate():
    errs = []
    pool = json.load(open(POOL, encoding="utf8"))
    try:
        batches = json.load(open(BATCHES, encoding="utf8"))
    except Exception:
        batches = {}
    try:
        st = json.load(open(STATE, encoding="utf8"))
        applied, tossed = set(st.get("applied", [])), set(st.get("tossed", []))
    except Exception:
        applied, tossed = set(), set()

    # legacy batches (pre-2026-08-10 pipeline) are grouped under the "legacy" manifest
    for j in pool:
        if j.get("batch") in (None, 2, "daily", "week", "month-backfill") or isinstance(j.get("batch"), int):
            j["_mb"] = "legacy"
        else:
            j["_mb"] = str(j.get("batch"))
    live = [j for j in pool
            if j["jobId"] not in applied and j["jobId"] not in tossed
            and j.get("call") not in LIVE_EXCLUDE_CALLS
            and (j.get("workplace") or "") != "GONE"]

    # A. provenance
    seen_batches = sorted({j["_mb"] for j in pool})
    for b in seen_batches:
        m = batches.get(b)
        if not m:
            errs.append("PROVENANCE: batch '%s' has no search manifest in sourcing/batches.json" % b)
            continue
        region = m.get("region", "US")
        rc = REGIONS.get(region) or {}
        if not rc.get("gateChecksManifests", True):
            continue   # this region's rules are enforced at ingest only (old manifests predate them)
        kws = {k.lower() for k in m.get("keywords", [])}
        missing = CORE_KW - kws
        if missing and rc.get("requireCoreKeywords") and not m.get("keywordsExempt"):
            errs.append("PROVENANCE: batch '%s' was not searched with the %d core keywords (missing: %s)" % (b, len(CORE_KW), ", ".join(sorted(missing))))
        req = rc.get("requiredWorkplace")
        tok = str(m.get("workplace") or "").upper()
        local_ok = tok in LOCAL_TOKENS and bool(local_market({"region": region, "workplace": tok}))   # this region's markets only
        if req and m.get("workplace") != req and not local_ok:
            errs.append("PROVENANCE: %s batch '%s' workplace filter is '%s', must be '%s'" % (region, b, m.get("workplace"), req))

    # B. JD filter ran
    no_verdict = [j for j in live if j.get("decision") in ("TAILORED", "REVIEW", "GENERIC") and not j.get("verdict")]
    if no_verdict:
        by_batch = {}
        for j in no_verdict: by_batch[j.get("batch")] = by_batch.get(j.get("batch"), 0) + 1
        errs.append("JD FILTER SKIPPED: %d priority rows have no evaluate() verdict %s" % (len(no_verdict), by_batch))

    # C. walls
    wall_hits = [j for j in live if WALLS.search(j.get("title") or "") and j.get("decision") != "SKIP"]
    if wall_hits:
        ex = "; ".join("%s | %s" % ((j.get("company") or "")[:18], (j.get("title") or "")[:40]) for j in wall_hits[:4])
        errs.append("WALLS: %d rows hit a hard wall (healthcare/construction/factory/HR/clearance) but are not SKIP: %s" % (len(wall_hits), ex))

    # D. dedupe
    # Mirrors dedupe_pool exactly: same shared key, and a group whose calls DISAGREE is not a
    # duplicate to collapse (dedupe_pool keeps it apart on purpose), so it never blocks the board.
    groups = {}
    for j in live:
        groups.setdefault((j.get("region", "US"),) + norm_key(j.get("company"), j.get("title")), []).append(j)
    dups = 0
    for g in groups.values():
        if len(g) > 1 and len({j.get("call") for j in g if j.get("call")}) <= 1:
            dups += len(g) - 1
    if dups:
        errs.append("DEDUPE: %d live rows are company+title duplicates (multi-state reposts not collapsed)" % dups)

    # F. layout contract (Board_Spec.md): the generator's view list must match the spec, and lane
    # files must come from profile.json (lanes.TAC / lanes.STRAT generalResume), never a literal.
    gen = open(os.path.join(SRC_DIR, "board_gen_v2.py"), encoding="utf8").read()
    SPEC_VIEWS = ('VIEWS = [("SEND", "SEND BUILT"), ("TAILOR", "TO TAILOR"), ("MAYBE", "MAYBE"), ("GENERAL", "GENERAL"),' + chr(10) +
                  '         ("EZ", "EZ QUEUE"), ("QUEUE", "QUEUE"), ("UNSCORED", "UNSCORED"), ("MYSKIP", "MY SKIPS"), ("APPLIED", "APPLIED"), ("ALL", "ALL")]')
    SPEC_LANEFILE = 'LANE_FILE = {k: pget(PROFILE, "lanes.%s.generalResume" % k, "") for k in ("TAC", "STRAT")}'
    if SPEC_VIEWS not in gen:
        errs.append("LAYOUT: board_gen_v2.py view buttons differ from sourcing/Board_Spec.md. The owner must approve layout changes in chat; update the spec change log first.")
    if SPEC_LANEFILE not in gen:
        errs.append("LAYOUT: board_gen_v2.py no longer reads its lane files from profile.json (lanes.TAC / lanes.STRAT generalResume), see Board_Spec.md.")
    no_file = [k for k in ("TAC", "STRAT") if not pget(PROFILE, "lanes.%s.generalResume" % k, "")]
    if no_file:
        errs.append("LAYOUT: profile.json lanes.%s.generalResume is empty: every lane needs its General resume file name." % "/".join(no_file))

    # E. lanes
    no_lane = [j for j in live if j.get("verdict") != "PASS" and j.get("decision") != "SKIP" and not j.get("lane")]
    if no_lane:
        errs.append("LANES: %d live rows have no TAC/STRAT resume lane (the tactical/strategic column is permanent)" % len(no_lane))

    # G. score-at-birth: every live non-SKIP row carries a machine verdict
    unscored = [j for j in live if j.get("decision") != "SKIP" and not j.get("verdict")]
    if unscored:
        errs.append("UNSCORED: %d live rows have no machine verdict (score-at-birth violated; run resume-workspace/sourcing/backfill_score.py)" % len(unscored))

    # H. save rule: LinkedIn Saved is the Easy Apply queue ONLY
    bad_saves = [j for j in pool if j.get("savedToLinkedIn") and not j.get("easyApply")]
    if bad_saves:
        errs.append("SAVE RULE: %d rows carry savedToLinkedIn but are not easyApply (the Saved list is the EZ queue only)" % len(bad_saves))

    # I. harvest freshness: the authenticated harvester must actually be running.
    import glob, time
    hv = sorted(glob.glob(os.path.join(SRC_DIR, "daily-harvest-*.txt")))
    if not hv:
        errs.append("HARVEST FRESHNESS: no daily-harvest files exist at all. NEEDS-YOU: run voyager_harvest.js (see PIPELINE_SPEC.md).")
    else:
        age_h = (time.time() - os.path.getmtime(hv[-1])) / 3600.0
        if age_h > 48:
            errs.append("HARVEST FRESHNESS: newest harvest file %s is %.0f hours old (limit 48). "
                        "easyApply flags and the trusted remote filter are stale. NEEDS-YOU: run "
                        "voyager_harvest.js in the logged-in browser, ingest, then regenerate." % (os.path.basename(hv[-1]), age_h))
        else:
            # I2. harvest CONTENT health (a broken harvester still writes a FRESH file - one #HTTP
            # line, or rows with blank companies and easyApply hard-0 - and mtime alone calls that
            # healthy).
            lines = [l for l in open(hv[-1], encoding="utf8", errors="replace").read().split("\n")
                     if l.strip() and not l.startswith("#")]
            rows5 = [l.split("|") for l in lines if len(l.split("|")) >= 5]
            if len(rows5) < 25:
                errs.append("HARVEST CONTENT: newest harvest file has only %d valid rows (floor 25). "
                            "A fresh-but-broken harvest is not a harvest. NEEDS-YOU: check voyager_harvest.js "
                            "against the live endpoint (see PIPELINE_SPEC.md, harvester row)." % len(rows5))
            else:
                blank_co = sum(1 for p in rows5 if not p[2].strip())
                ez = sum(1 for p in rows5 if p[4].strip() == "1")
                if blank_co > len(rows5) * 0.05:
                    errs.append("HARVEST CONTENT: %d/%d rows have a blank company (extraction broke; "
                                "the JobPostingCard schema likely changed again)." % (blank_co, len(rows5)))
                if ez < 5:
                    errs.append("HARVEST CONTENT: only %d easyApply rows in %d (expected a meaningful share). "
                                "easyApply extraction is likely broken; ingesting would wipe flags pool-wide." % (ez, len(rows5)))

    # J. APPLIED REACHES THE TRACKER: an id in board-state applied whose tracker entry is still
    # built-unsent/tracked means sync_applied.py did not run after the Job Tracker scrape; the board
    # would show a sent application under SEND BUILT and leave its docx unfrozen.
    try:
        trk = json.load(open(os.path.join(PROJECT, "resume-workspace", "roles.tracked.json"), encoding="utf8"))
        stuck = []
        for r in trk:
            if (r.get("status") or "") in ("built-unsent", "tracked"):
                ids = re.findall(r"/jobs/view/(\d+)", json.dumps(r.get("urls") or {}))
                if any(i in applied for i in ids):
                    stuck.append("%s | %s" % ((r.get("company") or "")[:18], (r.get("title") or "")[:40]))
        if stuck:
            errs.append("APPLIED NOT TRACKED: %d tracker entries are built-unsent/tracked but board-state records them "
                        "applied (run resume-workspace/sourcing/sync_applied.py): %s" % (len(stuck), "; ".join(stuck[:4])))
    except Exception:
        pass

    return errs, len(pool), len(live)

def main():
    manual = "--check" in sys.argv
    data = {}
    if not manual:
        try:
            data = json.load(sys.stdin)
        except Exception:
            data = {}
    cmd = (data.get("tool_input") or {}).get("command", "") if data else ""
    if not manual and "board_gen" not in cmd:
        sys.exit(0)
    errs, n_pool, n_live = validate()
    if errs:
        print("BOARD REGEN BLOCKED by verify_board.py (%d pool rows, %d live):" % (n_pool, n_live))
        for e in errs: print("  - " + e)
        print("Fix: register the batch manifest in sourcing/batches.json, then run")
        print("     python resume-workspace/sourcing/reclassify_batch.py <batch>   (classifier + JD evaluate + lanes)")
        print("     python resume-workspace/sourcing/dedupe_pool.py                (collapse reposts)")
        print("Never ingest through an ad-hoc script: use resume-workspace/sourcing/ingest_harvest.py.")
        sys.exit(2)
    print("verify_board: OK (%d pool rows, %d live, all batches registered, JD filter + walls + dedupe + lanes hold)" % (n_pool, n_live))
    sys.exit(0)

if __name__ == "__main__":
    main()
