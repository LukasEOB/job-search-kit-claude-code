// Canonical Voyager job-search HARVESTER (canonicalized after a 9-day orphaning: this logic once
// lived only in session memory and died with a routine redesign). Runs as in-browser JS in a
// LOGGED-IN linkedin.com tab. Never improvise a variant;
// edit here. Registered in PIPELINE_SPEC.md; pipeline_selftest.py checks this file exists.
//
// WHY THIS EXISTS: the guest endpoint (daily_sweep.py) only loosely honors the remote filter
// and carries NO easyApply flag. This authenticated search is the ONLY source of both.
//
// API CHANGE (found by a backfill run, verified by probe): LinkedIn now rejects
// `locationUnion:(geoIds:List(...))` with HTTP 500 - single-geo AND multi-geo alike. The live
// jobs page sends the SINGULAR `locationUnion:(geoId:N)` against the same -220 decoration.
// Probe: singular -> 200 / 125 postings; List form -> 500 / empty, both variants. So a multi-geo
// set (e.g. several EU countries) can no longer be one request: we loop the geoIds and page each one separately,
// deduping across geos with the shared `seen` set. The caller contract (geoIds: [...]) is
// unchanged. Left as-is, every harvest returns a single `#HTTP 500 page 0` line and zero jobs.
//
// SHAPE CHANGE (same run, second break, and the dangerous one): with the 500 fixed,
// rows came back as `id|title|||0` - blank company, blank location, easyApply 0 on ALL of them.
// JobPosting is now a stub (title + urn only); company/location/apply moved to JobPostingCard,
// and easyApply is a footerItems entry of type EASY_APPLY_TEXT. This mattered more than the 500:
// ingest_harvest.py stamps easyApply onto EXISTING rows from harvest truth, so ingesting a
// hard-0 harvest would have silently wiped the easyApply flag across the whole pool - the one
// field only this harvester can supply. Verified after fix: 25 rows/page, 9 easyApply, real
// companies. If rows ever come back blank again, STOP - do not ingest.
//
// USAGE (once per keyword in profile.json search.coreKeywords; this file cannot read the profile,
// so the caller passes its values):
//   const lines = await voyagerHarvest({
//     keywords: "<one search.coreKeywords entry>",
//     geoIds: ["103644278"],            // search.regions.<REGION>.geoIds (103644278 = United States)
//     window: "r86400",                  // daily; backfill r604800; weekly regions r604800
//     maxPages: 40,
//     workplaceTypes: [2],               // default remote. LOCAL MARKETS (search.localMarkets): a
//                                        // market's geo ALSO runs [3] (hybrid) and/or [1] (onsite) as
//                                        // SEPARATE harvests, so each file carries one known workplace
//                                        // for ingest (--workplace <code>-hyb / <code>-onsite)
//     locationFilter: "\\bcityname\\b",  // optional regex; keeps only cards whose location matches
//                                        // (a country geo narrowed to one commutable city)
//   });
// Collect lines from each run, concatenate, save as daily-harvest-YYYY-MM-DD.txt, then:
//   python resume-workspace/sourcing/ingest_harvest.py <file> <batch> --region US --workplace remote \
//       --window <window> --keywords <every search.coreKeywords entry, each in quotes>
// Output line format (ingest contract): id|title|company|location|easyApply(1/0)
async function voyagerHarvest(opts) {
  const csrf = (document.cookie.match(/JSESSIONID="?([^";]+)/) || [])[1];
  if (!csrf) return { error: "no JSESSIONID cookie; not logged in?" };
  const H = {
    "csrf-token": csrf,
    "accept": "application/vnd.linkedin.normalized+json+2.1",
    "x-restli-protocol-version": "2.0.0",
  };
  const geos = opts.geoIds || ["103644278"];
  const wts = (opts.workplaceTypes || [2]).join(",");
  const locRx = opts.locationFilter ? new RegExp(opts.locationFilter, "i") : null;
  const lines = [], seen = new Set();
  for (const geo of geos) {
  for (let page = 0; page < (opts.maxPages || 40); page++) {
    const start = page * 25;
    const query = "(origin:JOB_SEARCH_PAGE_JOB_FILTER,keywords:" +
      encodeURIComponent(opts.keywords) +
      ",locationUnion:(geoId:" + geo + ")" +
      ",selectedFilters:(timePostedRange:List(" + (opts.window || "r86400") + ")," +
      "workplaceType:List(" + wts + ")),spellCorrectionEnabled:true)";
    const url = "/voyager/api/voyagerJobsDashJobCards?decorationId=" +
      "com.linkedin.voyager.dash.deco.jobs.search.JobSearchCardsCollection-220" +
      "&count=25&q=jobSearch&query=" + query + "&start=" + start;
    let data;
    try {
      const r = await fetch(url, { headers: H });
      if (!r.ok) { lines.push("#HTTP " + r.status + " page " + page + " geo " + geo); break; }
      data = await r.json();
    } catch (e) { lines.push("#ERR " + String(e).slice(0, 80)); break; }
    // SHAPE CHANGE (see header): the JobPosting entity is now a stub carrying only
    // title + urn. Company, location and the apply method moved to JobPostingCard. The old
    // filter `$type.includes("JobPosting")` ALSO matched JobPostingCard/RelevanceFeedback/
    // Verification, so it emitted `id|title|||0` rows: blank company, blank location, and
    // easyApply hard-0 on every row. Read the card, and only the card.
    const included = data.included || [];
    const txt = (o) => (o && (o.text && o.text.text || o.text)) || "";
    const cards = included.filter((x) => (x.$type || "").endsWith("JobPostingCard"));
    if (!cards.length) break;
    let emitted = 0;
    for (const c of cards) {
      const id = String(c.jobPostingUrn || c.entityUrn || "").match(/(\d+)/);
      const title = txt(c.title).trim();
      if (!id || !title || seen.has(id[1])) continue;   // untitled card variants are dupes
      seen.add(id[1]);
      emitted++;
      const co = txt(c.primaryDescription).replace(/\|/g, "/").slice(0, 40);
      const loc = txt(c.secondaryDescription).replace(/\|/g, "/").slice(0, 40);
      if (locRx && !locRx.test(loc)) continue;   // counted as emitted above so paging continues
      // easyApply: the card carries an EASY_APPLY_TEXT footer item; offsite applies carry none.
      const ez = (c.footerItems || []).some((f) => f.type === "EASY_APPLY_TEXT") ? "1" : "0";
      lines.push([id[1], title.replace(/\|/g, "/").slice(0, 80), co, loc, ez].join("|"));
    }
    if (!emitted) break;   // page of pure repeats = end of this geo's results
    await new Promise((r) => setTimeout(r, 600 + Math.random() * 400));
  }
  }
  return lines.join("\n");
}
// Example: await voyagerHarvest({keywords:"<keyword>", geoIds:["103644278"], window:"r604800"});
