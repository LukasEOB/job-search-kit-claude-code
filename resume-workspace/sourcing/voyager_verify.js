// Canonical Voyager workplace-verify + save snippets (the "proper fix": verify before reading).
// Runs as in-browser JS in a LOGGED-IN linkedin.com tab. Never improvise a variant; edit here.
// jobState SUSPENDED counts as closed (a suspended req was once read as open), and the save path
// is the VERIFIED job-page button flow below; the Voyager save API died with HTTP 400 and its
// loop is removed.
//
// VERIFY usage: run voyagerVerify(IDS) in any logged-in tab, collect the returned JSON,
// apply with: python resume-workspace/sourcing/verify_workplace.py <results.json>
// workplaceType: 1 = On-site, 2 = Remote, 3 = Hybrid.
async function voyagerVerify(IDS) {
  const csrf = (document.cookie.match(/JSESSIONID="?([^";]+)/) || [])[1];
  if (!csrf) return { error: "no JSESSIONID cookie; not logged in?" };
  const H = {
    "csrf-token": csrf,
    "accept": "application/vnd.linkedin.normalized+json+2.1",
    "x-restli-protocol-version": "2.0.0",
  };
  const out = { verified: {}, saved: {}, errors: {} };
  for (const id of IDS || []) {
    try {
      const r = await fetch("/voyager/api/jobs/jobPostings/" + id, { headers: H });
      if (!r.ok) { out.errors[id] = "verify HTTP " + r.status; continue; }
      const s = JSON.stringify(await r.json());
      const m = s.match(/urn:li:fsd?_workplaceType:(\d)/) || s.match(/workplaceType[^0-9\[\]]{0,30}(\d)/);
      let wt = m ? +m[1] : null;
      // some postings have workplaceTypes:[] but carry the legacy boolean
      if (wt === null) {
        if (/"workRemoteAllowed"\s*:\s*true/.test(s)) wt = 2;
        else if (/"workRemoteAllowed"\s*:\s*false/.test(s)) wt = 1;
      }
      // CLOSED, closedAt, or SUSPENDED (suspended reqs are dead reqs)
      const gone = /"jobState"\s*:\s*"CLOSED"|"jobState"\s*:\s*"SUSPENDED"|"closedAt"\s*:\s*\d/.test(s);
      out.verified[id] = { wt: wt, closed: gone };
    } catch (e) { out.errors[id] = String(e).slice(0, 100); }
    await new Promise((r) => setTimeout(r, 450 + Math.random() * 300));
  }
  return out;
}

// SAVE usage (per job, VERIFIED): navigate the tab to linkedin.com/jobs/view/<id>/ first,
// then run pageSave(id). Only the returned states SAVED and ALREADY count as a save;
// record them into the results JSON as saved[id] = "SAVED" / "ALREADY" and apply with
// verify_workplace.py, which accepts those strings (and only those) as success.
// CLOSED / APPLIED / NOBTN are free intelligence: CLOSED feeds the GONE stamp, APPLIED
// feeds the applied sync. The watch recheck also uses this page-truth.
//
// click-delivery fix (found during a Saved-list cleanup, 116/116 success):
// LinkedIn's Save button ignores a bare .click(). clickHard() below delivers the full
// pointer/mouse event sequence after scrollIntoView + settle, re-querying the button,
// with up to 3 attempts. Verification semantics unchanged: only a confirmed aria-label
// flip counts.
function _findSaveBtn() {
  return [...document.querySelectorAll("button")]
    .find((x) => /Unsave the job|Save the job/.test(x.getAttribute("aria-label") || ""));
}
async function clickHard(getBtn) {
  for (let attempt = 0; attempt < 3; attempt++) {
    let b = getBtn();
    if (!b) return false;
    b.scrollIntoView({ block: "center" });
    await new Promise((r) => setTimeout(r, 600));
    b = getBtn();
    if (!b) return false;
    const rect = b.getBoundingClientRect();
    const opts = { bubbles: true, cancelable: true, view: window,
                   clientX: rect.x + rect.width / 2, clientY: rect.y + rect.height / 2 };
    for (const t of ["pointerover", "pointerenter", "pointerdown", "mousedown", "pointerup", "mouseup", "click"]) {
      b.dispatchEvent(t.startsWith("pointer") ? new PointerEvent(t, opts) : new MouseEvent(t, opts));
    }
    await new Promise((r) => setTimeout(r, 2500));
    return true;
  }
  return false;
}
async function pageSave(id) {
  let b = _findSaveBtn(), w = 0;
  while (!b && w < 8) { await new Promise((r) => setTimeout(r, 1000)); b = _findSaveBtn(); w++; }
  if (!b) {
    // LinkedIn also uses "Not currently accepting applications" - a check for the older
    // string alone reported all 8 watched ids as open. Test both, always.
    if (/No longer accepting|Not currently accepting/.test(document.body.innerText)) return id + ":CLOSED";
    if (document.body.innerText.includes("Application submitted")) return id + ":APPLIED";
    return id + ":NOBTN";
  }
  if (b.getAttribute("aria-label") === "Unsave the job") return id + ":ALREADY";
  for (let attempt = 0; attempt < 3; attempt++) {
    await clickHard(_findSaveBtn);
    await new Promise((r) => setTimeout(r, 2500));
    const after = _findSaveBtn();
    if (after && after.getAttribute("aria-label") === "Unsave the job") return id + ":SAVED";
  }
  return id + ":NOBTN";
}

// UNSAVE usage (Saved-list hygiene): navigate to the job page, run pageUnsave(id).
// Only UNSAVED counts.
async function pageUnsave(id) {
  let b = _findSaveBtn(), w = 0;
  while (!b && w < 8) { await new Promise((r) => setTimeout(r, 1000)); b = _findSaveBtn(); w++; }
  if (!b) return id + ":NOBTN";
  if (b.getAttribute("aria-label") === "Save the job") return id + ":NOTSAVED";
  for (let attempt = 0; attempt < 3; attempt++) {
    await clickHard(_findSaveBtn);
    await new Promise((r) => setTimeout(r, 2000));
    const after = _findSaveBtn();
    if (after && after.getAttribute("aria-label") === "Save the job") return id + ":UNSAVED";
  }
  return id + ":STILL-SAVED";
}
// Example: await voyagerVerify(["<jobId>", "<jobId>"]);
