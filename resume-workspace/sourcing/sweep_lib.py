# -*- coding: utf-8 -*-
"""sweep_lib: the single source of truth for harvest classification, JD fetching,
machine scoring (evaluate) and lane stamping. daily_sweep.py, reclassify_batch.py and
backfill_score.py import from here; there is exactly one rule set.

Everything that depends on WHO is searching (target titles, walls, strengths, skills never to
claim, local markets, currencies, pay thresholds) lives in profile.json under search / scoring /
pay and is compiled by configure() at import. This file holds only the mechanics.

Scripts run from the repo root (paths are relative, matching the existing convention).
"""
import json, re, os, sys, time, io, urllib.request, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
if os.path.dirname(HERE) not in sys.path:
    sys.path.insert(0, os.path.dirname(HERE))   # profile_lib lives in resume-workspace/
from profile_lib import load_profile, get as pget, pattern as ppat

ROOT = "resume-workspace/sourcing"
JDD = os.path.join(ROOT, "jds")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"}


def get(url, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=20) as r:
                if r.status == 200:
                    return r.read().decode("utf8", "replace")
        except Exception:
            pass
        time.sleep(1.2 + i)
    return None


def strip_tags(h):
    h = re.sub(r"<br[^>]*>", "\n", h)
    h = re.sub(r"</(p|li|div|h\d)>", "\n", h)
    h = re.sub(r"<[^>]+>", " ", h)
    return re.sub(r"[ \t]+", " ", h.replace("&amp;", "&").replace("&nbsp;", " ")).strip()


def dedupe_key(co, ti):
    """THE repost key, shared by daily_sweep, ingest_harvest and dedupe_pool (2026-09-14). Three
    private copies had drifted: none collapsed whitespace, and the guest harvest cuts titles at 60
    chars while the authenticated harvest keeps 80, so a cross-source repost never matched (15
    duplicate groups found, e.g. one Sr Principal TPM req under two job IDs). The RAW title is cut
    at 60 chars BEFORE normalizing, mirroring exactly what the guest harvest stores, so an 80-char
    harvest title and its 60-char guest twin reduce to the same key (cutting after normalizing
    fails: punctuation removal shortens the guest title below 60)."""
    b = re.sub(r"[^a-z0-9 ]", "", (co or "").lower()).split()
    # digits are KEPT: "Project Manager - $33-49 per hour" and "$57-67 per hour" are different reqs
    # "&" reads as "and" (one employer posted "Enterprise Technology & AI" and "... and AI" for one req)
    t = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", (ti or "")[:60].lower().replace("&", " and "))).strip()
    return ((b[0] if b else ""), t)

def region_of(j):
    """US / EU for a pool row: the region field, else inferred from location (older rows carry none).
    Shared by sync_applied and board_gen_v2 so a repost match never crosses regions."""
    if not j:
        return None
    if j.get("region") in ("US", "EU"):
        return j["region"]
    loc = j.get("location") or ""
    if not loc:
        return None
    return "US" if re.search(r"United States|, [A-Z]{2}\b|\bUSA?\b", loc) else "EU"


def fetch_jd(job_id):
    p = os.path.join(JDD, job_id + ".txt")
    if os.path.exists(p):
        return open(p, encoding="utf8").read()
    h = get("https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/" + job_id)
    if not h:
        return None
    m = re.search(r'show-more-less-html__markup[^>]*>(.*?)</div>', h, re.S)
    desc = strip_tags(m.group(1)) if m else strip_tags(h)[:6000]
    ti = strip_tags((re.search(r"top-card-layout__title[^>]*>([^<]+)", h) or [None, ""])[1])
    txt = "TITLE: %s\nFETCHED: %s\n----\n%s" % (ti, datetime.date.today().isoformat(), desc[:9000])
    open(p, "w", encoding="utf8").write(txt)
    time.sleep(0.4)
    return txt


# ---- classifier, scorer and lane rules: ONE rule set for every path ----
# Every rule constant (WATCHLIST, BLOCK, AGG, GIG, GIG_T, STAFF, JUNIOR, DWALL, HCO, FWALL,
# EXTRA_FWALL, HARD_WALL_RX, OFFL, PRODUCT, DIRT, LANE, STRENGTHS, NEVER, HEALTHJD, LOCAL_MARKETS,
# LOCAL_TOKENS, the LANE_* regexes, the currency table and the J-axis vocabulary) is built from
# profile.json by configure() at the bottom of this file. Profile regexes are strings or lists of
# alternatives (joined with "|"), matched case-insensitively unless a comment says otherwise.
# An EMPTY list or string compiles to a regex that matches NOTHING, never to one that matches all.
#
# HARD WALLS - SINGLE SOURCE OF TRUTH. The classify walls and verify_board's invariant-C list once
# lived in two files and drifted (watchlist bypass; a missing "top secret"), which blocked the
# board. verify_board now IMPORTS HARD_WALL_RX from here; there is no second copy to drift.
# Semantics = invariant C: rows that are un-appliable no matter what (scoring.hardWallRegex).
#
# LOCAL-MARKET CARVE-OUT (search.localMarkets). Searches are remote-only by default; a local market
# is a named place where hybrid and/or onsite roles ARE acceptable (a commutable city). Everywhere
# else HYBRID/ONSITE stays disqualifying. Local rows carry MARKET TOKENS (CODE-HYB, CODE-ONSITE)
# instead of plain HYBRID/ONSITE, so the board keeps them, verify never flips their calls to SKIP,
# and the scorer does not treat "this is a hybrid role" as a location pin. A market may allow
# hybrid only: local_token returns None for onsite there.
_NOTHING = r"(?!x)x"


def _rx(value, flags=re.I):
    p = ppat(value)
    return re.compile(p if p else _NOTHING, flags)


def _lower_list(value):
    return [str(v).lower() for v in (value or []) if str(v)]


def local_market(row):
    """Market code when a row sits in a local market of ITS region where hybrid/onsite is allowed."""
    region = row.get("region") or "US"
    mine = [(mk, rx) for mk, rx in LOCAL_MARKETS if _LOCAL_REGION.get(mk) == region]
    if not mine:
        return None
    wp = (row.get("workplace") or "").upper()
    for mk, _ in mine:
        if wp.startswith(mk + "-"):
            return mk
    loc = row.get("location") or ""
    for mk, rx in mine:
        if rx.search(loc):
            return mk
    return None


def local_token(row, wt):
    """Verify-time token for a hybrid (wt=3) or onsite (wt=1) result; None if not local-allowed."""
    mk = local_market(row)
    if not mk:
        return None
    suffix = "ONSITE" if wt == 1 else "HYB"
    if suffix not in _LOCAL_ALLOWED.get(mk, ()):
        return None
    return "%s-%s" % (mk, suffix)


def classify(j):
    """One rule chain for every path. Returns (decision, reason)."""
    co, ti = (j.get("company") or "").lower(), j.get("title") or ""
    watch = any(w in co for w in WATCHLIST)
    # HARD WALLS BEFORE WATCHLIST (2026-09-09): invariant C is absolute - a clearance or
    # construction row is un-appliable no matter who posted it. The old order short-circuited
    # watchlist companies to TAILORED before any wall test, so a watchlist company's supply-chain
    # rows sat green until the board blocked. Watchlist guarantees VISIBILITY, not wall exemption: a
    # walled watchlist row keeps a WATCHLIST-tagged reason so the sweep report still names it.
    if HARD_WALL_RX.search(ti):
        return "SKIP", ("hard wall (WATCHLIST %s)" % co if watch else "hard wall")
    if watch: return "TAILORED", "WATCHLIST COMPANY"
    if any(b in co for b in BLOCK): return "SKIP", "blocklist"
    if any(a in co for a in AGG): return "SKIP", "aggregator"
    if any(g in co for g in GIG) or GIG_T.search(ti): return "SKIP", "gig funnel"
    if JUNIOR.search(ti): return "SKIP", "junior title"
    if HCO.search(co) or DWALL.search(ti): return "SKIP", DWALL_LABEL
    if FWALL.search(ti) or FWALL.search(co) or EXTRA_FWALL.search(ti): return "SKIP", "out-of-field"
    if OFFL.search(ti): return "SKIP", "off-lane"
    # (No applied-company rule: the tracker and board-state know what is applied, and
    # sync_applied.py stamps it per req. A hard-coded company list here went stale and was personal.)
    if DIRT.search(ti) and not LANE.search(ti): return "SKIP", "director outside lane"
    is_p = any(p in co for p in PRODUCT)
    senior = SENIOR_TITLE.search(ti)
    if is_p and senior: return "TAILORED", "product co, senior title"
    if is_p: return "GENERIC", "product co"
    if STAFF.search(j.get("company") or ""): return "GENERIC-B", "agency-shaped"
    return "GENERIC-B", "unknown co"


def evaluate(txt, watch=False, local=False):
    # watch=True (WATCHLIST company): hard-fails become a visible FLAG verdict,
    # never a silent PASS. The script does not make the call on the owner's named companies.
    # local=True (local market, see search.localMarkets): hybrid/onsite/location language is
    # allowed there, so the LOCATION pin is not a hard fail. Travel and comp checks still apply.
    low = txt.lower()
    why, score, hard = [], 0, []
    # "must reside in a state where <co> is registered" is any-state boilerplate, not a pin
    scrub = re.sub(r"resides? [^.\n]{0,40}state (where|in which)[^.\n]{0,60}(registered|does business|operates)", "", txt, flags=re.I)
    lp = None if local else LOCPIN.search(scrub)
    if lp:
        hard.append("LOCATION: " + re.sub(r"\s+", " ", lp.group(0))[:60])
    tr = re.search(r"travel[^.\n]{0,80}?(\d{1,3})\s*%", low)
    if tr and MAX_TRAVEL_PCT is not None and int(tr.group(1)) > MAX_TRAVEL_PCT:
        hard.append("travel %s%%" % tr.group(1))
    if TRAVEL_LANG.search(low):
        hard.append("travel: weekly/customer-site language")
    if HEALTHJD.search(low):
        hard.append(HEALTHJD_LABEL)
    m = re.search(r"\$\s?([\d,]+)(?:\.\d+)?\s*(?:-|to|–)\s*\$\s?([\d,]+)", txt)
    cr = None
    if m:
        lo, hi = int(m.group(1).replace(",", "")), int(m.group(2).replace(",", ""))
        if hi < 1000: lo, hi = lo * 1000, hi * 1000
        cr = (lo, hi)
        if USD_MIN_CEILING and hi < USD_MIN_CEILING:
            hard.append("comp ceiling $%dK" % (hi // 1000))
    if hard and not watch:
        return "PASS", "; ".join(hard)[:150], -99
    for name, pat in STRENGTHS.items():
        if re.search(pat, low):
            score += 2; why.append(name)
    walls = [n for n in NEVER if re.search(r"\b" + re.escape(n) + r"\b", low)]
    if walls:
        score -= 2 * len(walls); why.append("walls:" + ",".join(walls[:3]))
    pm = PPL_MGMT.search(low)
    if pm and int(pm.group(1)) >= PPL_MGMT_MIN_YEARS:
        score -= 3; why.append("ppl-mgmt %s+yr bar" % pm.group(1))
    if cr:
        for floor, pts in USD_BONUS:          # highest floor first; first match wins
            if cr[1] >= floor:
                score += pts
                break
        why.append("comp to $%dK" % (cr[1] // 1000))
    if hard:
        return "FLAG", "; ".join(hard + why)[:150], score
    v = "APPLY" if score >= APPLY_MIN else ("MAYBE" if score >= MAYBE_MIN else "PASS")
    return v, "; ".join(why)[:150], score


# ---- lane rule (scoring.laneRules): STRAT for senior titles, TAILORED rows, high comp and
# strategic-tier companies; TAC otherwise. One function, used by every path. ----
def stamp_lane(j):
    """Stamp TAC/STRAT on a live row. Callers skip SKIP/PASS/APPLIED rows themselves
    or rely on the guard here. Returns the lane or None."""
    if j.get("decision") == "SKIP" or j.get("verdict") == "PASS" or j.get("call") in ("APPLIED", "SKIP"):
        j.pop("lane", None)
        return None
    t = j.get("title") or ""
    comp_hi = bool(LANE_COMP_HI.search(j.get("comp") or ""))
    faang = LANE_FAANG.search(j.get("company") or "")
    j["lane"] = "STRAT" if (LANE_SENIOR.search(t) or j.get("decision") == "TAILORED" or comp_hi or faang
                            or (j.get("decision") == "GENERIC" and LANE_SENIORISH.search(t))) else "TAC"
    return j["lane"]


COMP_RANGE_RX = re.compile(
    r"\$\s*([\d]{2,3}(?:[,.]\d{3})*(?:\.\d+)?)\s*([kK])?\s*(?:-|\u2013|\u2014|\bto\b)\s*"
    r"\$?\s*([\d]{2,3}(?:[,.]\d{3})*(?:\.\d+)?)\s*([kK])?", re.U)
COMP_SINGLE_RX = re.compile(r"\$\s*([\d]{2,3}[,.]\d{3}(?:[,.]\d{3})?)(?!\s*[MB])", re.U)
# Non-USD bands (pay.currencies): ranges with space, dot or comma thousands ("80 000 - 120 000",
# "EUR 70.000 - 90.000"). A currency marker is REQUIRED on one side, so plain number ranges (user
# counts, headcount) never match. COMP_CUR_RX is compiled by configure() from the profile's markers
# and range separators (pay.rangeSeparators).
_AMT = r"(\d{1,3}(?:[ ., ]\d{3})+|\d{2,3}\s?[kK])"

def _cur_code(s):
    """The pay.currencies entry whose marker the matched text is, or None."""
    if not s:
        return None
    for cur in CURRENCIES:
        for mk in cur["markers"]:
            if re.fullmatch(mk, s, re.I):
                return cur
    return None

def comp_from_jd_nonusd(txt):
    """Currency-coded (non-USD) band from JD text, or None. A currency with a `monthly` rule is
    labelled /mo when monthly (a month word nearby, or a ceiling under the rule's `below` value:
    no annual salary in that currency is that low). Bands compete on annual EUR equivalents."""
    if COMP_CUR_RX is None:
        return None
    def amt(s):
        s = s.replace(" ", " ").strip()
        if s.lower().endswith("k"):
            return float(re.sub(r"[^\d]", "", s)) * 1000
        return float(re.sub(r"[ .,]", "", s))
    best, best_hi = None, 0
    for m in COMP_CUR_RX.finditer(txt or ""):
        cur = _cur_code(m.group(1)) or _cur_code(m.group(3)) or _cur_code(m.group(5))
        if not cur:
            continue
        lo, hi = amt(m.group(2)), amt(m.group(4))
        if not (lo <= hi) or hi < 1000:
            continue
        near = (txt or "")[m.end():m.end() + 40].lower() + (txt or "")[max(0, m.start() - 40):m.start()].lower()
        monthly = (cur["monthlyWords"] is not None or cur["monthlyBelow"] is not None) and (
            (cur["monthlyWords"] is not None and cur["monthlyWords"].search(near))
            or (cur["monthlyBelow"] is not None and hi < cur["monthlyBelow"]))
        eur_equiv = hi * (12 if monthly else 1) / cur["perEur"]
        if eur_equiv > best_hi:
            best = "%s %s - %s%s" % (cur["code"], "{:,.0f}".format(lo), "{:,.0f}".format(hi), " /mo" if monthly else "")
            best_hi = eur_equiv
    return best

def comp_from_jd(txt):
    """Mine the pay band out of JD TEXT. LinkedIn's structured comp field is usually empty
    while the band sits in the description, and board P-tags read the comp field, so without
    this real P1 rows rendered as P3. Returns a verbatim-style display string
    or None. Ranges preferred; the range with the highest ceiling wins; a lone salary-
    sized figure is the fallback. Never invents: only what the text states."""
    def val(num, k):
        s = num.replace(",", "")
        # European-style dots as thousands separators ("137.970.00", "121.500"):
        # multiple dots, or a single dot followed by exactly 3 digits, are separators.
        if s.count(".") > 1:
            s = s.replace(".", "")
        elif "." in s and len(s.split(".")[1]) == 3:
            s = s.replace(".", "")
        try:
            n = float(s)
        except ValueError:
            return 0
        return n * 1000 if (k or n < 1000) else n
    best, best_hi = None, 0
    for m in COMP_RANGE_RX.finditer(txt or ""):
        tail = (txt or "")[m.end():m.end() + 16].lower()
        if "hour" in tail or "/hr" in tail or " hr" in tail:
            # hourly band: keep it labelled hourly (never inflate to annual dollars);
            # ceiling compared on the annualized value so it can still win the pick.
            lo_h, hi_h = float(m.group(1).replace(",", "")), float(m.group(3).replace(",", ""))
            if 15 <= hi_h <= 400 and lo_h <= hi_h and hi_h * 2000 > best_hi:
                best, best_hi = "$%.2f - $%.2f /hr" % (lo_h, hi_h), hi_h * 2000
            continue
        lo, hi = val(m.group(1), m.group(2)), val(m.group(3), m.group(4))
        if 40000 <= hi <= 900000 and lo <= hi and hi > best_hi:
            best, best_hi = "$%s - $%s" % ("{:,.0f}".format(lo), "{:,.0f}".format(hi)), hi
    if best:
        return best
    singles = [val(m.group(1), None) for m in COMP_SINGLE_RX.finditer(txt or "")]
    singles = [s for s in singles if 40000 <= s <= 900000]
    if singles:
        return "$" + "{:,.0f}".format(max(singles))
    return comp_from_jd_nonusd(txt)


def enrich_from_harvest(row, ez_flag, workplace="REMOTE"):
    """Enrich an EXISTING pool row from an authenticated-harvest line (PIPELINE_SPEC 2026-09-08).
    easyApply: harvest is the ONLY source, so always stamp it. workplace: a row with NO workplace
    takes the harvest's own filter (REMOTE for remote searches, a local-market token such as
    CODE-HYB for local-market searches), but page-level verify truth (ONSITE/HYBRID/REMOTE) and GONE
    stamps are never overwritten."""
    row["easyApply"] = bool(ez_flag)
    if not row.get("workplace"):
        row["workplace"] = workplace
    return row


def score_rows(rows, watch_companies=None):
    """Score-at-birth (redesign step A1): fetch + evaluate EVERY row whose decision is
    not SKIP (GENERIC-B included), then stamp lanes and mine the comp band from the JD
    text when LinkedIn's structured field gave none. Returns counter dict."""
    watch_companies = watch_companies or WATCHLIST
    out = {"scored": 0, "no_jd": 0, "skipped": 0}
    for j in rows:
        if j.get("decision") == "SKIP":
            out["skipped"] += 1
            continue
        txt = fetch_jd(j["jobId"])
        if not txt:
            j["verdict"], j["why"] = "NO-JD", ""
            out["no_jd"] += 1
        else:
            v, why, sc = evaluate(txt, watch=any(w in (j.get("company") or "").lower() for w in watch_companies),
                                  local=bool(local_market(j)))
            j["verdict"], j["why"], j["score"] = v, why, sc
            if not j.get("comp"):
                band = comp_from_jd(txt)
                if band:
                    j["comp"] = band
            out["scored"] += 1
        stamp_lane(j)
    return out


# ---- J AXIS: how well the Career Bank covers what a JD asks for ----
# Purpose: sort jobs by how closely the bank matches what each JD is looking for, i.e. where an
# interview is most likely. Machine estimate from the JD text alone. No pool writes: the board
# computes it at render, so it never goes stale as the bank grows. Each requirement line is classified:
#   BLOCKED   a confirmed negative: the bank's never-claim registry, scoring.evaluate.neverClaim,
#             hard walls, a language you do not speak, a credential you do not hold, a degree-field
#             gate with no "or equivalent", or the years bar (scoring.jAxis.*)
#   COVERED   vocabulary your gate-passed builds already covered honestly (the ATS keyword file of
#             every build) or a strengths pattern; generic words need two hits to count
#   UNCOVERED neither
# Required lines weigh 1.0, preferred/nice-to-have lines 0.5. Tier thresholds (scoring.jAxis.tiers)
# are calibrated against builds whose true gaps are known (SOP "J axis").
#
# The JD-structure parsers below (section headers, end-of-requirements markers, boilerplate,
# requirement cues) are about how JDs are written, not about you, so they stay in code.
_J_VOCAB = None
_J_HDR = re.compile(r"^\W*((minimum|basic|required|preferred|desired|additional)\s+)?((qualifications?|requirements?|"
                    r"skills|experience)(\s*(&|and|/)\s*(qualifications?|requirements?|skills|experience))?)\W*$|"
                    r"^\W*(what you('| wi)ll (need|bring)|what you bring|what we('re| are) looking for|who you are|"
                    r"about you|your profile|you have|you bring|must[- ]haves?|nice[- ]to[- ]haves?|bonus points( for)?|"
                    r"preferred)\W*$", re.I)
_J_PREF = re.compile(r"preferred|desired|nice[- ]to[- ]have|bonus|additional", re.I)
_J_END = re.compile(r"^\W*(benefits|compensation|salary|pay (range|transparency)|perks|what we offer|about (us|the "
                    r"company|the team)|equal (employment )?opportunity|why join|our benefits|the (base )?pay range|"
                    r"how to apply|additional information|important notice|united states salary|salary range)\b", re.I)
# requirement-section lines that are policy boilerplate, not requirements (applicant notices,
# medical-screening lines, salary-range lines)
_J_BOILER = re.compile(r"applicants|salary range|pay range|equal opportunity|sponsorship|background check|"
                       r"drug (test|screen)|to verify|notice|e-verify|accommodation|great rewards|dental|401\(k\)|"
                       r"paid time off|eligible employee", re.I)
_J_EQUIV = re.compile(r"equivalent|or related|or similar|practical experience|or comparable", re.I)
_J_INLINE_PREF = re.compile(r"\b(preferred|a plus|nice to have|bonus|desirable|ideally)\b", re.I)
_J_CUE = re.compile(r"\b(experience|years|proficien\w*|familiar\w*|knowledge of|ability to|degree|certif\w*|fluen\w*|"
                    r"track record|expertise|background in|understanding of|hands-on)\b", re.I)
# Single common words match nearly every JD line ("requirements", "compliance", "security"), so a
# single-word vocabulary hit counts as SPECIFIC only when it is distinctive to your bank
# (scoring.jAxis.strongSingleWords). Multi-word terms ("dependency management", "launch readiness")
# stay specific. Calibration: a BSA/AML sanctions line once scored as covered because it contained
# the word "requirements".
#
# The bank's never-claim registry mixes three kinds of entry: SKILL/TECH negatives (Kafka, SOC 2,
# SAFe), OVERCLAIM wordings for your own resume ("built the data pipelines") and STYLE bans ("at the
# intersection of", "empower", "foster", "leveraged"). Only the first kind is a JD requirement you
# cannot meet; the other two appear constantly in JD prose and were marking coverable lines as gaps.
# Skill entries are product names / acronyms (uppercase inside the phrase, or a single capitalized
# token) plus a short list of lowercase skill phrases (scoring.jAxis.registryLowercaseSkills).


def _j_skill_phrase(ph):
    if ph.lower() in _J_REGISTRY_LOWER_SKILLS:
        return True
    if any(ch.isupper() for ch in ph[1:]):
        return True                               # SOC 2, DynamoDB, Six Sigma, AWS Glue, SPACE metrics
    return len(ph.split()) == 1 and ph[:1].isupper()   # Kafka, Redis, Bedrock (not "Reversed a declining...")


def _j_build_vocab(kw_lists, bank_text):
    """Cover vocabulary (every build's ATS keyword list) + blocker regexes (bank registry text).
    Pure function of its inputs, so the selftest can build a fixture vocabulary."""
    counts = {}
    for kws in kw_lists:
        try:
            for k in {str(x).strip().lower() for x in kws}:
                if 2 <= len(k) <= 40:
                    counts[k] = counts.get(k, 0) + 1
        except Exception:
            pass
    # CROSS-VALIDATED ONLY: a term must appear in 2+ builds' keyword files. Calibration found
    # single-build vocabulary scored a JD against its OWN build (one build's jargon made its own
    # JD a J1 despite four required gaps).
    terms = {k for k, c in counts.items() if c >= 2}
    registry = []
    try:
        for m in re.finditer(r"^\s*-\s*\U0001F6AB\s*`([^`]+)`", bank_text or "", re.M):
            ph = m.group(1).strip()
            if not _j_skill_phrase(ph):
                continue   # style or overclaim-wording ban: not a skill gap in a JD
            # product names and acronyms (SAFe, Bedrock, KMS) match case-sensitively so
            # "safe environment" or "the bedrock of our culture" never read as a gap
            flags = 0 if any(ch.isupper() for ch in ph) else re.I
            registry.append((ph, re.compile(r"(?<![A-Za-z])" + re.escape(ph) + r"(?![A-Za-z])", flags)))
    except Exception:
        pass
    alt = "|".join(re.escape(t) for t in sorted(terms, key=len, reverse=True))
    cover = re.compile(r"(?<![A-Za-z0-9])(" + alt + r")(?![A-Za-z0-9])", re.I) if alt else re.compile(r"(?!x)x")
    return {"cover": cover, "registry": registry, "n_terms": len(terms)}


def _j_vocab():
    """The J vocabulary from disk: resume-configs/*-kw.json + Career_Bank.md at the project root."""
    global _J_VOCAB
    if _J_VOCAB is not None:
        return _J_VOCAB
    import glob
    ws = os.path.dirname(HERE)
    kw_lists = []
    for p in glob.glob(os.path.join(ws, "resume-configs", "*-kw.json")):
        try:
            kw_lists.append(json.load(open(p, encoding="utf8")))
        except Exception:
            pass
    try:
        bank = open(os.path.join(os.path.dirname(ws), "Career_Bank.md"), encoding="utf8").read()
    except Exception:
        bank = ""
    _J_VOCAB = _j_build_vocab(kw_lists, bank)
    return _J_VOCAB


def _j_block(s, v):
    held_alt = _J_CRED_HELD.search(s) or _J_EQUIV.search(s)
    for ph, rx in v["registry"]:
        if rx.search(s):
            if ph in _J_CRED_PHRASES and held_alt:
                continue   # "PMP, PgMP, CSM or SAFe" is an alternatives list met by a credential held
            return ph
    low = s.lower()
    for n in NEVER:
        if re.search(r"\b" + re.escape(n) + r"\b", low):
            return n
    m = HARD_WALL_RX.search(s) or HEALTHJD.search(s)
    if m and _J_CUE.search(s):   # a domain REQUIREMENT, not a medical-screening or site-policy sentence
        return m.group(0).lower()
    dg = _J_DOMAIN_GAP.search(s)
    if dg:
        return "domain: " + dg.group(0).lower()
    if _J_LANG.search(s):
        return "language: " + re.search(r"\b(" + _J_LANG_NOT + r")\b", s, re.I).group(1).lower()
    c = _J_CRED.search(s)
    if c and not _J_CRED_HELD.search(s):
        return "credential: " + c.group(1).upper()
    d = _J_DEGREE.search(s)
    if d and not _J_EQUIV.search(s):
        return "degree: " + d.group("field").lower()
    if _J_YEARS.search(s):
        return _J_YEARS_LABEL
    return None


def jd_match(txt):
    """J axis for one JD: {score 0-100, tier J1/J2/J3, n, blockers, misses} or None (no JD)."""
    if not txt:
        return None
    v = _j_vocab()
    lines = [l.strip().strip("-•*·▪● ").strip() for l in txt.split("\n")]
    reqs, mode = [], None
    for s in lines:
        if not s:
            continue
        if len(s) < 60 and _J_HDR.match(s):
            mode = 0.5 if _J_PREF.search(s) else 1.0
            continue
        if len(s) < 60 and _J_END.match(s):
            mode = None
            continue
        if mode and len(s) >= 15 and not _J_BOILER.search(s):
            reqs.append((s, 0.5 if (mode == 1.0 and _J_INLINE_PREF.search(s)) else mode))
    if len(reqs) < 3:   # headerless JD: fall back to requirement-cue lines anywhere
        reqs = [(s, 0.5 if _J_INLINE_PREF.search(s) else 1.0) for s in lines
                if len(s) >= 20 and _J_CUE.search(s) and not _J_BOILER.search(s)]
    if not reqs:
        return None
    tot = cov = 0.0
    blocked, misses = [], []
    for s, w in reqs[:40]:
        tot += w
        b = _j_block(s, v)
        if b:
            blocked.append((w, b))
            continue
        hits = {m.group(0).lower() for m in v["cover"].finditer(s)}
        specific = [h for h in hits if h not in _J_GENERIC and (" " in h or "-" in h or h in _J_STRONG_SINGLE)]
        strength = any(re.search(p, s.lower()) for p in STRENGTHS.values())
        if specific or strength:
            cov += w
        elif hits:
            cov += w * 0.5          # generic PM vocabulary only: half credit
            misses.append((w * 0.5, s[:60]))
        else:
            misses.append((w, s[:60]))
    score = round(100 * cov / tot) if tot else 0
    req_blocks = sum(1 for w, _ in blocked if w == 1.0)
    if score >= J1_MIN and req_blocks == 0:
        tier = "J1"
    elif score >= J2_MIN and req_blocks <= 1:
        tier = "J2"
    else:
        tier = "J3"
    seen, blockers = set(), []
    for _, b in blocked:
        if b not in seen:
            seen.add(b)
            blockers.append(b)
    return {"score": score, "tier": tier, "n": len(reqs), "blockers": blockers[:3],
            "misses": [m for _, m in sorted(misses, key=lambda x: -x[0])][:2]}


# ---- profile -> rules ----
_WORKPLACE_SUFFIX = {"hybrid": "HYB", "hyb": "HYB", "onsite": "ONSITE", "on-site": "ONSITE"}


def configure(profile):
    """(Re)build every profile-driven rule. Called once at import with profile.json;
    pipeline_selftest.py calls it with fixture profiles and restores the real one after."""
    global PROFILE, WATCHLIST, BLOCK, AGG, GIG, GIG_T, STAFF, JUNIOR, DWALL, HCO, DWALL_LABEL
    global FWALL, EXTRA_FWALL, HARD_WALL_RX, OFFL, PRODUCT, DIRT, LANE, SENIOR_TITLE
    global LOCAL_MARKETS, LOCAL_TOKENS, _LOCAL_ALLOWED, _LOCAL_REGION
    global LOCPIN, MAX_TRAVEL_PCT, TRAVEL_LANG, HEALTHJD, HEALTHJD_LABEL, STRENGTHS, NEVER
    global PPL_MGMT, PPL_MGMT_MIN_YEARS, APPLY_MIN, MAYBE_MIN, USD_MIN_CEILING, USD_BONUS
    global LANE_SENIOR, LANE_SENIORISH, LANE_COMP_HI, LANE_FAANG, CURRENCIES, COMP_CUR_RX
    global J1_MIN, J2_MIN, _J_GENERIC, _J_STRONG_SINGLE, _J_LANG_NOT, _J_LANG, _J_CRED, _J_CRED_HELD
    global _J_DEGREE, _J_YEARS, _J_YEARS_LABEL, _J_DOMAIN_GAP, _J_REGISTRY_LOWER_SKILLS, _J_CRED_PHRASES, _J_VOCAB
    PROFILE = profile

    def g(path, default=None):
        v = pget(profile, path, default)
        return default if v is None else v

    # classify (scoring.classify + scoring.hardWallRegex)
    WATCHLIST = _lower_list(g("scoring.classify.watchlist"))   # always surfaces: TAILORED + evaluated + named
    BLOCK = _lower_list(g("scoring.classify.blocklist"))
    AGG = _lower_list(g("scoring.classify.aggregators"))
    GIG = _lower_list(g("scoring.classify.gigCompanies"))
    GIG_T = _rx(g("scoring.classify.gigTitleRegex"))
    STAFF = _rx(g("scoring.classify.agencyCompanyRegex"))
    JUNIOR = _rx(g("scoring.classify.juniorTitleRegex"))
    DWALL = _rx(g("scoring.classify.domainWall.titleRegex"))
    HCO = _rx(g("scoring.classify.domainWall.companyRegex"))
    DWALL_LABEL = str(g("scoring.classify.domainWall.label", "domain wall"))
    FWALL = _rx(g("scoring.classify.outOfFieldRegex"))
    EXTRA_FWALL = _rx(g("scoring.classify.outOfFieldTitleRegex"))
    HARD_WALL_RX = _rx(g("scoring.hardWallRegex"))
    OFFL = _rx(g("scoring.classify.offLaneTitleRegex"))
    PRODUCT = _lower_list(g("scoring.classify.productCompanies"))
    DIRT = _rx(g("scoring.classify.directorTitleRegex"))
    LANE = _rx(g("scoring.classify.inLaneTitleRegex"))
    SENIOR_TITLE = _rx(g("scoring.classify.seniorTitleRegex"))

    # local markets (search.localMarkets)
    LOCAL_MARKETS, toks, _LOCAL_ALLOWED, _LOCAL_REGION = [], [], {}, {}
    for m in g("search.localMarkets", []):
        if not isinstance(m, dict) or not m.get("code"):
            continue
        code = str(m["code"]).upper()
        allowed = [_WORKPLACE_SUFFIX.get(str(w).lower(), str(w).upper()) for w in (m.get("workplaces") or ["hybrid"])]
        LOCAL_MARKETS.append((code, _rx(m.get("locationRegex"))))
        _LOCAL_ALLOWED[code] = tuple(allowed)
        _LOCAL_REGION[code] = str(m.get("region") or "EU")
        toks += ["%s-%s" % (code, w) for w in allowed]
    LOCAL_TOKENS = tuple(toks)

    # evaluate (scoring.evaluate + pay.usd)
    LOCPIN = _rx(g("scoring.evaluate.locationPinRegex"))
    MAX_TRAVEL_PCT = pget(profile, "scoring.evaluate.maxTravelPct", 20)
    TRAVEL_LANG = _rx(g("scoring.evaluate.travelLanguageRegex"))
    HEALTHJD = _rx(g("scoring.evaluate.domainJdRegex"))
    HEALTHJD_LABEL = str(g("scoring.evaluate.domainJdLabel", "domain JD content"))
    STRENGTHS = {k: ppat(v) for k, v in g("scoring.evaluate.strengths", {}).items()
                 if not str(k).startswith("_") and ppat(v)}
    NEVER = _lower_list(g("scoring.evaluate.neverClaim"))
    PPL_MGMT = _rx(g("scoring.evaluate.peopleMgmtRegex"))
    PPL_MGMT_MIN_YEARS = int(g("scoring.evaluate.peopleMgmtMinYears", 5))
    APPLY_MIN = g("scoring.evaluate.applyMinScore", 9)
    MAYBE_MIN = g("scoring.evaluate.maybeMinScore", 5)
    USD_MIN_CEILING = pget(profile, "pay.usd.minCeiling", 120000)
    USD_BONUS = sorted(([int(a), int(b)] for a, b in g("pay.usd.scoreBonus", [[200000, 2], [160000, 1]])),
                       key=lambda x: -x[0])

    # lanes (scoring.laneRules); highCompRegex is CASE-SENSITIVE (it reads "190K", not "190k")
    LANE_SENIOR = _rx(g("scoring.laneRules.strategicTitleRegex"))
    LANE_SENIORISH = _rx(g("scoring.laneRules.seniorishTitleRegex"))
    LANE_COMP_HI = _rx(g("scoring.laneRules.highCompRegex"), 0)
    LANE_FAANG = _rx(g("scoring.laneRules.strategicCompanyRegex"))

    # non-USD comp mining (pay.currencies, pay.rangeSeparators)
    CURRENCIES = []
    for cdef in g("pay.currencies", []):
        if not isinstance(cdef, dict) or not cdef.get("code"):
            continue
        code = str(cdef["code"]).upper()
        markers = [str(x) for x in (cdef.get("markers") or [code]) if str(x)]
        mo = cdef.get("monthly") or {}
        CURRENCIES.append({
            "code": code, "markers": markers,
            "perEur": float(cdef.get("perEur") or 1),
            "monthlyWords": re.compile(mo["words"], re.I) if mo.get("words") else None,
            "monthlyBelow": mo.get("below"),
            "boardMatch": cdef.get("boardMatch") or "|".join(markers)})
    if CURRENCIES:
        cur = "(" + "|".join(mk for c in CURRENCIES for mk in c["markers"]) + ")"
        seps = ppat(g("pay.rangeSeparators"), r"-|\u2013|\u2014|\bto\b")
        COMP_CUR_RX = re.compile(cur + r"?\s*" + _AMT + r"\s*(?:" + seps + r")\s*" + cur + r"?\s*" + _AMT
                                 + r"\s*" + cur + r"?", re.I)
    else:
        COMP_CUR_RX = None

    # J axis (scoring.jAxis)
    J1_MIN = g("scoring.jAxis.tiers.J1", 70)
    J2_MIN = g("scoring.jAxis.tiers.J2", 50)
    _J_GENERIC = set(_lower_list(g("scoring.jAxis.genericWords")))
    _J_STRONG_SINGLE = set(_lower_list(g("scoring.jAxis.strongSingleWords")))
    _J_LANG_NOT = ppat(g("scoring.jAxis.languagesNotSpoken"))
    _J_LANG = re.compile(r"\b(fluen\w*|native|proficien\w*|business[- ]level|written and spoken|c1|c2|b2)\b[^.\n]{0,40}\b("
                         + _J_LANG_NOT + r")\b|\b(" + _J_LANG_NOT
                         + r")\b[^.\n]{0,25}\b(fluen\w*|required|native|proficien\w*|speaking|language skills|c1|c2|b2)\b",
                         re.I) if _J_LANG_NOT else re.compile(_NOTHING)
    _cred = ppat(g("scoring.jAxis.credentialsRequiredNotHeld"))
    _J_CRED = re.compile(r"\b(" + _cred + r")\b", re.I) if _cred else re.compile(_NOTHING)
    _held = ppat(g("scoring.jAxis.credentialsHeld"))
    _J_CRED_HELD = re.compile(r"\b(" + _held + r")\b", re.I) if _held else re.compile(_NOTHING)
    _fields = ppat(g("scoring.jAxis.degreeFieldsLacking"))
    _J_DEGREE = re.compile(r"\b(bachelor\w*|master\w*|degree|b\.?s\.?|m\.?s\.?|phd)\b[^.\n]{0,60}\b(?P<field>"
                           + _fields + r")\b", re.I) if _fields else re.compile(r"(?P<field>(?!x)x)")
    _J_YEARS = _rx(g("scoring.jAxis.yearsBarRegex"))
    _J_YEARS_LABEL = str(g("scoring.jAxis.yearsBarLabel", "years bar"))
    _J_DOMAIN_GAP = _rx(g("scoring.jAxis.domainGaps"))
    _J_REGISTRY_LOWER_SKILLS = set(_lower_list(g("scoring.jAxis.registryLowercaseSkills")))
    _J_CRED_PHRASES = set(str(x) for x in g("scoring.jAxis.registryCredentialPhrases", []))
    _J_VOCAB = None   # registry classification depends on the lists above


configure(load_profile(HERE))
