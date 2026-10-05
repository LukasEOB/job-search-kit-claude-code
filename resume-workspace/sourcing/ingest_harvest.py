# -*- coding: utf-8 -*-
"""THE ONLY WAY a harvest reaches the board. No ad-hoc ingest scripts. Ever.

    python resume-workspace/sourcing/ingest_harvest.py <harvest.txt> <batch-name> \
        --region US --workplace remote --window r604800 \
        --keywords <every keyword in profile.json search.coreKeywords, each in quotes>

Region rules come from profile.json search.regions.<REGION>: requireCoreKeywords (all core
keywords must be listed) and requiredWorkplace (e.g. remote-only); local-market tokens from
search.localMarkets (e.g. --workplace code-hyb) are accepted for that market's region.

Harvest file format (what the browser/API harvester writes): id|title|company|location|easyApply
(optional extra columns after that are ignored). Stages, in order, none skippable:
  1. register the search manifest in batches.json   (provenance: verify_board checks it)
  2. add new rows, deduped by jobId AND company+title (within file and vs pool)
  3. reclassify_batch.py on the batch              (daily_sweep classifier + JD fetch + evaluate())
  4. dedupe_pool.py                                 (collapse multi-state reposts)
  5. lane flags                                     (TAC / STRAT resume lane on every live row)
  6. board_gen.py                                   (guarded by verify_board.py)
"""
import json, os, re, sys, io, subprocess, datetime, argparse
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(os.path.dirname(HERE))
POOL = os.path.join(HERE, "sourced-jobs.json")
BATCHES = os.path.join(HERE, "batches.json")
PY = sys.executable

ap = argparse.ArgumentParser()
ap.add_argument("harvest"); ap.add_argument("batch")
ap.add_argument("--region", default="US"); ap.add_argument("--workplace", default="remote")
ap.add_argument("--window", default="r604800"); ap.add_argument("--keywords", nargs="+", required=True)
ap.add_argument("--method", default="logged-in Voyager API")
a = ap.parse_args()
T = datetime.date.today().isoformat()

# 1. manifest
b = json.load(open(BATCHES, encoding="utf8"))
b[a.batch] = {"region": a.region, "workplace": a.workplace, "window": a.window, "harvested": T,
              "keywords": a.keywords, "method": a.method, "source": os.path.basename(a.harvest)}
json.dump(b, open(BATCHES, "w", encoding="utf8"), indent=1, ensure_ascii=False)
sys.path.insert(0, HERE)
from sweep_lib import LOCAL_TOKENS, enrich_from_harvest, local_market, PROFILE
from profile_lib import get as pget
RC = pget(PROFILE, "search.regions." + a.region, {}) or {}
core = {k.lower() for k in (pget(PROFILE, "search.coreKeywords", []) or [])}
if RC.get("requireCoreKeywords") and not core <= {k.lower() for k in a.keywords}:
    print("REFUSED: a %s batch must be searched with all %d core keywords. Missing:" % (a.region, len(core)),
          core - {k.lower() for k in a.keywords}); sys.exit(2)
WP = "REMOTE" if a.workplace == "remote" else a.workplace.upper()
# Hybrid/onsite is allowed ONLY in a local market of this region (search.localMarkets).
REGION_TOKENS = [t for t in LOCAL_TOKENS if local_market({"region": a.region, "workplace": t})]
REQ = RC.get("requiredWorkplace")
if REQ and a.workplace != REQ and WP not in REGION_TOKENS:
    print("REFUSED: %s batches must use workplace '%s'%s. Got: %s" % (
        a.region, REQ, (" or a local-market token %s" % REGION_TOKENS) if REGION_TOKENS else "", a.workplace)); sys.exit(2)

# 2. rows
pool = json.load(open(POOL, encoding="utf8"))
by_id = {j["jobId"]: j for j in pool}
from sweep_lib import dedupe_key as ck   # shared repost key; private copies drifted
seen = {ck(j.get("company"), j.get("title")) for j in pool if j.get("region", "US") == a.region}
added = dup = 0
for line in open(a.harvest, encoding="utf8", errors="replace"):
    p = line.rstrip("\n").split("|")
    if len(p) < 5: continue
    jid, title, co, loc, ez = p[:5]
    if jid in by_id:
        # Enrichment (PIPELINE_SPEC.md, ingest row): a known row seen by the authenticated
        # harvester gets its easyApply flag and (if blind) REMOTE stamped, instead of the
        # old lastSeen-only touch that left guest-sourced rows blind forever.
        enrich_from_harvest(by_id[jid], ez == "1", WP)
        by_id[jid]["lastSeen"] = T; dup += 1; continue
    k = ck(co, title)
    if k in seen: dup += 1; continue
    seen.add(k)
    row = {"jobId": jid, "title": title, "company": co, "location": loc, "region": a.region,
           "workplace": WP,
           "easyApply": ez == "1", "batch": a.batch, "decision": "GENERIC-B", "flags": ["ingest"],
           "firstSeen": T, "lastSeen": T, "url": "https://www.linkedin.com/jobs/view/%s/" % jid}
    pool.append(row); by_id[jid] = row; added += 1
json.dump(pool, open(POOL, "w", encoding="utf8"), indent=1, ensure_ascii=False)
print("ingest: +%d new rows, %d dupes skipped (batch %s)" % (added, dup, a.batch))

# 3-4. classifier + JD evaluate, then repost collapse
# REGION FIX: reclassify_batch.py selects rows by region and defaults to US
# (REGION = "EU" if "--eu" in sys.argv else "US"). This call once never forwarded the region, so an
# EU ingest reclassified 0 rows: every EU row stayed GENERIC-B with no verdict, no call and no
# score, which trips verify_board invariant G (unscored live = 0). Seen as "+386 new rows" and
# "scored: 0" in the same run. Forward the flag.
for script, args in (("reclassify_batch.py", [a.batch] + (["--eu"] if a.region == "EU" else [])),
                     ("dedupe_pool.py", [])):
    r = subprocess.run([PY, os.path.join(HERE, script)] + args, cwd=PROJECT)
    if r.returncode != 0: print("STAGE FAILED:", script); sys.exit(2)

# 5. lanes (the ONE lane rule, sweep_lib.stamp_lane; rows that are not live keep what they have)
from sweep_lib import stamp_lane
pool = json.load(open(POOL, encoding="utf8"))
for j in pool:
    if j.get("batch") != a.batch or j.get("decision") == "SKIP" or j.get("verdict") == "PASS" or j.get("call") in ("APPLIED", "SKIP"):
        continue
    stamp_lane(j)
json.dump(pool, open(POOL, "w", encoding="utf8"), indent=1, ensure_ascii=False)

# 6. board (hook-guarded)
r = subprocess.run([PY, os.path.join(HERE, "board_gen_v2.py")], cwd=PROJECT)
sys.exit(r.returncode)
