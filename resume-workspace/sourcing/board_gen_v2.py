# -*- coding: utf-8 -*-
"""V2 board. Writes job-board-v2.html (Board_Spec.md is the contract; verify_board.py gates it).
Design: action views with decision columns; audit views with evidence columns; one state per row.
Everything personal (lane resume files, the file-name prefix, pay tiers, local markets, currencies,
the page title, the staffing-flag list) comes from profile.json."""
import json, html, datetime, io, sys, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

SRC = json.load(open("resume-workspace/sourcing/sourced-jobs.json", encoding="utf8"))
try:
    RUN = json.load(open("resume-workspace/sourcing/easyapply-run.json", encoding="utf8"))
    APPLIED_IDS = {a["id"] for a in RUN.get("applied", [])}
    for k, v in RUN.items():
        if k.startswith("day") and isinstance(v, dict):
            APPLIED_IDS |= {a["id"] for a in v.get("applied", [])}
except Exception:
    APPLIED_IDS = set()
try:
    ST = json.load(open("resume-workspace/sourcing/board-state.json", encoding="utf8"))
    APPLIED_IDS |= set(ST.get("applied", []))
    TOSSED_IDS = set(ST.get("tossed", []))
except Exception:
    TOSSED_IDS = set()

# Tracker match by key = the shared repost key AND the tracked req's region: a private 25-letter
# any-region key once rendered different open reqs as APPLIED (a closed US req under an unrelated EU
# application; nine different TPM teams of one employer under a single application).
sys.path.insert(0, "resume-workspace/sourcing")
from sweep_lib import dedupe_key, region_of
from sweep_lib import PROFILE, LOCAL_TOKENS, CURRENCIES
from profile_lib import get as pget
_SRC_BY_ID = {str(j["jobId"]): j for j in SRC}
_TRK_RANK = {"applied": 0, "built-unsent": 1, "closed-before-apply": 2}
TRK_BY_ID, TRK_BY_KEY = {}, {}
try:
    for r in json.load(open("resume-workspace/roles.tracked.json", encoding="utf8")):
        st_ = r.get("status") or ""
        res = (r.get("output") or {}).get("resume", "")
        ids = []
        for u in (r.get("urls") or {}).values() if isinstance(r.get("urls"), dict) else []:
            m = re.search(r"/jobs/view/(\d+)", str(u))
            if m:
                TRK_BY_ID[m.group(1)] = (st_, res)
                ids.append(m.group(1))
        if r.get("id"):
            m = re.search(r"(\d{9,})", str(r["id"]))
            if m: TRK_BY_ID[m.group(1)] = (st_, res)
        regs = {region_of(_SRC_BY_ID.get(i)) for i in ids} - {None}
        TRK_BY_KEY.setdefault(dedupe_key(r.get("company"), r.get("title")), []).append((st_, res, regs))
except Exception:
    pass
def trk(j):
    hit = TRK_BY_ID.get(str(j["jobId"]))
    if hit: return hit
    best = None
    for st_, res, regs in TRK_BY_KEY.get(dedupe_key(j.get("company"), j.get("title")), []):
        if (not regs or region_of(j) in regs) and (best is None or _TRK_RANK.get(st_, 9) < _TRK_RANK.get(best[0], 9)):
            best = (st_, res)
    return best

# Lane resume files (profile lanes.TAC / lanes.STRAT generalResume): the General each lane fires.
LANE_FILE = {k: pget(PROFILE, "lanes.%s.generalResume" % k, "") for k in ("TAC", "STRAT")}
# A built resume named in a call's why: <person.fileNamePrefix>_<anything>.docx
_PREFIX = pget(PROFILE, "person.fileNamePrefix", "") or pget(PROFILE, "person.filePrefix", "") or ""
RESUME_RX = re.compile(r"(" + (re.escape(_PREFIX) + r"_" if _PREFIX else "") + r"[\w\-]+\.docx)")
# STAFF flag (owner request: do real companies first, then contractors and staffing agencies):
# consulting firms, staffing/recruiting agencies, and job-board reposters (board.staffingFlagRegex)
# get an informational tag and sort AFTER real companies inside every view.
# Never changes calls, lanes, or states; purely presentation.
_staff = pget(PROFILE, "board.staffingFlagRegex", "")
STAFF_RX = re.compile("|".join(_staff) if isinstance(_staff, list) else (_staff or r"(?!x)x"), re.I)
def is_staff(j): return bool(STAFF_RX.search(j.get("company") or ""))
def esc(s): return html.escape(str(s or ""))

def state_of(j):
    """One state per row. Priority: applied/closed > built > my call > machine."""
    ts = trk(j)
    if j["jobId"] in APPLIED_IDS or (ts and ts[0] == "applied"): return "APPLIED", (ts[1] if ts else "")
    if (ts and ts[0] == "closed-before-apply") or (j.get("workplace") or "") == "GONE": return "CLOSED", ""
    if ts and ts[0] == "built-unsent": return "SEND", ts[1] or "resume built"
    c = j.get("call") or ""
    if c in ("NEEDS-YOU", "VERIFY"):
        m = RESUME_RX.search(j.get("callWhy") or "")
        return "SEND", (m.group(1) if m else "see WHY")
    if c == "TAILOR": return "TAILOR", "tailor first (or %s)" % LANE_FILE.get(j.get("lane") or "STRAT")
    if c == "MAYBE": return "MAYBE", LANE_FILE.get(j.get("lane") or "TAC")
    if c == "GENERIC":
        m = RESUME_RX.search(j.get("callWhy") or "")
        return "GENERAL", (m.group(1) if m else LANE_FILE.get(j.get("lane") or "TAC"))
    if c == "SKIP": return "MYSKIP", ""
    if j.get("decision") == "SKIP" or j.get("verdict") == "PASS": return "MYSKIP", ""
    if not j.get("verdict"): return "UNSCORED", ""
    return "QUEUE", ""

# Currencies that need conversion before tiering (pay.currencies with perEur != 1 or a monthly
# rule), in profile order. EUR/GBP-style currencies tier "as posted" and take the plain path.
CONVERTED = [cur for cur in CURRENCIES if cur["perEur"] != 1 or cur["monthlyBelow"] is not None
             or cur["monthlyWords"] is not None]

def comp_key(comp):
    c = comp or ""
    # Converted-currency bands tier and sort as EUR-annual equivalents at the profile's perEur
    # rate; monthly bands x12. Display stays as posted. The EU tier thresholds are "EUR/GBP as
    # posted" (SOP), so a raw 120,000/month band in a weak currency must never read as a 120K P1.
    for cur in CONVERTED:
        if not re.search(cur["boardMatch"], c, re.I):
            continue
        vals = [float(x.replace(",", "")) for x in re.findall(r"(\d[\d,]*)", c)]
        if not vals:
            return 0
        hi = max(vals)
        below = cur["monthlyBelow"]
        return round(hi * (12 if ("/mo" in c or (below is not None and hi < below)) else 1) / cur["perEur"])
    nums = [float(x.replace(",", "")) for x in re.findall(r"\$?([\d][\d,]*(?:\.\d+)?)", c)]
    # Hourly bands ANNUALIZE for decisions (P-tags, sort) at the SOP's 2,000 hours while the
    # display stays /hr: before this, $95-102/hr ($190-204K) and $119-124.75/hr ($238-249K)
    # contracts rendered as P3.
    if re.search(r"/\s*hr|hour", c, re.I):
        hourly = [n * 2000 for n in nums if n < 1000]
        return max(hourly) if hourly else 0
    nums = [n * 1000 if n < 1000 else n for n in nums]
    return max(nums) if nums else 0

# P/J/M AXES: P = pay tier (pay.tiers), J = bank-vs-JD requirement match (computed here from
# the JD text so it never goes stale), M = mission (reader judgment stamped on the row, or on the
# tracker entry for pool-less builds). Sort buttons reorder any view by pay / fit / mission / overlap.
import os as _os, sys as _sys
_sys.path.insert(0, "resume-workspace/sourcing")
try:
    from sweep_lib import jd_match as _jd_match
except Exception:
    _jd_match = None
J_STATES = ("SEND", "TAILOR", "MAYBE", "GENERAL", "EZ", "QUEUE")
# P tiers per region (pay.tiers): p1 = send first, p2 = good, below p2 = p3. A region without its own
# tiers uses the US ones.
TIERS = {k: v for k, v in (pget(PROFILE, "pay.tiers", {}) or {}).items() if isinstance(v, dict)}

rows = []
for j in SRC:
    if j["jobId"] in TOSSED_IDS: continue
    w = (j.get("workplace") or "").upper()
    stt, resume = state_of(j)
    if (w.startswith("ONSITE") or w.startswith("HYBRID")) and stt not in ("SEND",): continue
    if j.get("easyApply") and stt in ("MAYBE", "GENERAL"): stt = "EZ"
    rows.append((j, stt, resume))

# SYNTHETIC SEND ROWS (owner request: built roles must be workable from the board one by one):
# built-unsent roles sourced outside the harvest pipeline (one-off URLs, email reqs) have no pool
# row, so built resumes were INVISIBLE on the board. The board is THE tracker (owner rule): every
# built-unsent resume renders in SEND BUILT regardless of source. Pool-backed roles are skipped
# here (their pool row already shows).
_pool_ids = {str(j["jobId"]) for j, _, _ in rows}
try:
    for r in json.load(open("resume-workspace/roles.tracked.json", encoding="utf8")):
        if (r.get("status") or "") != "built-unsent": continue
        res = (r.get("output") or {}).get("resume", "")
        if not res: continue
        u = str((r.get("urls") or {}).get("job", ""))
        m = re.search(r"/jobs/view/([\w-]+)", u)
        jid = m.group(1) if m else "trk-" + re.sub(r"[^a-z0-9]", "", (r.get("company") or "x").lower())[:16]
        if jid in _pool_ids: continue
        if jid in APPLIED_IDS: continue
        note = str(r.get("note") or "")
        comp = str(r.get("comp") or "")
        region = "EU" if ("EU" in comp or "EU" in note[:300]
                          or any(cur["code"] in comp for cur in CURRENCIES) and "$" not in comp) else "US"
        synth = {"jobId": jid, "title": r.get("title") or "", "company": r.get("company") or "",
                 "comp": comp, "region": region, "workplace": "REMOTE",
                 "callWhy": "BUILT (no pool row - one-off build). " + note[:220],
                 "mission": r.get("mission") or "",
                 "url": u if u.startswith("http") else ""}
        rows.append((synth, "SEND", res))
        _pool_ids.add(jid)
except Exception:
    pass

ORDER = {"SEND": 0, "TAILOR": 1, "MAYBE": 2, "GENERAL": 3, "EZ": 4, "QUEUE": 5, "UNSCORED": 6, "MYSKIP": 7, "APPLIED": 8, "CLOSED": 9}
rows.sort(key=lambda x: (ORDER.get(x[1], 9), 1 if is_staff(x[0]) else 0, -(1 if x[0].get("easyApply") else 0), -comp_key(x[0].get("comp")), x[0].get("company") or ""))

counts = {}
for _, stt, _r in rows: counts[stt] = counts.get(stt, 0) + 1

body = []
for _i, (j, stt, resume) in enumerate(rows):
    why = j.get("callWhy") or ""
    if stt in ("UNSCORED", "QUEUE"): why = j.get("why") or ""
    ez = '<span class="tag ez">EASY</span>' if j.get("easyApply") else ""
    if is_staff(j): ez += '<span class="tag st">STAFF</span>'
    _wp = (j.get("workplace") or "").upper()
    if _wp in LOCAL_TOKENS:
        ez += '<span class="tag lc">%s</span>' % esc(_wp.replace("-HYB", " HYBRID").replace("-", " "))
    _pn, _jd, _mn = 9, None, 0
    if stt in ("SEND", "TAILOR"):
        _c = comp_key(j.get("comp"))
        _tier = TIERS.get(j.get("region")) or TIERS.get("US") or {}
        _t = "p1" if _c >= _tier.get("p1", 0) else ("p2" if _c >= _tier.get("p2", 0) else "p3")
        ez += '<span class="tag %s">%s</span>' % (_t, _t.upper())
        _pn = int(_t[1])
    if _jd_match and stt in J_STATES:
        _jp = "resume-workspace/sourcing/jds/%s.txt" % j["jobId"]
        if _os.path.exists(_jp):
            _jd = _jd_match(open(_jp, encoding="utf8", errors="replace").read())
        if _jd:
            _tip = "%d%% of requirements matched" % _jd["score"]
            if _jd["blockers"]:
                _tip += "; gaps: " + ", ".join(_jd["blockers"])
            if _jd["misses"]:
                _tip += "; unmatched: " + " / ".join(_jd["misses"])
            ez += '<span class="tag %s" title="%s">%s</span>' % (_jd["tier"].lower(), esc(_tip), _jd["tier"])
    if j.get("mission"):
        _mn = 1
        ez += '<span class="tag mi" title="%s">M</span>' % esc(j.get("mission"))
    _best = (1 if _pn == 1 else 0) + (1 if (_jd and _jd["tier"] == "J1") else 0) + _mn
    q = ((j.get("company") or "") + " " + (j.get("title") or "") + " " + why).lower()
    body.append(
        '<tr data-s="%s" data-rg="%s" data-q="%s" data-c="%s" data-j="%s" data-m="%d" data-b="%d" data-i="%d">'
        '<td><input type="checkbox" class="ap" data-id="%s" title="applied"></td>'
        '<td><input type="checkbox" class="tx" data-id="%s" title="toss"></td>'
        '<td><input type="checkbox" class="cl" data-id="%s" title="no longer accepting"></td>'
        '<td><a href="%s" target="_blank">%s</a></td>'
        '<td>%s</td><td>%s %s</td>'
        '<td class="rs">%s</td><td class="fl">%s</td>'
        '<td class="aud">%s</td><td class="aud">%s</td><td class="aud">%s</td><td class="aud">%s</td></tr>'
        % (stt, esc(j.get("region", "US")), esc(q[:300]), comp_key(j.get("comp")),
           (_jd["score"] if _jd else -1), _mn, _best, _i,
           esc(j["jobId"]), esc(j["jobId"]), esc(j["jobId"]),
           esc(j.get("url", "")), esc((j.get("title") or "")[:70]),
           esc((j.get("company") or "")[:28]), esc((j.get("comp") or "")[:22]), ez,
           esc(resume), esc(why[:230]),
           esc(j.get("decision", "")), esc(j.get("verdict", "") or "-"), esc("" if j.get("score") is None else j.get("score")), esc((j.get("workplace") or "")[:12])))

VIEWS = [("SEND", "SEND BUILT"), ("TAILOR", "TO TAILOR"), ("MAYBE", "MAYBE"), ("GENERAL", "GENERAL"),
         ("EZ", "EZ QUEUE"), ("QUEUE", "QUEUE"), ("UNSCORED", "UNSCORED"), ("MYSKIP", "MY SKIPS"), ("APPLIED", "APPLIED"), ("ALL", "ALL")]
PRIMARY = ("SEND", "TAILOR", "MAYBE", "GENERAL")
def _btn(k, label):
    return '<button onclick="fv(\'%s\')" id="v-%s">%s (%s)</button>' % (
        k, k, label, counts.get(k, 0) if k != "ALL" else len(rows))
btns = "".join(_btn(k, label) for k, label in VIEWS if k in PRIMARY)
btns += '<button onclick="ta()" id="audit-toggle" style="opacity:.55">audit &#9656;</button>'
btns += ('<span id="audit-btns" style="display:none">'
         + "".join(_btn(k, label) for k, label in VIEWS if k not in PRIMARY) + '</span>')
start = "SEND" if counts.get("SEND") else "TAILOR"

# Routine-run status line: the scheduled sweep's last run shows on the dashboard itself
def routine_line():
    bits = []
    try:
        batches = json.load(open("resume-workspace/sourcing/batches.json", encoding="utf8"))
        batches = {k: v for k, v in batches.items() if isinstance(v, dict)}
        key = sorted(batches, key=lambda k: str(batches[k].get("harvested") or ""))[-1]
        b = batches[key]
        bits.append("last sweep: <b>%s</b> (%s, %d keywords, %s %s)" % (
            esc(key), esc(b.get("harvested") or "?"), len(b.get("keywords") or []),
            esc(b.get("region") or "?"), esc(b.get("workplace") or "?")))
    except Exception:
        bits.append("last sweep: unknown")
    try:
        st2 = json.load(open("resume-workspace/sourcing/board-state.json", encoding="utf8"))
        if st2.get("ticksImport"):
            bits.append("ticks imported: %s" % esc(str(st2["ticksImport"])[:60]))
        if st2.get("watch"):
            bits.append("watching %d closed role(s) for reopen" % len(st2["watch"]))
    except Exception:
        pass
    # measured scoreboard (redesign 2026-09-03: the numbers the sweep is judged by)
    try:
        unscored = sum(1 for j in SRC if j["jobId"] not in APPLIED_IDS and j["jobId"] not in TOSSED_IDS
                       and j.get("decision") != "SKIP" and j.get("call") not in ("APPLIED", "SKIP")
                       and (j.get("workplace") or "") != "GONE" and not j.get("verdict"))
        ez_saved = sum(1 for j in SRC if j.get("savedToLinkedIn") and j.get("easyApply"))
        bits.append("<b>UNSCORED live: %d (must be 0)</b>" % unscored)
        bits.append("EZ saved on LinkedIn: %d" % ez_saved)
    except Exception:
        pass
    return " &middot; ".join(bits)
ROUTINE = routine_line()

# Legend pieces that depend on the profile.
_us = TIERS.get("US") or {}
P_LEGEND = ("<b>P1</b> (send first, $%dK+), P2 ($%d-%dK), P3 (hook/low or unstated comp)"
            % (_us.get("p1", 0) // 1000, _us.get("p2", 0) // 1000, _us.get("p1", 0) // 1000)) if _us else \
           "<b>P1</b> / P2 / P3 by pay.tiers"
_mk_both = [t.rsplit("-", 1)[0] for t in LOCAL_TOKENS if t.endswith("-ONSITE") and t.rsplit("-", 1)[0] + "-HYB" in LOCAL_TOKENS]
_mk_hyb = [t.rsplit("-", 1)[0] for t in LOCAL_TOKENS if t.endswith("-HYB")]
if _mk_both:
    LOCAL_LEGEND = ("<b>%s HYBRID or ONSITE</b> = local-market rows, where hybrid and onsite are allowed. "
                    % " / ".join(_mk_both))
elif _mk_hyb:
    LOCAL_LEGEND = "<b>%s HYBRID</b> = local-market rows, where hybrid is allowed. " % " / ".join(_mk_hyb)
else:
    LOCAL_LEGEND = ""
BOARD_TITLE = pget(PROFILE, "board.title", "Job Board") or "Job Board"

doc = """<!doctype html><html><head><meta charset="utf-8"><title>%s %s</title><style>
body{font-family:Segoe UI,Arial,sans-serif;margin:16px;background:#111;color:#ddd}
h1{font-size:18px} .sub{color:#888;font-size:12px;margin-bottom:10px}
button{margin:2px;padding:4px 10px;border:1px solid #444;background:#222;color:#ccc;cursor:pointer;border-radius:4px}
button.on{background:#2d6cdf;color:#fff;border-color:#2d6cdf}
input[type=text]{width:320px;padding:5px;background:#1a1a1a;border:1px solid #444;color:#eee;border-radius:4px}
table{border-collapse:collapse;width:100%%;margin-top:10px;font-size:12.5px}
th,td{border-bottom:1px solid #2a2a2a;padding:5px 7px;text-align:left;vertical-align:top}
th{position:sticky;top:0;background:#181818}
a{color:#7ab7ff;text-decoration:none} a:hover{text-decoration:underline}
.tag{padding:1px 7px;border-radius:8px;font-size:11px;white-space:nowrap}
.ez{background:#2d6cdf;color:#fff}
.st{background:#6b3fa0;color:#eee}
.lc{background:#8a6a1f;color:#fff}
.j1{background:#1f7a4a;color:#fff}.j2{background:#3d5a44;color:#ddd}.j3{background:#333;color:#999}
.mi{background:#1f5f8b;color:#fff}
.p1{background:#b8860b;color:#fff}.p2{background:#4a6741;color:#ddd}.p3{background:#333;color:#999}
.rs{color:#ffcb7d;font-size:11.5px;max-width:230px} .fl{color:#aaa;font-size:11px;max-width:430px}
.aud{display:none;color:#888;font-size:11px} body.audit .aud{display:table-cell}
tr.done td{opacity:.35} tr.toss td{opacity:.25;text-decoration:line-through} tr.gone td{opacity:.3;font-style:italic}
</style></head><body>
<h1>Job Board v2 - %d rows (generated %s)</h1>
<div class="sub">%s</div>
<div class="sub">One state per row. <b>SEND BUILT</b> = a resume exists, send it (file in RESUME) &middot; <b>TO TAILOR</b> = worth a custom build (Easy Apply tailors live here AND in your LinkedIn Saved queue) &middot; <b>MAYBE</b> = one named gap, in WHY, your decision &middot; <b>GENERAL</b> = worth applying, fire the General in RESUME, external apply &middot; <b>EZ QUEUE</b> = Easy Applies, tracked here but processed from LinkedIn Saved (audit view) &middot; <b>QUEUE</b> = machine-flagged APPLY/MAYBE, awaiting workplace verification and the reader (the sweep drains it daily) &middot; <b>UNSCORED / MY SKIPS / ALL</b> = audit views with the machine columns. Sorted best-pay first inside every view. TAILOR rows carry %s. <b>STAFF</b> = consulting/staffing/reposter shell; real companies sort first in every view. <b>J1 / J2 / J3</b> = how well your Career Bank covers the JD's requirements (hover for the matched %% and the gaps; machine estimate). <b>M</b> = mission-driven company (hover for the reason). %s<b>sort</b> reorders any view: pay (default), fit, mission, best overlap (P1 + J1 + M).</div>
<div>%s &nbsp; <input type="text" id="q" placeholder="search title, company, why" oninput="fq()"></div>
<div style="margin-top:4px">region: <button onclick="fr('ALL')" id="r-ALL">ALL</button><button onclick="fr('US')" id="r-US">US</button><button onclick="fr('EU')" id="r-EU">EU</button>
&nbsp;&nbsp;sort: <button onclick="fs('pay')" id="s-pay">pay</button><button onclick="fs('fit')" id="s-fit">fit (J)</button><button onclick="fs('mission')" id="s-mission">mission (M)</button><button onclick="fs('best')" id="s-best">best overlap</button>
&nbsp;&nbsp;<button onclick="saveState()" style="background:#1c4d2e;color:#7fe0a2">&#128190; save ticks for Claude</button></div>
<table id="t"><thead><tr><th>&#10003;</th><th>&#10007;</th><th title="no longer accepting">&#8856;</th><th>title</th><th>company</th><th>comp</th><th>RESUME</th><th>WHY</th><th class="aud">bucket</th><th class="aud">verdict</th><th class="aud">fit</th><th class="aud">workplace</th></tr></thead>
<tbody>%s</tbody></table>
<script>
let V='%s';let R='ALL';let S='pay';
function ta(){const s=document.getElementById('audit-btns');const on=s.style.display==='none';s.style.display=on?'inline':'none';document.getElementById('audit-toggle').innerHTML=on?'audit &#9662;':'audit &#9656;';}
const ROWS=[...document.querySelectorAll('#t tbody tr')];
function mark(){document.querySelectorAll('button').forEach(x=>x.classList.remove('on'));
['v-'+V,'r-'+R,'s-'+S].forEach(id=>{const el=document.getElementById(id);if(el)el.classList.add('on');});
document.body.classList.toggle('audit',['QUEUE','UNSCORED','EZ','MYSKIP','ALL'].includes(V));}
function fv(v){V=v;mark();apply();}
function fr(rg){R=rg;mark();apply();}
function fs(s){S=s;mark();const tb=document.querySelector('#t tbody');const n=x=>+x||0;
const k={pay:r=>n(r.dataset.i),fit:r=>-n(r.dataset.j)*1e6+n(r.dataset.i),
mission:r=>-n(r.dataset.m)*1e9-n(r.dataset.j)*1e6+n(r.dataset.i),
best:r=>-n(r.dataset.b)*1e9-n(r.dataset.j)*1e6+n(r.dataset.i)}[s];
[...ROWS].sort((a,b)=>k(a)-k(b)).forEach(r=>tb.appendChild(r));}
let qt=null;function fq(){clearTimeout(qt);qt=setTimeout(apply,150);}
function apply(){const q=document.getElementById('q').value.toLowerCase();
for(const r of ROWS){const s=r.dataset.s;
const okV=(V==='ALL')||s===V||(V==='APPLIED'&&s==='CLOSED');
const okR=(R==='ALL')||(r.dataset.rg||'US')===R;
const okQ=!q||r.dataset.q.includes(q);
r.style.display=(okV&&okR&&okQ)?'':'none';}}
document.querySelectorAll('.ap').forEach(c=>{const k='ap-'+c.dataset.id;
c.checked=localStorage.getItem(k)==='1';
if(c.checked)c.closest('tr').classList.add('done');
c.onchange=()=>{localStorage.setItem(k,c.checked?'1':'0');c.closest('tr').classList.toggle('done',c.checked);};});
document.querySelectorAll('.tx').forEach(c=>{const k='tx-'+c.dataset.id;
c.checked=localStorage.getItem(k)==='1';
if(c.checked)c.closest('tr').classList.add('toss');
c.onchange=()=>{localStorage.setItem(k,c.checked?'1':'0');c.closest('tr').classList.toggle('toss',c.checked);};});
document.querySelectorAll('.cl').forEach(c=>{const k='cl-'+c.dataset.id;
c.checked=localStorage.getItem(k)==='1';
if(c.checked)c.closest('tr').classList.add('gone');
c.onchange=()=>{localStorage.setItem(k,c.checked?'1':'0');c.closest('tr').classList.toggle('gone',c.checked);};});
function saveState(){const s={applied:[],tossed:[],closed:[],saved:new Date().toISOString()};
for(let i=0;i<localStorage.length;i++){const k=localStorage.key(i);
if(k.startsWith('ap-')&&localStorage.getItem(k)==='1')s.applied.push(k.slice(3));
if(k.startsWith('tx-')&&localStorage.getItem(k)==='1')s.tossed.push(k.slice(3));
if(k.startsWith('cl-')&&localStorage.getItem(k)==='1')s.closed.push(k.slice(3));}
const b=new Blob([JSON.stringify(s,null,1)],{type:'application/json'});
const a=document.createElement('a');a.href=URL.createObjectURL(b);a.download='board-state.json';
document.body.appendChild(a);a.click();a.remove();}
mark();apply();
</script></body></html>""" % (esc(BOARD_TITLE), datetime.date.today().isoformat(), len(rows), datetime.date.today().isoformat(),
                             ROUTINE, P_LEGEND, LOCAL_LEGEND, btns, "\n".join(body), start)

open("resume-workspace/sourcing/job-board-v2.html", "w", encoding="utf8").write(doc)
print("job-board-v2.html written: %d rows | counts: %s" % (len(rows), counts))
