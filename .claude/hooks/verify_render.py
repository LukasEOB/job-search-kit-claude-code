#!/usr/bin/env python3
"""Provenance + content gate. Runs BEFORE a render, so it blocks bad paper rather than
auditing it afterwards. Exit 2 = block. Exit 0 = pass.

Enforces four things against resume-workspace/resume-configs/<config>.json:

  1. PROVENANCE  every bullet carries a `bankAnchor` that appears VERBATIM in Career_Bank.md.
                 No anchor, or an anchor that is not in the bank, blocks the render.
  2. NEVER-CLAIM no bullet or summary contains a phrase from the bank's NEVER-CLAIM REGISTRY.
  3. CONTENT     summary length, banned phrases, AI tells, em-dashes, escape artifacts,
                 checked on the CONFIG (the old docx checks never fired on a render at all).
  4. ATS         achievable-keyword coverage, scored against the keyword list MINUS anything
                 in the never-claim registry. Reported always; blocks below the floor.

Personal rules live in profile.json, not here (see profile.resume.example.json):
  `gates`        tunable thresholds; a missing key keeps the built-in default.
  `lanes`        resume lanes and the config-name prefix that selects each one.
  `summaryLock`  an optional locked summary sentence (required phrases, ceilings). Off unless
                 `summaryLock.enabled` is true. With no profile.json at all, every generic
                 check still runs on the defaults and the lock is off.

Reads Claude Code hook JSON on stdin, or `python verify_render.py <config.json>` by hand."""
import sys, json, re, os
from collections import Counter

BANNED = ["hardworking", "team player", "passionate about", "responsible for", "detail-oriented",
          "detailed-orientat", "results-driven", "self-starter", "proven track record", "synergy",
          "rigorous scale", "perfectly aligns", "seamless", "leverage my",
          "i am writing to express", "i am excited to apply", "proven expertise",
          "demonstrated excellence", "seasoned", "highly accomplished"]
AI_TELLS = ["having delivered", "having run", "having built", "not just shipping", "not just deploying"]

HERE = os.path.dirname(os.path.abspath(__file__))


def project_dir():
    return os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()


def import_profile_lib():
    """profile_lib.py ships in resume-workspace/ next to the renderer. Look beside this hook's own
    repo first (the hook and the loader travel together), then under CLAUDE_PROJECT_DIR."""
    for root in (os.path.dirname(os.path.dirname(HERE)), project_dir()):
        ws = os.path.join(root, "resume-workspace")
        if os.path.exists(os.path.join(ws, "profile_lib.py")):
            if ws not in sys.path:
                sys.path.insert(0, ws)
            import profile_lib
            return profile_lib
    raise ImportError("resume-workspace/profile_lib.py not found")


def resolve_cfg_asset(cfg_path, rel):
    """Resolve a config-declared relative path (jdFile / keywordFile). Configs have written bare
    filenames, workspace-relative paths, and legacy inputs/ paths; a bare keywordFile never
    resolved, so the ATS gate silently degraded to a warning on every reference config
    (found independently by both build agents, 2026-09-03). Returns the first existing
    candidate or None; callers decide whether a miss blocks."""
    if not rel:
        return None
    cfg_dir = os.path.dirname(os.path.abspath(cfg_path))
    ws = os.path.dirname(cfg_dir)
    for cand in (os.path.join(ws, rel), os.path.join(cfg_dir, rel),
                 os.path.join(ws, "inputs", rel), os.path.join(ws, "sourcing", "jds", rel)):
        if os.path.exists(cand):
            return cand
    return None


def find_up(filename, start):
    """Walk up from `start` until `filename` is found. The session's working directory may be
    the project root OR resume-workspace (a child); path assumptions broke the gate silently."""
    d = os.path.abspath(start)
    for _ in range(8):
        p = os.path.join(d, filename)
        if os.path.exists(p):
            return p
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return None


def load_bank(near=None):
    p = find_up("Career_Bank.md", near or project_dir())
    return open(p, encoding="utf8").read() if p else ""


def never_claims(bank):
    """Parse the machine-enforced registry: lines of the form  - 🚫 `phrase` : reason"""
    out = []
    for line in bank.split("\n"):
        m = re.match(r"\s*-\s*\U0001F6AB\s*`([^`]+)`", line)
        if m:
            out.append(m.group(1).strip())
    return out


def norm(s):
    """Collapse whitespace and strip markdown emphasis, so an anchor may span a **bold** boundary
    in the bank without false-failing."""
    return re.sub(r"\s+", " ", s.replace("*", "").replace("`", "").replace("~", "")).strip()


def jd_mirrored(bank):
    """Parse the JD-MIRRORED PHRASES registry: lines of the form  - 🔁 `phrase`
    Each phrase may appear in a config only if that config's own jdFile contains it."""
    out = []
    for line in bank.split("\n"):
        m = re.match(r"\s*-\s*\U0001F501\s*`([^`]+)`", line)
        if m:
            out.append(m.group(1).strip())
    return out


def pick_lane(base, lanes):
    """The lane whose `configPrefix` the config file name starts with. The longest non-empty
    prefix wins; a lane with an empty prefix is the default. Keys starting with "_" are notes."""
    best, best_len = None, -1
    for name, spec in (lanes or {}).items():
        if name.startswith("_") or not isinstance(spec, dict):
            continue
        pfx = spec.get("configPrefix", "") or ""
        if base.startswith(pfx) and len(pfx) > best_len:
            best, best_len = name, len(pfx)
    return best


def summary_lock(lock, lane, s_lock, jd_text, errs, warns):
    """The owner's locked summary sentence (profile `summaryLock`). What is locked is the MEANING,
    carried by required phrases, not a verbatim string: a verbatim lock once froze a JD-mirrored
    variant of the sentence into 27 builds (RCA 2026-08-22). The verbs and objects around the
    required phrases stay free, subject to the ceilings checked by the caller."""
    n = norm(s_lock).lower()
    lane_rules = ((lock.get("lanes") or {}).get(lane) or {}) if lane else {}
    missing = [p for p in list(lock.get("requiredPhrases") or []) + list(lane_rules.get("requiredPhrases") or [])
               if p.lower() not in n]
    for group in list(lock.get("requiredAnyOf") or []) + list(lane_rules.get("requiredAnyOf") or []):
        ok = any(a.lower() in n for a in group.get("anyOf") or [])
        # A JD-conditional alternative counts only when THIS job's JD uses its trigger word, so a
        # wording borrowed from one posting cannot drift into every summary.
        for cond in group.get("jdConditional") or []:
            if not ok and cond["phrase"].lower() in n:
                if jd_text is None or cond["jdWord"].lower() not in jd_text:
                    errs.append(cond.get("message") or (
                        "%s: %r is allowed only when the JD uses the word %r; this one does not. "
                        "Use one of: %s." % (lock.get("label", "SUMMARY LOCK"), cond["phrase"],
                                             cond["jdWord"], ", ".join(map(repr, group.get("anyOf") or [])))))
                else:
                    ok = True
        if not ok:
            missing.append(group.get("missingLabel") or " or ".join(map(repr, group.get("anyOf") or [])))
    if missing:
        errs.append("%s (%s lane): sentence %d must carry %s. Missing: %s. "
                    "Only the required phrases are locked; the words around them stay adjustable."
                    % (lock.get("label", "SUMMARY LOCK"), (lane or "default").lower(),
                       int(lock.get("sentence", 2)),
                       lock.get("description", "the locked phrases from profile.json summaryLock"),
                       ", ".join(repr(m) for m in missing)))
    for w in lane_rules.get("warnIfMissing") or []:
        if w["phrase"].lower() not in n:
            warns.append(w.get("message") or "locked sentence has no %r" % w["phrase"])
    for f in lane_rules.get("forbidPatterns") or []:
        if re.search(f["regex"], n):
            errs.append(f.get("message") or "locked sentence matches forbidden pattern %r" % f["regex"])


def check(cfg_path, bank, profile=None):
    errs, warns, info = [], [], []
    import_profile_lib()
    import profile_lib
    G = profile_lib.gates(profile)
    lock = (profile or {}).get("summaryLock") or {}
    lock_on = bool(lock.get("enabled"))
    lock_n = int(lock.get("sentence", 2)) if lock_on else 0
    FLOOR = float(G["atsFloor"])
    SW = G["summaryWords"]

    cfg = json.load(open(cfg_path, encoding="utf8"))
    summary = cfg.get("summary", {}).get("text", "")
    bullets = [(j.get("company", "?"), i + 1, b)
               for sec in cfg.get("experienceSections", [])
               for j in sec.get("jobs", [])
               for i, b in enumerate(j.get("bullets", []))]
    anchors = {}
    for sec in cfg.get("experienceSections", []):
        for j in sec.get("jobs", []):
            for i, b in enumerate(j.get("bullets", [])):
                anchors[(j.get("company", "?"), i + 1)] = j.get("bankAnchors", {}).get(str(i), None) \
                    if isinstance(j.get("bankAnchors"), dict) else None

    # ---- 1. PROVENANCE ----
    # Anchors may only resolve against paper-eligible bank text. Two exclusions:
    #  - everything from the "INTERVIEW ONLY" heading onward (true, but not for paper)
    #  - ~~struck-through~~ spans, so a retired claim cannot prove its own provenance from the
    #    very text that retired it.
    paper_bank = re.split(r"\n##+\s*\U0001F512\s*INTERVIEW ONLY", bank)[0]
    bank_n = norm(re.sub(r"~~.*?~~", " ", paper_bank, flags=re.S))
    if not bank:
        errs.append("Career_Bank.md not found. Cannot verify provenance.")
    for (co, n, _b) in bullets:
        a = anchors.get((co, n))
        if not a:
            errs.append("NO BANK ANCHOR: %s bullet %d. Every bullet needs a bankAnchors entry "
                        "quoting Career_Bank.md verbatim." % (co, n))
            continue
        # A bullet that merges two banked facts needs an anchor for EACH, otherwise half the
        # claim rides on the other half's provenance. Accept a list as well as a string.
        for one in (a if isinstance(a, list) else [a]):
            if norm(one) not in bank_n:
                errs.append("ANCHOR NOT IN BANK: %s bullet %d -> %r. Nothing in Career_Bank.md "
                            "matches this. The claim is unsourced." % (co, n, one[:70]))
    # Certifications print as their own section, so they need provenance too: the name (the text
    # before the first comma, e.g. "Project Management Professional (PMP)") must be in the bank.
    for c in cfg.get("certifications") or []:
        name = c.split(",")[0].strip()
        if name and norm(name) not in bank_n:
            errs.append("CERTIFICATION NOT IN BANK: %r. Add it to Career_Bank.md first, or remove it." % name)

    # ---- 2. NEVER-CLAIM REGISTRY ----
    registry = never_claims(bank)
    info.append("never-claim registry: %d phrases loaded" % len(registry))
    blob_parts = [("headline", cfg.get("headline", "")), ("summary", summary)] + [("%s bullet %d" % (co, n), b) for co, n, b in bullets]
    for cat, det in cfg.get("skills", []):
        # Include the category label: the renderer prints it, so a parser sees it too.
        blob_parts.append(("skills row %r" % cat, cat + ": " + det))
    for c in cfg.get("certifications") or []:
        blob_parts.append(("certification %r" % c[:40], c))
    for where, text in blob_parts:
        for phrase in registry:
            if re.search(r"\b%s\b" % re.escape(phrase), text, re.I):
                errs.append("NEVER-CLAIM %r appears in %s. This is a confirmed negative or a "
                            "disputed claim. It cannot go on paper." % (phrase, where))

    # ---- 3. CONTENT ----
    w = len(summary.split())
    if w > SW["hardMax"]:
        errs.append("SUMMARY IS %d WORDS. Hard limit %d, target %d-%d."
                    % (w, SW["hardMax"], SW["targetMin"], SW["targetMax"]))
    elif w < SW["targetMin"]:
        warns.append("summary only %d words (target %d-%d)" % (w, SW["targetMin"], SW["targetMax"]))
    whole = " ".join(t for _, t in blob_parts)
    low = whole.lower()
    for b in BANNED:
        if b in low:
            errs.append("BANNED PHRASE: %r" % b)
    for a in AI_TELLS:
        if a in low:
            errs.append("AI TELL: %r" % a)
    # Participial pile-up: 3+ gerunds in list position hanging off one finite verb. Documented AI
    # tell (Step 9.4). Counts prepositional position ("by launching, running, and standing up"),
    # which a comma/and-only pattern misses.
    # Plenty of -ing words in this domain are NOUNS, not gerunds. Counting them produced a false
    # positive on "product and engineering teams" that would have blocked the owner's own approved
    # summary. Exclude the known nouns before counting.
    ING_NOUNS = {"engineering", "marketing", "training", "planning", "reporting", "tracking",
                 "testing", "gating", "onboarding", "learning", "grooming", "billing",
                 "forecasting", "ticketing", "accounting", "manufacturing", "consulting",
                 "pricing", "licensing", "whitelabeling", "meeting", "briefing", "staffing",
                 "coding", "building", "sourcing", "monitoring", "logging", "caching"}
    for where, text in blob_parts:
        ger = [g for g in re.findall(r"(?:,|\band\b|\bby\b|\bthrough\b)\s+(\w+ing)\b", text)
               if g.lower() not in ING_NOUNS]
        if len(ger) >= 3:
            errs.append("PARTICIPIAL PILE-UP in %s (%s). Rewrite with finite verbs."
                        % (where, ", ".join(ger)))
    if "\u2014" in whole:
        errs.append("EM-DASH in resume body text.")
    if "\\$" in whole or "\\\\" in whole:
        errs.append("ESCAPE ARTIFACT (\\$ or \\\\) in the config.")

    # ---- 3d. JD-MIRRORED PHRASES (anti-clone-chain) ----
    # A phrase in the bank's 🔁 registry may appear here ONLY if this config's own JD contains it.
    # Blocks one company's JD language from leaking into another company's resume.
    mirrored = jd_mirrored(bank)
    info.append("jd-mirrored registry: %d phrases loaded" % len(mirrored))
    used = [(where, p) for where, text in blob_parts for p in mirrored
            if re.search(re.escape(p), text, re.I)]
    if used:
        jd_rel = cfg.get("jdFile", "")
        jd_path = resolve_cfg_asset(cfg_path, jd_rel)
        jd_text = open(jd_path, encoding="utf8").read().lower() if jd_path else None
        for where, p in used:
            if jd_text is None:
                errs.append("JD-MIRRORED phrase %r in %s but jdFile %r is missing/unset. "
                            "Mirrored phrases require the JD on disk to prove the JD uses them." % (p, where, jd_rel))
            elif p.lower() not in jd_text:
                errs.append("JD-MIRRORED phrase %r in %s but THIS job's JD never says it. "
                            "That phrase belongs to another company's JD (clone-chain leak). "
                            "Use this JD's own vocabulary." % (p, where))

    _jdp = resolve_cfg_asset(cfg_path, cfg.get("jdFile", ""))
    jd_text = open(_jdp, encoding="utf8").read().lower() if _jdp else None
    try:
        _kwp = resolve_cfg_asset(cfg_path, cfg.get("keywordFile", ""))
        kw_list = json.load(open(_kwp, encoding="utf8")) if _kwp else []
        if not isinstance(kw_list, list): kw_list = []
    except Exception:
        kw_list = []

    # ---- 3e. SUMMARY SHAPE: the optional lock, then the reread ----
    # Configs named with an exempt prefix carry a summary that was approved as a whole (your
    # General resumes, archived SUBMITTED- copies); re-gating it would force edits to approved
    # text, so both the lock and the reread skip them.
    base = os.path.basename(cfg_path)
    sents = [x.strip() for x in re.split(r"(?<=[.!?])\s+", summary.strip()) if x.strip()]
    exempt = any(base.startswith(p) for p in G["summaryExemptConfigPrefixes"])
    if not exempt:
        reread_exempt = {x.lower() for x in G["rereadExemptWords"]}
        if lock_on:
            lane = pick_lane(base, (profile or {}).get("lanes"))
            s2 = sents[lock_n - 1] if len(sents) >= lock_n else ""
            summary_lock(lock, lane, s2, jd_text, errs, warns)
            # Pipeline checks (owner, 2026-08-22: a summary is supposed to invite the reader in,
            # not hold every claim).
            w2 = len(s2.split())
            if "maxWords" in lock and w2 > int(lock["maxWords"]):
                errs.append("SENTENCE %d IS %d WORDS; ceiling is %d (the General's own length)."
                            % (lock_n, w2, int(lock["maxWords"])))
            lists = len(re.findall(r",\s+and\s+", s2))
            if "maxLists" in lock and lists > int(lock["maxLists"]):
                errs.append("SENTENCE %d has %d 'a, b, and c' lists; max %d (the General's own "
                            "shape). More is keyword stuffing." % (lock_n, lists, int(lock["maxLists"])))
            regions = lock.get("regionNames") or []
            if regions:
                geo = re.findall(r"\b(%s)\b" % "|".join(re.escape(r) for r in regions), summary)
                if geo and (jd_text is None or not any(g.lower() in jd_text for g in geo)):
                    errs.append("SUMMARY names regions %s but the JD does not; drop them (write "
                                "'globally distributed' or nothing)." % sorted(set(geo)))
            if kw_list and "proofKeywordCap" in lock:
                # Score only the authored proof sentences (after the locked one). The locked
                # sentences carry whatever vocabulary the lock carries; when a JD's keyword list
                # overlaps it ("workflows", "execution", "product") that is not stuffing, and the
                # lock cannot be de-stuffed without breaking itself.
                _s3 = " ".join(sents[lock_n:]).lower()
                _skel = {x.lower() for x in lock.get("proofKeywordExempt") or []}
                hits = [k for k in kw_list if k.lower() in _s3 and k.lower() not in _skel]
                cap = int(lock["proofKeywordCap"])
                if len(hits) > cap:
                    errs.append("SUMMARY proof sentence carries %d keyword-file hits (%s); cap is %d. "
                                "Move the rest to bullets or skills." % (len(hits), ", ".join(hits[:8]), cap))
            # The lock's own vocabulary may repeat across sentences without being an echo.
            reread_exempt |= {x.lower() for x in lock.get("rereadExemptWords") or []}
        # REREAD CHECK (added 2026-08-22, after the owner pointed out the agent had no way to
        # reread its own work): no content word may appear twice in the summary unless it is
        # listed as exempt (gates.rereadExemptWords, or the lock's own vocabulary).
        words = re.findall(r"[a-z][a-z\-]{5,}", summary.lower())
        dup = sorted(w for w, n in Counter(words).items() if n > 1 and w not in reread_exempt)
        if dup:
            errs.append("REREAD: summary repeats %s. Each sentence must carry different nouns."
                        % ", ".join(dup))
        if lock_on:
            info.append("summary s%d: %d words, %d lists" % (lock_n, w2, lists))

    # ---- 3c. WHOLE-PAGE REVIEW ----
    # Every defect the owner caught by hand (duplicate bullets, a position-1 with no number,
    # semicolon-stapled facts, activity-first bullets) is only visible when the assembled page is
    # read end to end. Claude kept editing bullet-by-bullet and never re-reading. Automate it.
    jobs = [j for sec in cfg.get("experienceSections", []) for j in sec.get("jobs", [])]
    OVER_STOP = {"the", "and", "a", "of", "to", "in", "for", "with", "on", "that", "across",
                 "their", "it", "before", "by", "from", "at", "as", "an", "is", "was", "were",
                 "then", "into", "them", "its", "this", "through", "while", "both", "each"}
    def dwords(s):
        return {w for w in re.findall(r"[a-z]+", s.lower()) if w not in OVER_STOP and len(w) > 3}
    flat = [("%s #%d" % (j.get("company", "?")[:12], i + 1), b)
            for j in jobs for i, b in enumerate(j.get("bullets", []))]
    for x in range(len(flat)):
        for y in range(x + 1, len(flat)):
            shared = dwords(flat[x][1]) & dwords(flat[y][1])
            if len(shared) >= 4:
                errs.append("DUPLICATE BULLETS: %s and %s share %s. Merge them or cut one."
                            % (flat[x][0], flat[y][0], ", ".join(sorted(shared))))
            elif len(shared) == 3:
                warns.append("%s / %s overlap on %s" % (flat[x][0], flat[y][0], ", ".join(sorted(shared))))
    for j in jobs:
        # Only for roles that actually get scanned. A 1-2 bullet legacy role may have no banked
        # metric at all (one older role had its only metric removed at the owner's request), and
        # demanding a number there would mean inventing one.
        if len(j.get("bullets") or []) < 3:
            continue
        b = j["bullets"][0]
        if not re.search(r"\d", b):
            errs.append("POSITION 1 HAS NO NUMBER: %s. Step 6 requires the top bullet of each role "
                        "to be the highest-relevance one that passes 'so what' with a number."
                        % j.get("company", "?"))
    allb = [b for _, b in flat]
    if allb:
        RESULT = r"\d|\bcut\b|\braised\b|\bdelivered\b|\bdrove\b|\bimproved\b|\bwon\b|\breversed\b|\bcaptured\b|\blifted\b|\breclaimed\b|\badded\b|\bheld\b"
        of = sum(1 for b in allb if re.search(RESULT, " ".join(b.split()[:8]), re.I))
        # Target calibrated on a resume that earned interviews: 15 of its 18 bullets led with
        # the outcome.
        if of / len(allb) < 0.70:
            warns.append("only %d/%d bullets are outcome-first (target 70%%+)" % (of, len(allb)))
        semis = sum(b.count(";") for b in allb)
        if semis > 2:
            warns.append("%d semicolons across the bullets. A semicolon usually means two facts "
                         "stapled together rather than one cause producing both" % semis)

    # ---- 3b. DE-ECHO ----
    # Lifting the JD's own phrasing reads as AI-tailored to the person who wrote it. Threshold is
    # 4 words, not 6: "Led the governance workstream" was lifted from the JD and a 6-word check
    # missed it. Stopword-only runs are ignored. (gates.deEchoWords tunes the threshold.)
    jdf = cfg.get("jdFile")
    if jdf:
        jp = resolve_cfg_asset(cfg_path, jdf)
        if jp:
            ECHO_STOP = {"and", "or", "the", "of", "a", "in", "for", "to", "with", "across",
                         "that", "on", "at", "as", "by", "an", "is"}
            words = lambda t: re.sub(r"[^a-z0-9 ]", " ", t.lower()).split()
            jd_s = " ".join(words(open(jp, encoding="utf8").read()))
            # Exempt the headline (title mirroring is a recommended tactic), the skills rows
            # (a skills list exists to carry the JD's exact keywords and reads as a list, not
            # prose), and the opening summary sentences: sentence 1 carries the mirrored job
            # title, and a LOCKED sentence predates every JD, so a JD using the same 4-gram does
            # not make it an echo. Echoing the JD's PROSE in authored surfaces is the problem
            # this check exists for, so the scored surface is the rest of the summary plus
            # every bullet.
            _skip = max(1, lock_n)
            _sents = [x.strip() for x in re.split(r"(?<=[.!?])\s+", (summary or "").strip()) if x.strip()]
            rw = words(" ".join(_sents[_skip:]) + " " + " ".join(
                t for w, t in blob_parts
                if w not in ("headline", "summary") and not w.startswith(("skills row", "certification"))))
            n_echo = int(G["deEchoWords"])
            ech = set()
            for k in (n_echo + 1, n_echo):
                for i in range(len(rw) - k):
                    g = rw[i:i + k]
                    if sum(1 for w in g if w in ECHO_STOP) >= k - 1:
                        continue
                    if " ".join(g) in jd_s:
                        ech.add(" ".join(g))
            keep = [h for h in ech if not any(h in o and h != o for o in ech)]
            if keep:
                errs.append("DE-ECHO: %d phrase(s) lifted from the JD: %s. Rewrite in your own "
                            "words." % (len(keep), "; ".join(sorted(keep)[:5])))
            else:
                info.append("de-echo: clean at the %d-word threshold" % n_echo)
        else:
            warns.append("jdFile %r declared but not found" % jdf)
    else:
        warns.append("no jdFile declared; de-echo not checked")

    # ---- 4. ATS ----
    kwf = cfg.get("keywordFile")
    if kwf:
        kp = resolve_cfg_asset(cfg_path, kwf)
        if kp:
            kws = json.load(open(kp, encoding="utf8"))
            # A keyword is unachievable only when a forbidden phrase appears as WHOLE WORDS
            # inside it. Loose substring matching wrongly excluded "storage" (contains "rag")
            # and a cloud-vendor keyword that sat inside a longer registry entry.
            def forbidden(k):
                return any(re.search(r"\b%s\b" % re.escape(r), k, re.I) for r in registry)
            # Deliberate gaps: JD keywords you genuinely cannot claim from the bank. Excluded
            # from the denominator, but ALWAYS printed, so a gap is a stated decision and never
            # a silent truncation that makes coverage look better than it is.
            gaps = cfg.get("deliberateGaps", {})
            achievable = [k for k in kws if not forbidden(k) and k not in gaps]
            blocked = [k for k in kws if forbidden(k)]

            # Match on content words with a 6-char prefix, so "program management" is credited by
            # "Technical Program Manager" and "cost optimization" by "cloud optimization program".
            STOP = {"and", "or", "the", "of", "a", "in", "for", "to", "with"}
            def covered(k):
                # Word-boundary on BOTH ends of the fast path: a bare substring test credited
                # "RDS" to the word "standa-rds". Prefix matching still allows manager/management,
                # but must start at a word boundary so "multi-phase" cannot credit "multi-team".
                if re.search(r"\b%s\b" % re.escape(k), low, re.I):
                    return True
                words = [w for w in re.findall(r"[a-z0-9+]+", k.lower()) if w not in STOP]
                return bool(words) and all(
                    re.search(r"\b%s" % re.escape(w[:6]), low) for w in words)
            hit = [k for k in achievable if covered(k)]
            pct = len(hit) / len(achievable) if achievable else 1.0
            info.append("ATS: %d/%d achievable keywords = %.0f%%  (%d excluded as confirmed "
                        "negatives: %s)" % (len(hit), len(achievable), pct * 100,
                                            len(blocked), ", ".join(blocked) or "none"))
            if gaps:
                info.append("DELIBERATE GAPS (excluded, stated on purpose): " +
                            "; ".join("%s = %s" % (k, v) for k, v in gaps.items()))
            miss = [k for k in achievable if not covered(k)]
            if miss:
                info.append("ATS misses (achievable, not yet covered): " + ", ".join(miss))
            if pct < FLOOR:
                errs.append("ATS COVERAGE %.0f%% is below the %.0f%% floor on ACHIEVABLE keywords."
                            % (pct * 100, FLOOR * 100))
        else:
            # A declared-but-unresolvable keyword file used to be a warning, which let the ATS
            # gate silently skip every config that wrote a bare filename. An unscored tailored
            # build is the exact failure mode the floor exists to prevent, so it now blocks.
            errs.append("keywordFile %r declared but not found (tried workspace root, "
                        "resume-configs/, inputs/). ATS cannot be scored; fix the path." % kwf)
    else:
        warns.append("no keywordFile declared in config; ATS coverage not scored")

    return errs, warns, info


def main():
    # Manual mode: `python verify_render.py <config.json>` verifies that config directly.
    # (Previously this path silently exited 0, making manual "verification" a no-op.)
    if len(sys.argv) > 1 and sys.argv[1].endswith(".json"):
        cfg_path = sys.argv[1]
    else:
        try:
            data = json.load(sys.stdin)
        except Exception:
            sys.exit(0)
        cmd = (data.get("tool_input") or {}).get("command", "")
        if "render_our_template" not in cmd:
            sys.exit(0)
        m = re.search(r"render_our_template\.js\s+(\S+\.json)", cmd) or re.search(r"(\S+\.json)", cmd)
        if not m:
            sys.exit(0)
        cfg_path = m.group(1).strip("\"'")
    # CWD FIX 2026-09-09: renders run from resume-workspace with workspace-relative config
    # paths, but this hook resolved them against the project root only - the file was never
    # found and the gate SILENTLY exited 0. Every "gate PASS" since the cwd drift came from
    # manual verify runs, not from this hook. Resolve against both roots, and a config the
    # gate cannot find now BLOCKS instead of passing silently.
    if not os.path.isabs(cfg_path):
        for cand in (os.path.join(project_dir(), cfg_path),
                     os.path.join(project_dir(), "resume-workspace", cfg_path)):
            if os.path.exists(cand):
                cfg_path = cand
                break
    if not os.path.exists(cfg_path):
        print("RENDER BLOCKED: the gate cannot find config %r (tried project root and "
              "resume-workspace/). A render whose config the gate cannot verify does not "
              "run. Use a standard config path." % cfg_path, file=sys.stderr)
        sys.exit(2)
    # The profile can switch a personal rule ON (summaryLock), so a profile that exists but
    # cannot be read blocks: silently falling back to defaults would switch that rule off.
    # No profile at all is a fresh install: generic checks run on the defaults, lock off.
    try:
        profile, profile_path = import_profile_lib().load_profile_optional(
            os.path.dirname(os.path.abspath(cfg_path)))
    except Exception as e:
        print("RENDER BLOCKED: profile.json could not be read (%s). Fix it first: a broken "
              "profile must never silently switch a configured rule off." % e, file=sys.stderr)
        sys.exit(2)
    try:
        errs, warns, info = check(cfg_path, load_bank(near=os.path.dirname(os.path.abspath(cfg_path))),
                                  profile)
    except Exception as e:
        print("verify_render could not run (%s). Blocking, because an unverified render is "
              "exactly what this gate exists to prevent." % e, file=sys.stderr)
        sys.exit(2)
    if profile is None:
        warns.append("no profile.json found; built-in gate defaults used, summary lock off")
    # RECEIPT: append an audit line so every verification leaves a timestamped record
    # (standing rule since 2026-08-13: a check with no receipt is indistinguishable from no check).
    try:
        import datetime, hashlib
        bank_path = find_up("Career_Bank.md", os.path.dirname(os.path.abspath(cfg_path)))
        bank_hash = hashlib.sha1(open(bank_path, "rb").read()).hexdigest()[:10] if bank_path else "NO-BANK"
        rw = os.path.dirname(os.path.dirname(os.path.abspath(cfg_path)))
        with open(os.path.join(rw, "gate-receipts.log"), "a", encoding="utf8") as rf:
            rf.write("%s | %s | bank=%s | %s | %s\n" % (
                datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                os.path.basename(cfg_path),
                bank_hash,
                "BLOCKED: " + "; ".join(e[:80] for e in errs[:3]) if errs else "PASS",
                " / ".join(i for i in info if i.startswith(("ATS", "never-claim", "jd-mirrored")))))
    except Exception:
        pass
    for i in info:
        print("  " + i)
    if warns:
        print("  warnings: " + "; ".join(warns))
    if errs:
        print("RENDER BLOCKED for %s:\n%s\nFix these before rendering. See Resume_Process.md "
              "and the NEVER-CLAIM REGISTRY in Career_Bank.md."
              % (os.path.basename(cfg_path), "\n".join("  - " + e for e in errs)), file=sys.stderr)
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
