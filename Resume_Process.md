# Resume Tailoring Process (SOP)

> The locked process. Every tailored resume runs through all the steps, in order.
> Companion to `Career_Bank.md`, the only source of facts.
> "You" below means the job seeker who owns this repo. "Claude" is the assistant doing the work.

---

## Step 0.0: Read first (gate)

Before any build, refresh or edit, Claude reads this file, `Career_Bank.md` and `docs/Resume_Format.md` in full and says so in its reply. A build that skipped this is invalid. Level, header, location and phrasing rules get dropped when Claude works from memory.

## Step 0.1: Scope rule

Edit only the resume you asked for. Claude never refreshes, re-renders or "improves" other resumes because a new fact landed, unless you explicitly say to batch them. New facts wait in the bank until that specific resume is next requested.

## Step 0: Job triage (before any work)

- **Status check first.** Look the company and role up in `resume-workspace/roles.tracked.json`. If the status is applied, rejected or ghosted, stop: no builds or re-renders for dead or in-flight applications unless you ask (for example, a re-apply to a new posting). When you say "I applied," "interview" or "rejected," Claude records it in the tracker immediately.
- **Fit score 0 to 10** against your target (the roles, level and domains in `profile.json` and the bank).
- **Field check:** flag roles outside your field, wrong seniority, or with requirements you have ruled out (clearance, relocation, a domain in your never-claim list). Stop and ask whether to continue.
- **Staffing-firm check** against the agency list in `profile.json`.
- **Posting tier.** Two or more of these signals make a posting Tier B: staffing agency or outsourcing firm; contract or contract-to-hire; pay unlisted or hourly; end client hidden; "multiple openings"; a JD written by an AI (coined Capitalized Terms in quotes, a bolted-on AI section); a screening question like "can you start within two weeks?"
  - **Tier A** (named employer, full-time, pay listed): full treatment. Tailored build, collateral, outreach.
  - **Tier B:** use one of your general resumes, apply fast, no bespoke collateral. At first contact ask for the end client's name and the rate. Never grant an agency exclusive right to represent you without the client's name: two agencies submitting you to the same client can disqualify you there. Log every agency and client pair in the tracker.
- **Pay check** against the floor and tiers in `profile.json`.
- **Location and travel check** against your rules in `profile.json` (remote only, hybrid in named cities, travel limit).
- If fit is under 6 or any flag is raised, Claude reports and asks before going on.

## Step 0.2: How to judge fit (work the JD, never summarize it)

Never judge a role by its title or org name. Work the JD mechanically:

1. **Count the duties by category:** domain-specific, generic for the level, and anything special (AI, compliance, people management). A title can say "Ads" while only 2 of 11 duties are about ads.
2. **Read the team-scope paragraph.** Titles mislead; the remit is the truth.
3. **Separate required from preferred gaps.** A preferred gap is cheap. A required gap is expensive, unless the clause says "and/or," which lets you satisfy either side.
4. **Discount what does not differentiate.** If two roles demand the same thing, it cannot break the tie between them.
5. **Apply your filters** from Step 0: level, pay, location, travel, ruled-out domains.
6. **Name the interview risk:** where will the interviews probe, and can you defend it there? Past interview failures count as evidence.
7. **State the flip condition:** the single fact that would change the recommendation.

## Step 0.3: One resume for several roles at one company

Some employers keep one resume per candidate. When you target two or more roles there:

- Build on the **intersection** of their required lists: the shared spine goes in the header, the summary and the top bullets.
- **Carry both domain proofs** in the middle bullets so neither reviewer finds a blank.
- Keep the header and summary **neutral between the roles**.
- Score the config against each role's keyword list separately; neither may fall below the ATS floor.

## Step 1: Extract the JD's keywords

Four buckets:
1. **Hard requirements** (years, named tools, certifications, counts). These are the ATS screening criteria.
2. **Preferred** items.
3. **Exact tool names** (Jira, Figma, Salesforce). Highest ATS weight.
4. **Action verbs** the JD uses. Mirror them as bullet openers only where the fact supports it.

Check the JD is complete. Job sites collapse sections, and "What you need" can arrive empty. Save the JD as text in `resume-workspace/inputs/` and the keywords as `resume-configs/<name>-kw.json`.

## Step 2: Gap table (bank against JD)

- Match every keyword to bank facts.
- Build the table: ✅ have it, ⚠️ have it but not phrased that way, ❌ genuine gap.
- **Show you the table before writing anything.**

## Step 3: Pick the base

Rank the existing resume configs, pick the closest one, say why.

## Step 4: Fill the gaps (ask, never invent)

- Every ❌ and ⚠️ becomes a question to you. Ask them in one batch, not one at a time.
- **Claude never invents facts, metrics, tools or framings.** If the bank does not have it and you have not confirmed it, it does not go on paper.
- Every claim must be one you can tell the story behind in an interview.
- **Metrics probe for every new fact:** ask for (a) scale (teams, people, systems touched), (b) outcome (what changed and by how much), (c) duration. A fact without a number is bankable only if you confirm no metric exists; the bank records that so it is never asked again.
- **The bank is incomplete, not exhaustive.** Before declaring something a gap, ask. You may have done it and never written it down.

## Step 5: Update the bank first

- New confirmed facts go into `Career_Bank.md` with ✅ and the date, above the INTERVIEW ONLY section (the provenance gate reads only text above it). Never overwrite an existing fact; mark it corrected or removed.
- When a JD uses a different word for something you did, add the variant next to the fact. The fact stays fixed; variants accumulate.

## Step 6: Write

**Format comes from `docs/Resume_Format.md`**, your researched format spec (section order, length, header, what your field and region expect). The rules below are about content and hold in every field.

- **Summary:** 50 to 70 words, 3 sentences. (1) Your title and thesis: the thing you do that others at your level do not, with the domain. (2) Your method, with scale. (3) Proof: 3 or 4 metrics, each correctly labeled. Banned openings: "Experienced," "Highly accomplished," "Results-driven," "Seasoned." Test: if the sentence could describe someone else, rewrite it.
- **Bullet counts are ceilings, not quotas.** Most recent two roles at most 5 to 7, middle roles at most 3, earliest 1 or 2. Bullet count is an output of selection: score every banked fact against the JD, keep only those that hit a requirement or top duty AND carry a number. Four strong bullets beat six padded ones. One no-number bullet per role at most, and only on purpose.
- **Keywords land in this order:** inside a bullet that carries a number, then the skills section, then a declared gap. Never write or stretch a bullet just to carry a keyword.
- **Ordering inside each role:** position 1 is the most JD-relevant bullet that has a number (relevance beats size). Positions 2 and 3 are the next most relevant, by size. Positions 4 and up show range. Vary the type across the top three (impact, scale, leadership). The weakest bullet goes last.
- **Bullet shape:** outcome first, mechanism second ("Cut reporting time 50% by building..."). Merge two metrics into one bullet only when one cause produced both. A semicolon usually means two facts stapled together. 18 to 36 words. Position 1 of every role carries a number.
- Every bullet answers "why did this need you?": impact and complexity, not a task list.
- **Skills section:** 4 or 5 rows at most, 8 items or fewer per row, most JD-relevant row first, only what the JD asks for and you can defend in a screen, plain nouns, no prose.
- **No jargon or internal names.** A recruiter must parse every line cold. Spell out acronyms or replace them.
- **Mirror the JD at the term level only** (tool names, method nouns, titles). Never copy its clause structure; the hiring manager wrote those sentences and will recognize them. The de-echo gate blocks 4-word phrases lifted from the JD.
- **Banned words:** hardworking, team player, passionate, responsible for, detail-oriented, results-driven, self-starter, dynamic, motivated, proven track record, synergy. "Responsible for managing" becomes "led a team of 7 that [result]."
- Past tense for roles that ended.
- **Header never downgrades:** your current level, or higher if the JD is above it. Re-derive the header for each JD.
- **Carry-over check:** any bullet reused from an older resume is re-checked against the bank word by word. Old resumes predate the process and carry inflated claims.

## Step 7: ATS pass

- Standard section headers (your format spec names them).
- Keywords placed naturally; repetition hurts on modern parsers.
- Single column, no tables or graphics, standard fonts.
- Page count checked, not assumed.

## Step 8: Deliver

- .docx unless you say otherwise.
- A keyword scorecard: hard requirements hit, remaining gaps, anything left out on purpose.

### Pre-flight: report each line in the reply, every build

```
[ ] Read-first done (Resume_Process.md, Career_Bank.md, docs/Resume_Format.md)
[ ] Scope: only the requested resume touched
[ ] Header = current level + one focus phrase
[ ] Summary 50-70 words, 3 sentences, proof labeled, no banned openings
[ ] Bullets: ceilings respected, position 1 of each role has a number, weakest last
[ ] Skills: 4-5 rows, 8 or fewer each, JD-relevant first, all defensible
[ ] No jargon, no unexplained acronyms
[ ] Carry-over bullets re-checked against the bank
[ ] Gate passed (verify_render.py) and ATS score reported
[ ] Page count checked
[ ] Application fields identified (why-us field? cover letter? screening questions?)
[ ] Swap test passed: at least one sentence impossible to reuse at another company
[ ] Every deliverable searched for em-dashes: zero
```

## Step 9: Application collateral (short answers and cover letters)

Find out which fields the application has before writing; they take different content.

### 9.1 Three layers, one home each

| Layer | What it is | Where it goes |
|---|---|---|
| **Thesis** | Your capability claim | Resume summary |
| **Target** | Why this company, specifically | Short "why us" field |
| **Origin** | The personal story behind the thesis | Cover letter |

Cramming all three into one short field makes all three weak.

### 9.2 Short "why do you want to join X" fields: 4 sentences, about 90 words, hard fail above 110

- Answer the question asked. "Why do you want to join" is not "why should we hire me."
- **No metrics.** They are on the resume already.
- **Swap test (hard gate):** if a sentence survives a find-and-replace of the company name, it is wasted. At least one sentence must be impossible to reuse elsewhere.
- Lead with the company-specific connection, then the role hook, then one line of grounding.

### 9.3 Cover letters: 150 to 200 words, 3 short paragraphs, hard fail above 220

1. Why this company, specifically. Must fail the swap test. No "I am writing to express my interest."
2. Your origin or thesis in one or two lines, then the single closest proof point.
3. Name a known gap on purpose if the JD demands something you lack, then what you bring instead. Close in one line.

### 9.4 Rules that carry over

- **No fabrication.** Do not invent stakeholders, teams or approvals to make a sentence sound bigger.
- **De-echo applies** to letters and answers too.
- **No em-dashes, anywhere.** They are the most recognized AI-writing tell. Use commas, colons, parentheses or a full stop.
- **AI tells:** participial pile-ups ("having delivered, run, and optimized"), three jargon clauses in one sentence, "actually," "truly," "perfectly aligns." Read it aloud before sending.

### 9.5 The application system decides how much to tailor

- Per-application upload (Greenhouse, Lever, Ashby): tailor fully.
- Single-profile portals (one resume for every role at that company): build on the intersection (Step 0.3) and keep the summary neutral.

---

## Standing rules

1. The bank is upstream of every resume. Change the bank first, then resumes.
2. Facts are append-only with status marks: ✅ verified, 🔵 corrected, ❌ removed, 🟡 needs confirming.
3. One resume per application when tailoring is warranted; otherwise use one of your two general resumes.
4. Inventing a fact is a process failure. When unsure, ask.
5. Sent resumes are never edited or re-rendered. The freeze gate enforces this from the tracker.

## Two lanes: tactical and strategic

Most people have two honest versions of themselves: the hands-on delivery person and the senior, organization-level person. The kit keeps one general resume for each (`lanes` in `profile.json`):

- **TAC (tactical):** for roles where the scope is one team or one program. Execution-forward bullets.
- **STRAT (strategic):** for senior roles where the scope is an organization. Outcome and scale-forward bullets.

Decide the lane from the JD's scope (how many teams, what level it reports to, what it owns), not from the title. Tailored configs for the tactical lane start with `tac-`.

## Optional: lock one summary sentence

Once you have a summary sentence that says how you work and you never want it diluted, put its required phrases in `summaryLock` in `profile.json` and set `enabled: true`. The render gate then blocks any tailored summary that drops them. Lock the meaning, not every word: list the phrases that carry the meaning and leave the verbs free.

## Summary reread rule

Before a summary reaches you, Claude shows it with its moving parts labeled and confirms that no content word repeats. The gate blocks a content word used twice. Read it aloud: a summary that passes the gate but does not sound like a person you would hire is not done.
