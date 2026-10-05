# PIPELINE SPEC - the design sheet

Why this file exists: adding one feature kept silently breaking another. This sheet is the
registry of every pipeline feature, its contract, and where its regression test lives. RULES:
1. Any change to a file listed here REQUIRES: (a) updating this sheet's row if the contract
   changes, (b) `python resume-workspace/sourcing/pipeline_selftest.py` passing. A hook
   (`.claude/hooks/selftest_gate.py`) runs the selftest automatically after every Edit/Write to
   `sourcing/*.py` or `sourcing/*.js` and blocks on failure.
2. A feature without a selftest row is a feature that can silently die (a harvester once lived
   only in session memory, not in a file, and a routine redesign orphaned it for 9 days).
   Canonical artifacts only. No session-memory tooling. Ever.
3. Nothing personal lives in code. Who is searching (keywords, regions, local markets, walls,
   strengths, never-claim terms, pay tiers, currencies, lane resume files, board title) lives in
   `profile.json` at the repo root, under the keys below. The selftest runs on `profile.json`, or
   on `profile.example.json` when there is none (its first output line says which), and tests the
   personal rules' mechanics on a built-in fixture profile, never on anyone's real lists.

## Profile keys the pipeline reads
| Key | Read by | Controls |
|---|---|---|
| `search.coreKeywords` | daily_sweep, ingest_harvest, verify_board (A) | the titles searched; batches in a region with `requireCoreKeywords` must use all of them |
| `search.regions.<US/EU>` | ingest_harvest, verify_board (A), daily_sweep | `geoIds` (harvest), `guestLocation` (guest sweep), `requiredWorkplace` (e.g. remote-only), `requireCoreKeywords`, `gateChecksManifests` (the gate re-checks stored manifests), optional `keywords` |
| `search.guestSweepRegion` | daily_sweep | which region the no-login sweep searches |
| `search.localMarkets` | sweep_lib (`local_market`, `local_token`, `LOCAL_TOKENS`), ingest, verify_workplace, board, `evaluate(local=True)` | places where hybrid and/or onsite roles are acceptable |
| `scoring.hardWallRegex` | classify, verify_board (C), J axis | titles that are un-appliable no matter who posts them |
| `scoring.classify.*` | classify | watchlist, block/aggregator/gig lists, junior / domain / out-of-field / off-lane / director rules, product companies, agency shapes |
| `scoring.evaluate.*`, `pay.usd` | evaluate | location pins, travel, domain JD words, strengths, never-claim terms, people-management bar, verdict thresholds, USD ceiling and bonus |
| `scoring.laneRules.*` | stamp_lane | TAC vs STRAT |
| `scoring.jAxis.*` | jd_match | J tiers, generic and strong words, languages, credentials, degree fields, years bar, domain gaps, registry skill phrases |
| `pay.currencies`, `pay.rangeSeparators` | comp_from_jd_nonusd, board comp_key | non-USD mining, monthly rules, conversion for tiering |
| `pay.tiers` | board | P1/P2/P3 thresholds per region |
| `board.title`, `board.staffingFlagRegex` | board | page title, STAFF tag |
| `lanes.TAC/STRAT.generalResume`, `person.fileNamePrefix` | board, verify_board (F) | the General each lane fires; the built-resume file pattern |

## Intake (two sources, BOTH required)
| Feature | Contract | Test |
|---|---|---|
| Voyager harvester (`voyager_harvest.js`) | Canonical in-browser JS for a logged-in LinkedIn tab. Authenticated search that truly honors the workplace filter; emits `id|title|company|location|easyApply` lines. Run once per `search.coreKeywords` entry per region (`geoIds` from `search.regions`), daily window r86400 (backfill and weekly regions r604800). THE ONLY SOURCE of the easyApply flag. **Geo param:** LinkedIn answers HTTP 500 to `locationUnion:(geoIds:List(...))`; the singular `locationUnion:(geoId:N)` is the live form, so multi-geo sets are looped one geo at a time inside the function and deduped across geos. **Fields:** JobPosting is a stub; company, location and the apply method live on JobPostingCard, and easyApply is a `footerItems[].type == "EASY_APPLY_TEXT"` entry. If rows ever come back as `id|title|||0`, STOP: ingesting a hard-0 harvest would wipe easyApply across the whole pool. Local markets run as separate harvests (`workplaceTypes` [3] hybrid / [1] onsite, optional `locationFilter`). | selftest: file exists + canonical markers |
| Guest sweep (`daily_sweep.py`) | Volume net, no login, region `search.guestSweepRegion`. Remote filter UNTRUSTED (the guest API lies), no easyApply. Classifies, scores at birth, mines comp, stamps lanes. | selftest: compile + markers |
| `ingest_harvest.py` | THE ONLY ingest path. Registers the manifest, applies the region rules from the profile (core keywords, required workplace, this region's local-market tokens), dedupes by jobId AND company+title, runs reclassify (region forwarded: an unforwarded `--eu` once scored zero EU rows) and dedupe_pool, then stamps lanes with `sweep_lib.stamp_lane`. A harvest line matching an EXISTING row ENRICHES it via `sweep_lib.enrich_from_harvest`: easyApply always stamped from harvest truth; workplace set from the harvest's own filter only when the row has none (never overwrites verify-page truth or GONE). | selftest: enrich cases + markers |

## Scoring & judgment
| Feature | Contract | Test |
|---|---|---|
| `sweep_lib.classify()` | One title/company rule chain from `scoring.classify`. Hard walls are tested BEFORE the watchlist: the watchlist guarantees visibility, never wall exemption, and a walled watchlist row keeps a WATCHLIST-tagged reason so the sweep report still names it. There is no applied-company rule: applied state comes from the tracker and board-state (`sync_applied.py`). | selftest: smoke + fixture walls-beat-watchlist |
| `sweep_lib.evaluate()` | Regex scorer -> verdict APPLY/MAYBE/PASS/FLAG + why + score. Hard fails (location pin, travel, domain JD content, USD ceiling) give PASS, or FLAG for a watchlist company (the script never makes the call on a named company). `local=True` skips the location pin. | selftest: smoke + fixture local-lane cases |
| Score-at-birth (`score_rows`) | Every non-SKIP row gets JD fetch + verdict + lane + mined comp the day it arrives. Invariant G: unscored live = 0. | verify_board G + selftest smoke |
| `sweep_lib.comp_from_jd()` | Mines the pay band from JD text (LinkedIn's structured comp field is usually empty): USD ranges, K-forms, EU dot separators, hourly kept `/hr` and never annualized in display, 401(k) never matches, no band -> None; then non-USD bands from `pay.currencies` (a currency marker is required on one side; a currency's `monthly` rule labels `/mo`). | selftest: 6 USD cases + fixture currency cases |
| J axis (`sweep_lib.jd_match`) | Bank-vs-JD requirement coverage, computed at board render so it never goes stale. Cover vocabulary = terms found in 2+ builds' `resume-configs/*-kw.json` (single-build vocabulary scored a JD against its own build). Blockers = `Career_Bank.md` never-claim SKILL entries (style and overclaim wording bans excluded: they appear in ordinary JD prose), `neverClaim`, hard walls, and the `scoring.jAxis` gap lists. Required lines weigh 1.0, preferred 0.5; tiers from `scoring.jAxis.tiers` with blocker caps. | selftest: fixture J cases |
| ALTITUDE (SOP) | Reader judges lane from JD text; scope denominators over verbs; top-of-ladder titles STRAT; comp stamped on every TAILOR/MAYBE call; P-claims valid only against the stamped comp field. | reviewed in reader calls; apply_calls vocab in selftest |
| `apply_calls.py` | ONE sanctioned call writer. Closed vocab TAILOR/MAYBE/GENERIC/SKIP/NEEDS-YOU/VERIFY plus annotation-only KEEP; accepts lane + comp + mission; annotations apply even when the call is unchanged; never creates rows. | selftest: vocab set literal + markers |

## Verification & saves
| Feature | Contract | Test |
|---|---|---|
| `voyager_verify.js` | Canonical verify + pageSave/pageUnsave with clickHard (LinkedIn's Save ignores a bare click). SUSPENDED = closed. Both closed-page strings are tested. Only SAVED/ALREADY count as saves. | selftest: file markers |
| `verify_workplace.py` | Applies verify results; a hybrid/onsite result flips the call to SKIP, except in a local market, where the row takes a market token and keeps its call; refuses saves on non-easyApply rows (LinkedIn Saved is the Easy Apply queue only). | selftest: markers |
| Watch (`board-state.json` watch) | Closed ticks -> GONE + watch; daily job-page recheck; a reopen is announced loudly. | verify_board + routine step |

## Board & state
| Feature | Contract | Test |
|---|---|---|
| `board_gen_v2.py` | Contract in `Board_Spec.md`. States SEND/TAILOR/MAYBE/GENERAL/EZ/QUEUE/UNSCORED/MYSKIP/APPLIED/CLOSED; 4 primary buttons + audit toggle; lane files from the profile; P tags from the comp FIELD on `pay.tiers` (hourly x 2,000; converted currencies as annual EUR); STAFF tag + real-companies-first sort; local-market tag; J and M tags + sort buttons; 3rd tick column -> GONE + watch; synthetic SEND rows for built resumes with no pool row (never for an applied id). | verify_board F + selftest markers |
| `verify_board.py` | Blocks board gen on: A manifests (profile region rules), B JD verdicts, C walls, D dedupe (shared key; groups whose calls disagree are not duplicates), E lanes, F layout (view list + lane files read from the profile), G unscored, H save rule, I harvest freshness (newest daily-harvest file older than 48h = NEEDS-YOU), I2 harvest content (fewer than 25 rows, more than 5% blank companies, or under 5 easyApply rows), J applied ids reach the tracker. | it IS the gate; selftest checks markers |
| `ingest_state.py` | Board ticks ingest; merge preserves every canonical key (watch, linkedinAppliedSync, ticksImport); closed ticks -> GONE + watch; ticks without a tracker entry get a minimal one. | selftest: preserve-keys marker |
| `sync_applied.py` | Tracker + board-state -> pool APPLIED/CLOSED/NEEDS-YOU. A repost needs the shared `dedupe_key` AND the tracked req's region (a looser any-region key once hid 29 distinct reqs). Board-state applied flips tracker built-unsent/tracked entries to applied (dated by the first commit recording the id); stale "BUILT unsent ... Send it" notes are cleared; false repost stamps revert to a reader call. | verify_board J + selftest markers |
| `dedupe_pool.py` | Collapses reposts on the shared key within a region. Applied, tracker-referenced and watched rows are never dropped; live calls outrank SKIP when choosing the keeper; rows whose calls disagree stay visible. | selftest markers |

## Resume gates (listed for completeness; owned by Resume_Process.md)
`guard_render.py`, `verify_render.py`, `check_output.py`. The selftest compiles all three and checks the workspace-cwd path markers.

## Routine (a scheduled daily task)
Step order: harvest (+ weekly regions when due) -> ingest -> guest sweep -> sync applied -> tracker
scrape -> verify APPLY/MAYBE/FLAG -> watch recheck -> reader (altitude + comp on every call) -> EZ
saves -> board gen -> `verify_board.py --check` -> daily report file (`reports/sweep-YYYY-MM-DD.md`,
with per-step health; any failed or skipped step = NEEDS-YOU header) -> commit with measured numbers.
The report file and the commit message MUST carry every degradation flag. Transcripts are not the
alerting channel; the report file and the commit message are.

## Change log
- kit v1.0: pipeline packaged as a reusable kit. Every personal value moved to `profile.json`
  (keys above); the hard-coded applied-company classify rule removed (the tracker and board-state
  already know what is applied); `ingest_harvest.py` now stamps lanes with the shared
  `sweep_lib.stamp_lane` instead of a private copy that had drifted (its strategic-company regex
  carried a stray control character, so one company never matched); the selftest runs on the
  owner's profile and tests personal-rule mechanics on a fixture profile. Behavior parity with the
  source pipeline was proven function by function on the full source pool and on a full board render.
