# -*- coding: utf-8 -*-
"""Pipeline regression self-test (PIPELINE_SPEC.md).

Runs in seconds, no network, no writes. Exit 0 = every registered feature contract holds.
Exit 2 = a feature regressed; the failure names it. A hook runs this after every
Edit/Write to sourcing/*.py and on demand:  python resume-workspace/sourcing/pipeline_selftest.py

Profile: profile.json at the repo root if present, otherwise profile.example.json (the first
output line says which; JOB_KIT_PROFILE=<file> overrides both). Contracts that depend on WHO is
searching (watchlist, local markets, currencies, J-axis vocabulary) are tested against the
FIXTURE profile below, so the test proves the mechanics and never asserts anyone's personal lists.
"""
import os, sys, io, re, copy, py_compile
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

# ---- which profile (first output line) ----
_forced = os.environ.get("JOB_KIT_PROFILE")
_cands = ([_forced] if _forced else []) + [os.path.join(PROJECT, "profile.json"), os.path.join(PROJECT, "profile.example.json")]
PROFILE_FILE = next((p for p in _cands if p and os.path.exists(p)), None)
if not PROFILE_FILE:
    print("profile: NONE (no profile.json or profile.example.json at %s)" % PROJECT)
    print("SELFTEST FAILED (1): no profile to test against. Copy profile.example.json to profile.json.")
    sys.exit(2)
os.environ["JOB_KIT_PROFILE"] = os.path.abspath(PROFILE_FILE)
print("profile: %s" % os.path.relpath(os.path.abspath(PROFILE_FILE), PROJECT))

FAILS = []
def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (": " + detail if detail and not ok else ""))
    if not ok:
        FAILS.append(name + (": " + detail if detail else ""))

# ---- imports compile ----
try:
    import sweep_lib
    check("sweep_lib imports (profile loads and compiles)", True)
except Exception as e:
    check("sweep_lib imports (profile loads and compiles)", False, str(e)); print("cannot continue"); sys.exit(2)
from profile_lib import get as pget
REAL = sweep_lib.PROFILE

for f in ("daily_sweep.py", "ingest_harvest.py", "apply_calls.py", "backfill_score.py",
          "verify_workplace.py", "ingest_state.py", "board_gen_v2.py", "sync_applied.py",
          "dedupe_pool.py", "reclassify_batch.py"):
    try:
        py_compile.compile(os.path.join(HERE, f), doraise=True)
        check("compiles: " + f, True)
    except Exception as e:
        check("compiles: " + f, False, str(e)[:120])
for f in ("verify_render.py", "verify_board.py", "check_output.py", "guard_render.py", "selftest_gate.py"):
    p = os.path.join(PROJECT, ".claude", "hooks", f)
    try:
        py_compile.compile(p, doraise=True)
        check("compiles: hooks/" + f, True)
    except Exception as e:
        check("compiles: hooks/" + f, False, str(e)[:120])

# ---- the loaded profile carries what the gates need ----
check("profile: search.coreKeywords set", bool(pget(REAL, "search.coreKeywords")),
      "the sweep, ingest and the board gate need at least one core keyword")
check("profile: lanes.TAC / lanes.STRAT generalResume set",
      all(pget(REAL, "lanes.%s.generalResume" % k) for k in ("TAC", "STRAT")),
      "verify_board invariant F blocks the board without both lane files")
check("profile: hardWallRegex compiles to a real rule set", sweep_lib.HARD_WALL_RX.pattern != sweep_lib._NOTHING
      or not pget(REAL, "scoring.hardWallRegex"))
check("profile: an empty regex list matches nothing (never everything)", sweep_lib._rx([]).search("any title") is None)
check("sweep_lib: no hard-coded applied-company list (the tracker knows what is applied)", not hasattr(sweep_lib, "APPLIED"))

# ---- comp_from_jd contract (USD parsing is in code, profile-independent) ----
c = sweep_lib.comp_from_jd
cases = [
    ("base pay range is $128,500 – $192,700 annually plus RSUs", "$128,500 - $192,700"),
    ("The pay: $121.5K-182.3K depending on level", "$121,500 - $182,300"),
    ("$70.00 to $76.00 /hr, W-2", "$70.00 - $76.00 /hr"),
    ("Gehalt: $137.970.00 to $150.000.00 pro Jahr", None),  # parses without crashing; value optional
    ("We offer a 401(k) plan with $6,000 match", None),
    ("Competitive compensation and equity.", None),
]
for txt, want in cases:
    try:
        got = c(txt)
        if want is None and "137.970" in txt:
            check("comp_from_jd: EU separators no-crash", True)
        elif want is None:
            check("comp_from_jd: %r stays None" % txt[:24], got is None, "got %r" % got)
        else:
            check("comp_from_jd: %r" % want, got == want, "got %r" % got)
    except Exception as e:
        check("comp_from_jd crashed on %r" % txt[:30], False, str(e)[:100])

# ---- enrich_from_harvest contract ----
try:
    e = sweep_lib.enrich_from_harvest
    r1 = {"jobId": "1"}                                # blind row
    e(r1, True)
    check("enrich: easyApply stamped", r1.get("easyApply") is True)
    check("enrich: empty workplace -> REMOTE", r1.get("workplace") == "REMOTE")
    r2 = {"jobId": "2", "workplace": "ONSITE", "easyApply": False}
    e(r2, True)
    check("enrich: verify truth never overwritten", r2["workplace"] == "ONSITE")
    check("enrich: easyApply updated on existing row", r2["easyApply"] is True)
    r3 = {"jobId": "3", "workplace": "GONE"}
    e(r3, False)
    check("enrich: GONE untouched", r3["workplace"] == "GONE")
except AttributeError:
    check("enrich_from_harvest exists in sweep_lib", False, "missing")
except Exception as ex:
    check("enrich_from_harvest contract", False, str(ex)[:100])

# ---- evaluate + classify + stamp_lane smoke on the loaded profile ----
try:
    v, why, sc = sweep_lib.evaluate("Senior Technical Program Manager, AWS cloud, AI agents, dashboards, remote")
    check("evaluate smoke returns verdict", v in ("APPLY", "MAYBE", "PASS", "FLAG"), repr(v))
except Exception as ex:
    check("evaluate smoke", False, str(ex)[:100])
try:
    d, r = sweep_lib.classify({"title": "Technical Program Manager", "company": "TestCo", "location": "United States"})
    check("classify smoke", d in ("SKIP", "GENERIC-B", "REVIEW", "GENERIC", "TAILORED"), repr(d))
except Exception as ex:
    check("classify smoke", False, str(ex)[:100])
try:
    row = {"jobId": "t", "title": "Principal Technical Program Manager", "comp": "$200,000"}
    sweep_lib.stamp_lane(row)
    check("stamp_lane smoke", row.get("lane") in ("TAC", "STRAT"), repr(row.get("lane")))
except Exception as ex:
    check("stamp_lane smoke", False, str(ex)[:100])

# ---- canonical artifact + contract markers ----
def has(path, marker, name):
    try:
        t = open(os.path.join(HERE, path), encoding="utf8", errors="replace").read()
        check(name, marker in t, "marker %r missing from %s" % (marker, path))
    except FileNotFoundError:
        check(name, False, path + " MISSING")

has("voyager_harvest.js", "voyagerHarvest", "harvester: canonical file + entrypoint")
has("voyager_harvest.js", "easyApply", "harvester: easyApply extraction present")
# harvester defects locked in (PIPELINE_SPEC.md, harvester row):
has("voyager_harvest.js", "locationUnion:(geoId:", "harvester: singular geoId form (List() form 500s)")
has("voyager_harvest.js", "EASY_APPLY_TEXT", "harvester: easyApply from footerItems (JobPosting stub wipe-guard)")
has("voyager_harvest.js", "JobPostingCard", "harvester: fields from JobPostingCard schema")
has("ingest_harvest.py", '["--eu"] if a.region == "EU"', "ingest: region forwarded to reclassify (EU scored 0 bug)")
has("ingest_harvest.py", "stamp_lane(j)", "ingest: lanes use the ONE shared lane rule (a private copy drifted)")
has("ingest_harvest.py", 'RC.get("requireCoreKeywords")', "ingest: core-keyword rule read from the profile")
has("voyager_verify.js", "clickHard", "verify: clickHard canonical")
has("voyager_verify.js", "SUSPENDED", "verify: suspended=closed rule")
has("verify_workplace.py", "SAVE REFUSED", "verify_workplace: non-easyApply save refusal")
has("apply_calls.py", '{"TAILOR", "MAYBE", "GENERIC", "SKIP", "NEEDS-YOU", "VERIFY"}', "apply_calls: closed vocabulary")
has("apply_calls.py", 'c.get("comp")', "apply_calls: reader comp stamping")
has("ingest_state.py", "merged = dict(old)", "ingest_state: canonical-key preservation")
has("board_gen_v2.py", 'STAFF_RX', "board: STAFF flag")
has("board_gen_v2.py", "'cl-'+c.dataset.id", "board: closed-tick column")
has("board_gen_v2.py", 'LANE_FILE = {k: pget(PROFILE, "lanes.%s.generalResume" % k, "") for k in ("TAC", "STRAT")}',
    "board: lane files come from the profile, never a literal")
has("daily_sweep.py", "score_rows", "guest sweep: score-at-birth wired")
has("daily_sweep.py", '"search.coreKeywords"', "guest sweep: keywords read from the profile")
hook_vb = open(os.path.join(PROJECT, ".claude", "hooks", "verify_board.py"), encoding="utf8", errors="replace").read()
check("verify_board: invariant G (unscored)", "unscored" in hook_vb.lower())
check("verify_board: invariant I (harvest freshness)", "daily-harvest" in hook_vb,
      "invariant I missing: harvest staleness can go silent again")
check("verify_board: invariant I2 (harvest content health)", "HARVEST CONTENT" in hook_vb,
      "I2 missing: a fresh-but-broken harvest (blank companies / easyApply hard-0) would pass")
check("verify_board: core keywords and region rules from the profile",
      '"search.coreKeywords"' in hook_vb and '"requiredWorkplace"' in hook_vb)
check("verify_board: lane-file check reads the profile", '"lanes.%s.generalResume"' in hook_vb)
# applied ids once reached board-state but never the tracker; sent builds sat built-unsent.
has("sync_applied.py", 'r["status"] = "applied"', "sync_applied: board-state applied flips tracker built-unsent/tracked")
has("sync_applied.py", "Resume sent:", "sync_applied: stale 'BUILT unsent ... Send it' notes cleared on applied rows")
has("board_gen_v2.py", "if jid in APPLIED_IDS: continue", "board: synthetic SEND rows never render an applied role")
check("verify_board: invariant J (applied reaches tracker)", "APPLIED NOT TRACKED" in hook_vb,
      "J missing: a sent application can sit in SEND BUILT with an unfrozen docx")
# a private 25-letter any-region repost key once hid 25 distinct reqs as APPLIED/SKIP.
has("sync_applied.py", "from sweep_lib import dedupe_key", "sync_applied: repost match uses the shared dedupe_key")
has("sync_applied.py", "region_of(j) in regions", "sync_applied: a repost must share the tracked req's region")
has("sync_applied.py", "Un-stamped", "sync_applied: false repost stamps are reverted to a reader call")
has("board_gen_v2.py", "from sweep_lib import dedupe_key, region_of", "board: tracker match uses the shared repost key + region")
check("region_of: US from a state code, EU from a French city",
      sweep_lib.region_of({"location": "Cambridge, MA"}) == "US"
      and sweep_lib.region_of({"location": "Lyon, Auvergne-Rhône-Alpes, France (Remote)"}) == "EU")
check("dedupe_key: '&' and 'and' are one req title",
      sweep_lib.dedupe_key("Globex", "Senior Program Manager, Enterprise Technology & AI")
      == sweep_lib.dedupe_key("Globex", "Senior Program Manager, Enterprise Technology and AI"))
check("dedupe_key: team suffixes stay distinct (Sr TPM - Platform vs - Storage)",
      sweep_lib.dedupe_key("Initech", "Senior Technical Program Manager - Platform")
      != sweep_lib.dedupe_key("Initech", "Senior Technical Program Manager - Storage"))
# the render hooks once skipped silently when renders ran from resume-workspace cwd
# (config path resolved against project root only, missing file = silent exit 0).
hook_vr = open(os.path.join(PROJECT, ".claude", "hooks", "verify_render.py"), encoding="utf8", errors="replace").read()
hook_gr = open(os.path.join(PROJECT, ".claude", "hooks", "guard_render.py"), encoding="utf8", errors="replace").read()
check("verify_render: workspace-cwd path resolution", 'os.path.join(project_dir(), "resume-workspace", cfg_path)' in hook_vr,
      "cwd fix missing: workspace-relative renders bypass the gate silently")
check("verify_render: unfound config BLOCKS", "cannot find config" in hook_vr,
      "missing-config silent pass is back")
check("guard_render: workspace-cwd path resolution", '"resume-workspace", p' in hook_gr,
      "cwd fix missing: overwrite guard skips workspace-relative renders")
# wall-list drift fixes (classify vs verify_board once diverged and blocked the board).
check("sweep_lib: HARD_WALL_RX single source", hasattr(sweep_lib, "HARD_WALL_RX"),
      "shared wall list missing - the two-copies drift class is back")
check("verify_board: imports shared walls", "from sweep_lib import HARD_WALL_RX" in hook_vb,
      "hook keeps a private wall copy - it WILL drift again")
bg = open(os.path.join(HERE, "board_gen_v2.py"), encoding="utf8", errors="replace").read()
check("board: hourly comp annualized in comp_key", "* 2000" in bg,
      "hourly bands render as P3 at $200K+ again")
check("board: synthetic SEND rows for pool-less builds", "SYNTHETIC SEND ROWS" in bg,
      "one-off builds are invisible on the board again")
check("verify.js: both closed-markers tested", "Not currently accepting" in
      open(os.path.join(HERE, "voyager_verify.js"), encoding="utf8", errors="replace").read(),
      "watch recheck will call closed jobs open again")
has("voyager_harvest.js", "workplaceTypes", "harvester: workplaceTypes option (local markets)")
has("voyager_harvest.js", "locationFilter", "harvester: locationFilter option (city inside a country geo)")
has("ingest_harvest.py", 'enrich_from_harvest(by_id[jid], ez == "1", WP)', "ingest: enrich uses the harvest's workplace")
has("verify_workplace.py", "local_token(j, wt)", "verify: local markets keep their calls (token, never SKIP flip)")
has("apply_calls.py", '"mission" in c', "apply_calls: mission field")
check("board: local-market tag + converted-currency tiering", "tag lc" in bg and "LOCAL_TOKENS" in bg and 'cur["perEur"]' in bg,
      "local-market rows untagged or converted-currency bands mis-tiered")
check("board: P tiers from pay.tiers", '"pay.tiers"' in bg)
has("apply_calls.py", 'call == "KEEP"', "apply_calls: annotation-only KEEP updates (mission on called rows)")
check("board: J/M tags + sort buttons", "_jd_match" in bg and "tag mi" in bg and "fs('best')" in bg and "data-b=" in bg,
      "P/J/M axes or the sort buttons fell off the board")
# one shared repost key (cross-source reposts slipped through three drifted copies).
try:
    _full = "Sr Principal Technical Program Manager - Enterprise and Emerging Technologies"
    check("dedupe_key: 80-char harvest title matches its 60-char guest twin",
          sweep_lib.dedupe_key("Acme", _full) == sweep_lib.dedupe_key("Acme", _full[:60]))
    check("dedupe_key: whitespace and punctuation collapse",
          sweep_lib.dedupe_key("Umbrella", "Principal TPM  -  Partner GTM") == sweep_lib.dedupe_key("Umbrella, Inc.", "Principal TPM - Partner GTM"))
    check("dedupe_key: different roles stay distinct",
          sweep_lib.dedupe_key("Hooli", "Technical Program Manager, Cloud") != sweep_lib.dedupe_key("Hooli", "Technical Program Manager, Ads"))
    check("dedupe_key: different pay bands stay distinct reqs",
          sweep_lib.dedupe_key("Vandelay", "Project Manager - $33.03 - $49.57 per hour")
          != sweep_lib.dedupe_key("Vandelay", "Project Manager - $57.69 - $67.31 per hour"))
except Exception as ex:
    check("dedupe_key contract", False, str(ex)[:100])
has("dedupe_pool.py", "conflicting reads of the same role stay visible", "dedupe_pool: never resolves conflicting calls")
has("dedupe_pool.py", "str(r[\"jobId\"]) in WATCH", "dedupe_pool: never drops a watched req")
has("dedupe_pool.py", "CALL_RANK", "dedupe_pool: live calls outrank SKIP as keeper")
has("dedupe_pool.py", "from sweep_lib import dedupe_key", "dedupe_pool: shared repost key")
has("dedupe_pool.py", "str(r[\"jobId\"]) in TRACKED", "dedupe_pool: tracker-referenced rows win and are never dropped")
has("ingest_harvest.py", "dedupe_key as ck", "ingest: shared repost key")
has("daily_sweep.py", "ck = dedupe_key", "guest sweep: shared repost key")
check("verify_board: invariant D uses the shared repost key", "return dedupe_key(co, ti)" in hook_vb,
      "the gate keeps a private dedupe key again - it drifted once and blocked the board")

# ==== FIXTURE PROFILE: the mechanics of the personal rules, tested on made-up values ====
FIX = copy.deepcopy(REAL)
FIX.setdefault("search", {})["localMarkets"] = [
    {"code": "LIS", "region": "EU", "locationRegex": ["lisbon", "lisboa"], "workplaces": ["hybrid", "onsite"]},
    {"code": "OPO", "region": "EU", "locationRegex": "porto", "workplaces": ["hybrid"]}]
FIX.setdefault("scoring", {})["hardWallRegex"] = ["healthcare", "supply chain", "clearance", "top secret"]
FIX["scoring"].setdefault("classify", {})["watchlist"] = ["acme robotics"]
FIX["scoring"]["evaluate"] = {
    "locationPinRegex": ["this is (a|an) (hybrid|onsite|on.site)", "must (be located|live|reside)"],
    "maxTravelPct": 20, "travelLanguageRegex": "travel[^.\\n]{0,60}(weekly|customer sites)",
    "domainJdRegex": "\\b(payer|medicaid)\\b", "domainJdLabel": "fixture domain",
    "strengths": {"AI": "\\b(ai)\\b", "adoption": "\\badoption\\b", "dashboards": "\\bdashboards?\\b",
                  "exec": "\\bexecutive\\b", "governance": "\\bgovernance\\b", "cloud": "\\b(cloud|aws)\\b"},
    "neverClaim": ["kafka"], "peopleMgmtRegex": "(\\d{1,2})\\+?\\s*years[^.\\n]{0,60}people",
    "peopleMgmtMinYears": 5, "applyMinScore": 9, "maybeMinScore": 5}
FIX["scoring"]["jAxis"] = {
    "tiers": {"J1": 70, "J2": 50},
    "genericWords": ["experience", "management", "program", "technical", "teams", "stakeholders"],
    "strongSingleWords": ["jira", "confluence", "dependencies", "dashboards", "governance", "adoption"],
    "languagesNotSpoken": ["german"], "credentialsRequiredNotHeld": ["pgmp", "cissp"], "credentialsHeld": ["pmp", "psm"],
    "degreeFieldsLacking": ["computer science"], "yearsBarRegex": "\\b(1[5-9]|[2-9]\\d)\\+?\\s*years", "yearsBarLabel": "15+ years bar",
    "domainGaps": ["\\bbsa\\b", "\\baml\\b", "ofac", "(recruiting|recruitment) operations", "(leading|managing) hr\\b", "\\bhr teams?"],
    "registryLowercaseSkills": [], "registryCredentialPhrases": ["SAFe"]}
FIX.setdefault("pay", {})["currencies"] = [
    {"code": "PLN", "markers": ["PLN", "zł"], "perEur": 4.3, "monthly": {"words": "month|miesi", "below": 100000}},
    {"code": "EUR", "markers": ["EUR", "€"], "perEur": 1}]
FIX["pay"]["rangeSeparators"] = ["-", "\\u2013", "\\bto\\b"]
FIX_BANK = "\n".join("- \U0001F6AB `%s`" % p for p in ("Kafka", "SAFe", "at the intersection of", "empower", "foster"))
FIX_KW = [["jira", "confluence", "dependencies", "dashboards", "governance", "stakeholder management"],
          ["jira", "confluence", "dependencies", "dashboards", "governance", "stakeholder management"]]
try:
    sweep_lib.configure(FIX)
    sweep_lib._J_VOCAB = sweep_lib._j_build_vocab(FIX_KW, FIX_BANK)
    lt, lm = sweep_lib.local_token, sweep_lib.local_market
    check("local: Lisbon hybrid -> LIS-HYB", lt({"region": "EU", "location": "Lisbon, Portugal (Hybrid)"}, 3) == "LIS-HYB")
    check("local: Lisbon onsite -> LIS-ONSITE", lt({"region": "EU", "location": "Lisboa, Portugal"}, 1) == "LIS-ONSITE")
    check("local: hybrid-only market keeps hybrid", lt({"region": "EU", "location": "Porto, Portugal (Hybrid)"}, 3) == "OPO-HYB")
    check("local: hybrid-only market refuses onsite", lt({"region": "EU", "location": "Porto, Portugal"}, 1) is None)
    check("local: a city outside the markets stays disqualified", lt({"region": "EU", "location": "Warsaw, Poland (Hybrid)"}, 3) is None)
    check("local: a market never matches another region's row", lm({"region": "US", "location": "Lisbon, OH"}) is None)
    check("local: tokens built from the profile", sweep_lib.LOCAL_TOKENS == ("LIS-HYB", "LIS-ONSITE", "OPO-HYB"),
          repr(sweep_lib.LOCAL_TOKENS))
    _jd = ("This is a hybrid role in Lisbon. Technical program manager, AI adoption, dashboards, "
           "executive stakeholders, governance, cloud AWS, roadmap.")
    check("evaluate: a pinned JD is a LOCATION hard fail outside local markets", "LOCATION" in sweep_lib.evaluate(_jd)[1])
    check("evaluate: local lane drops the location pin", sweep_lib.evaluate(_jd, local=True)[0] != "PASS")
    _r = {"jobId": "z"}
    sweep_lib.enrich_from_harvest(_r, False, "LIS-HYB")
    check("enrich: blind row takes the harvest's workplace token", _r.get("workplace") == "LIS-HYB")
    check("walls: fixture wall covers top secret", bool(sweep_lib.HARD_WALL_RX.search("Senior PM (Top Secret)")))
    d, r = sweep_lib.classify({"title": "Senior Program Manager, Supply Chain (Top Secret clearance)", "company": "Acme Robotics"})
    check("classify: walls beat watchlist (walled watchlist row keeps a WATCHLIST reason)", d == "SKIP" and "WATCHLIST" in r, "got %s/%s" % (d, r))
    d, r = sweep_lib.classify({"title": "Program Manager", "company": "Acme Robotics"})
    check("classify: watchlist company surfaces as TAILORED", (d, r) == ("TAILORED", "WATCHLIST COMPANY"), "got %s/%s" % (d, r))
    check("comp: monthly currency band", sweep_lib.comp_from_jd("Wynagrodzenie 12 000 - 18 000 zł miesięcznie") == "PLN 12,000 - 18,000 /mo",
          repr(sweep_lib.comp_from_jd("Wynagrodzenie 12 000 - 18 000 zł miesięcznie")))
    check("comp: EUR band", sweep_lib.comp_from_jd("Salary EUR 70.000 - 90.000 per year") == "EUR 70,000 - 90,000")
    check("comp: currency-less ranges ignored", sweep_lib.comp_from_jd("We serve 120 000 - 300 000 users") is None)
    # J axis (bank-vs-JD fit)
    _strong = sweep_lib.jd_match("Qualifications\n- 8+ years of technical program management experience with Jira and Confluence\n"
                                 "- Experience driving AI adoption and governance across engineering organizations\n"
                                 "- Executive dashboards and stakeholder management at scale\n")
    _weak = sweep_lib.jd_match("Requirements\n- 5+ years of experience in recruiting operations\n"
                               "- Proven experience leading HR teams through transformation\n"
                               "- Deep knowledge of BSA/AML and OFAC compliance\n")
    _alt = sweep_lib.jd_match("Qualifications\n- PMP, PgMP, CSM or SAFe certification preferred\n"
                              "- Experience with Jira and Confluence\n- Experience managing cross-team dependencies\n")
    check("J: strong fixture scores J1/J2", bool(_strong) and _strong["tier"] in ("J1", "J2"), repr(_strong))
    check("J: domain-gap fixture is J3 with domain blockers", bool(_weak) and _weak["tier"] == "J3"
          and any(b.startswith("domain:") for b in _weak["blockers"]), repr(_weak))
    check("J: strong outscores weak", bool(_strong and _weak) and _strong["score"] > _weak["score"])
    check("J: held-credential alternatives list never blocks on SAFe", bool(_alt) and "SAFe" not in _alt["blockers"], repr(_alt))
    _style = sweep_lib.jd_match("Qualifications\n- Ability to operate at the intersection of strategy and execution with Jira\n"
                                "- Experience that will empower and foster teams through executive dashboards\n"
                                "- Experience with Kafka streaming pipelines\n")
    check("J: style/overclaim registry bans never count as JD gaps", bool(_style)
          and not any(b in ("at the intersection of", "empower", "foster") for b in _style["blockers"]), repr(_style))
    check("J: real skill negatives still block (Kafka)", bool(_style) and "Kafka" in _style["blockers"], repr(_style))
except Exception as ex:
    check("fixture-profile contracts (local markets / currencies / walls / J axis)", False, repr(ex)[:160])
finally:
    sweep_lib.configure(REAL)          # leave the module exactly as the real profile built it
    sweep_lib._J_VOCAB = None

print()
if FAILS:
    print("SELFTEST FAILED (%d): the change you just made broke a registered feature." % len(FAILS))
    for f in FAILS:
        print("  - " + f)
    print("See resume-workspace/sourcing/PIPELINE_SPEC.md. Fix before proceeding.")
    sys.exit(2)
print("SELFTEST PASS: all registered pipeline features hold.")
sys.exit(0)
