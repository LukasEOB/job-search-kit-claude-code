# -*- coding: utf-8 -*-
"""Ingest the owner's board ticks (board-state.json from the board's 💾 button, lands in Downloads)
into the tracker of record. Run from the project root:  python resume-workspace/sourcing/ingest_state.py

Flow: Downloads/board-state.json -> sourcing/board-state.json (canonical) -> roles.tracked.json
statuses updated -> board regenerated with permanent server-side APPLIED badges.
The HTML board is THE tracker (owner rule); this script makes the ticks durable."""
import json, os, shutil, io, sys, datetime
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

DL = os.path.join(os.path.expanduser("~"), "Downloads", "board-state.json")
CANON = "resume-workspace/sourcing/board-state.json"
TRACKER = "resume-workspace/roles.tracked.json"
POOL = "resume-workspace/sourcing/sourced-jobs.json"

if not os.path.exists(DL) and not os.path.exists(CANON):
    print("no board-state.json found in Downloads or sourcing/. Click the 💾 button on the board first.")
    sys.exit(1)

if os.path.exists(DL):
    # merge (never lose previously ingested ticks if the browser's localStorage was wiped)
    new = json.load(open(DL, encoding="utf8"))
    old = json.load(open(CANON, encoding="utf8")) if os.path.exists(CANON) else {"applied": [], "tossed": []}
    # Preserve every other canonical key (watch, linkedinAppliedSync, ticksImport); an older
    # merge silently dropped them.
    merged = dict(old)
    merged["applied"] = sorted(set(old.get("applied", [])) | set(new.get("applied", [])))
    merged["tossed"] = sorted(set(old.get("tossed", [])) | set(new.get("tossed", [])))
    merged["ingested"] = datetime.date.today().isoformat()
    # closed ticks (3rd board column): row goes GONE + on watch;
    # the daily sweep job-page recheck resurfaces it loudly if it reopens.
    closed_ticks = [str(c) for c in new.get("closed", [])]
    if closed_ticks:
        merged["watch"] = sorted(set(str(w) for w in merged.get("watch", [])) | set(closed_ticks))
        pl = json.load(open(POOL, encoding="utf8"))
        stamped = 0
        for j in pl:
            if str(j["jobId"]) in closed_ticks and (j.get("workplace") or "") != "GONE":
                j["workplace"] = "GONE"
                j["callWhy"] = (j.get("callWhy") or "") + " || GONE per owner board tick %s; on WATCH for reopen." % datetime.date.today().isoformat()
                stamped += 1
        json.dump(pl, open(POOL, "w", encoding="utf8"), indent=1, ensure_ascii=False)
        print("closed ticks: %d -> GONE + watch (%d stamped in pool)" % (len(closed_ticks), stamped))
    json.dump(merged, open(CANON, "w", encoding="utf8"), indent=1, ensure_ascii=False)
    os.remove(DL)
    print("ingested from Downloads: %d applied, %d tossed ticks" % (len(merged["applied"]), len(merged["tossed"])))
else:
    merged = json.load(open(CANON, encoding="utf8"))

state_applied = set(merged.get("applied", []))

# sync tracker statuses
trk = json.load(open(TRACKER, encoding="utf8"))
pool = {j["jobId"]: j for j in json.load(open(POOL, encoding="utf8"))}
tracked_ids = set()
updated = 0
for r in trk:
    u = json.dumps(r.get("urls", {}))
    for jid in state_applied:
        if jid in u:
            tracked_ids.add(jid)
            if r.get("status") != "applied":
                r["status"] = "applied"
                r["applied"] = r.get("applied") or ("%s per board tick (owner)" % datetime.date.today().isoformat())
                r["application"] = {"status": "submitted"}
                updated += 1
# ticks with no tracker entry get a minimal one so nothing is ever untracked
added = 0
for jid in state_applied - tracked_ids:
    p = pool.get(jid, {})
    trk.append({
        "id": "role_board_%s" % jid,
        "title": p.get("title", "?"),
        "company": p.get("company", "?"),
        "status": "applied",
        "applied": "%s per board tick (owner)" % datetime.date.today().isoformat(),
        "urls": {"job": "https://www.linkedin.com/jobs/view/%s/" % jid},
        "application": {"status": "submitted"},
        "notes": ["Auto-created from board-state ingest."],
    })
    added += 1
json.dump(trk, open(TRACKER, "w", encoding="utf8"), indent=1, ensure_ascii=False)
print("tracker: %d updated to applied, %d new entries created" % (updated, added))
