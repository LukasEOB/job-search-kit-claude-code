# -*- coding: utf-8 -*-
"""DAILY guest sweep (24h window): every profile search.coreKeywords entry, f_TPR=r86400 (24 hours),
in the region named by search.guestSweepRegion (its guestLocation and requiredWorkplace filter),
deduped against the pool by jobId AND company+title (catches new-ID reposts).

Design:
- rules, fetch_jd and evaluate() live in sweep_lib.py (one source of truth)
- SCORE AT BIRTH: every non-SKIP row (GENERIC-B included) gets a JD fetch and a
  machine verdict the day it arrives. Nothing enters the pool unread.
- lanes stamped at scoring time, so the daily path never produces laneless rows.
"""
import json, re, os, sys, time, io, urllib.parse, datetime
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sweep_lib import ROOT, get, strip_tags, classify, score_rows, WATCHLIST, dedupe_key
from sweep_lib import PROFILE
from profile_lib import get as pget

SRC = json.load(open(os.path.join(ROOT, "sourced-jobs.json"), encoding="utf8"))
seen_ids = {j["jobId"] for j in SRC}
ck = dedupe_key   # shared repost key; a private copy once never collapsed whitespace
seen_ct = {ck(j.get("company"), j.get("title")) for j in SRC}

CORE = list(pget(PROFILE, "search.coreKeywords", []) or [])
REGION = pget(PROFILE, "search.guestSweepRegion", "US") or "US"
_RC = pget(PROFILE, "search.regions." + REGION, {}) or {}
# LinkedIn workplace filter codes: 1 = on-site, 2 = remote, 3 = hybrid
F_WT = {"remote": "2", "hybrid": "3", "onsite": "1"}.get(str(_RC.get("requiredWorkplace") or "remote").lower(), "2")
LOC = urllib.parse.quote(_RC.get("guestLocation") or "United States")
if not CORE:
    print("daily sweep: profile.json search.coreKeywords is empty; nothing to search."); sys.exit(2)
new, reposts = [], 0
for kw, pages in [(k, 40) for k in CORE]:
    for s in range(0, pages * 10, 10):
        h = get("https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords=" +
                urllib.parse.quote(kw) + "&location=" + LOC + "&f_WT=" + F_WT + "&f_TPR=r86400&start=" + str(s))
        if not h:
            break
        cards = h.split("<li>")[1:]
        if not cards:
            break
        for c in cards:
            jid = (re.search(r'data-entity-urn="urn:li:jobPosting:(\d+)"', c) or [None, ""])[1]
            if not jid or jid in seen_ids:
                continue
            ti = strip_tags((re.search(r"base-search-card__title[^>]*>\s*([^<]+)", c) or [None, ""])[1])[:60]
            co = strip_tags((re.search(r"base-search-card__subtitle[^>]*>.*?>([^<]+)<", c, re.S) or
                             re.search(r"base-search-card__subtitle[^>]*>\s*([^<]+)", c) or [None, ""])[1])[:30]
            loc = strip_tags((re.search(r"job-search-card__location[^>]*>\s*([^<]+)", c) or [None, ""])[1])[:26]
            dt = (re.search(r'datetime="([^"]+)"', c) or [None, ""])[1]
            seen_ids.add(jid)
            if ck(co, ti) in seen_ct:
                reposts += 1
                continue
            seen_ct.add(ck(co, ti))
            new.append({"jobId": jid, "title": ti, "company": co, "location": loc, "posted": dt,
                        "batch": "daily", "region": REGION})
        time.sleep(0.35)
print("daily sweep: %d NEW unique postings (%d new-ID reposts of known roles skipped)" % (len(new), reposts))

today = datetime.date.today().isoformat()
kept = []
for j in new:
    d, r = classify(j)
    j.update({"decision": d, "flags": [r, "daily-sweep"], "firstSeen": today, "lastSeen": today,
              "url": "https://www.linkedin.com/jobs/view/%s/" % j["jobId"]})
    kept.append(j)

print("classified: %s" % {k: sum(1 for j in kept if j["decision"] == k) for k in set(x["decision"] for x in kept)})
to_score = [j for j in kept if j["decision"] != "SKIP"]
print("score-at-birth: fetching + evaluating %d rows (everything non-SKIP, GENERIC-B included)..." % len(to_score))
stats = score_rows(kept)
print("scored: %(scored)d | no-JD: %(no_jd)d | wall-skipped (no fetch): %(skipped)d" % stats)

SRC.extend(kept)
json.dump(SRC, open(os.path.join(ROOT, "sourced-jobs.json"), "w", encoding="utf8"), indent=1, ensure_ascii=False)

try:
    _st = json.load(open(os.path.join(ROOT, "board-state.json"), encoding="utf8"))
    _ap, _tx = set(_st.get("applied", [])), set(_st.get("tossed", []))
except Exception:
    _ap, _tx = set(), set()
unscored_live = sum(1 for j in SRC if str(j["jobId"]) not in _ap and str(j["jobId"]) not in _tx
                    and j.get("decision") != "SKIP" and not j.get("verdict")
                    and j.get("call") not in ("APPLIED", "SKIP") and (j.get("workplace") or "") != "GONE")
print("MEASURED: unscored live rows in pool after this sweep: %d (hook invariant G definition; must be 0)" % unscored_live)

wl = [j for j in kept if any("WATCHLIST" in str(f) for f in j.get("flags", []))]
print("\nWATCHLIST hits this sweep (%d) - always shown, verdicts advisory only:" % len(wl))
for j in wl:
    print("  %-7s %-48s %-20s %s" % (j.get("verdict", "?"), j["title"][:48], j["company"][:20], j.get("why", "")[:60]))
ap = sorted([j for j in kept if j.get("verdict") == "APPLY"], key=lambda x: -x.get("score", 0))
mb = [j for j in kept if j.get("verdict") == "MAYBE"]
print("\nNEW today - APPLY (%d):" % len(ap))
for j in ap:
    print("  %2d  %-48s %-24s %s" % (j.get("score", 0), j["title"][:48], j["company"][:24], j["why"][:66]))
print("\nNEW MAYBE: %d | pool total: %d" % (len(mb), len(SRC)))
