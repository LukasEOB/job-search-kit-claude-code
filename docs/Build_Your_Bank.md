# Build your Career Bank

The bank (`Career_Bank.md`) is the heart of the kit. Every resume line must quote it, the gates check that, and the job board uses it to score how well you match a posting. A good bank takes two or three sessions with Claude. It is worth it: after that, a tailored resume takes minutes and never contains anything you cannot defend.

The example bank in the repo belongs to an invented person, Alex Example. Keep its structure and replace its content.

## Step 1: Give Claude everything you have

Put these in an `inputs/` folder inside `resume-workspace/` (create it if missing), then tell Claude to read them:
- Every old resume version you can find, even bad ones. Different versions remember different facts.
- Your LinkedIn profile as a PDF (on your profile: More, then Save to PDF).
- Performance reviews, promotion write-ups, award citations, project one-pagers, anything with numbers.
- Things you wrote yourself in your own voice: cover letters, emails you were proud of, posts.

Then say: *"Read everything in inputs/. Draft Career_Bank.md in the example's structure. Mark every fact 🟡 (needs confirming). Do not invent anything. List the questions you need me to answer, role by role."*

## Step 2: Answer the questions, one role at a time

Claude interviews you. These are the questions it should ask for every role, plus the ones about you as a whole. Answer out loud or in rough notes; Claude turns them into bank entries and shows you each one before marking it ✅.

### For each role

1. **The basics.** Company, your exact title or titles, start and end month and year. Any promotion, with its date. Contract or employee?
2. **The company in one line.** What does it sell, to whom, at what scale (users, revenue, employees)?
3. **Your remit.** What did you own? How many people did you manage directly, and how many did you work with or align without managing them? Who did you report to (their title)?
4. **Your three to five biggest pieces of work.** For each: what was the problem, why did it need someone like you, and what exactly did you do?
5. **The numbers.** For each piece of work: how big was it (teams, people, systems, money), what changed and by how much, and over what period?
6. **What each number measures.** Cost avoided or cost cut? Revenue or savings? People reached, aligned or managed? Could you explain how it was measured if an interviewer asked? If not, say so; the bank records it.
7. **Your part, honestly.** Did you lead it, run delivery on it, or support it? Which verb is true? What did other teams own?
8. **Tools and methods.** What did you use hands-on, every day? What was only around you?
9. **The story behind it.** One situation you would tell in an interview: what went wrong or was hard, and what you did.

### About you as a whole

10. **Your thesis.** What do people come to you for that they do not go to others at your level for? (This becomes sentence 1 of your summary.)
11. **How you work.** In one sentence, what do you do for a team that makes it better? (Sentence 2 of your summary. You can lock it later.)
12. **Credentials.** Degrees (field, school, years), certifications (active or lapsed, dates), languages and how well you speak them.
13. **Never on paper.** What have old resumes or LinkedIn said that you cannot defend? What have you never done that people assume you have? Every answer becomes a 🚫 line in the never-claim registry and is enforced from then on.
14. **Interview only.** What is true but must never be written down (confidential client names, sensitive numbers, personal context)? It goes in the INTERVIEW ONLY section, which the gates never read for paper.
15. **Your search.** Which roles and levels, which regions, remote or hybrid, your pay floor, industries you will not work in, companies you would love to work for. (These go into `profile.json`, not the bank.)

### Rules Claude follows while interviewing you

- No number goes in without scale, outcome and period, unless you confirm none exists; then the bank says so and never asks again.
- Facts are never overwritten. A corrected fact gets 🔵 and the date; a retired one gets ❌ and stays visible so it is never reintroduced.
- When an old resume says something the bank does not support, Claude asks rather than copies.
- Claude asks in batches, not one question at a time, and shows you the bank entry it wrote before marking it ✅.

## Step 3: Status marks and structure

| Mark | Meaning |
|---|---|
| ✅ | Verified by you |
| 🔵 | Corrected (rewritten after your feedback) |
| ❌ | Removed, kept visible so it never comes back |
| 🟡 | Needs confirming |

Keep this order (the gates depend on it):
1. Header and status legend
2. Contact and top line, plus your "commonly mislabeled" numbers
3. One section per role, newest first, each bullet tagged (`[Delivery]`, `[AI/ML]`, `[Cost]`...) so Claude can pull by theme
4. Education and certifications
5. Open questions 🟡
6. `## 🔒 INTERVIEW ONLY` (everything below this line is invisible to the provenance gate)
7. `## 🚫 NEVER-CLAIM REGISTRY` with lines in the exact form `` - 🚫 `phrase` : reason ``

New facts that may go on paper are always added ABOVE the INTERVIEW ONLY heading.

## Step 4: Your voice

Ask Claude: *"From the things I wrote myself in inputs/, write docs/Voice_Profile.md: how I sound, the words I use, the words I never use, and what in my old summaries sounds generic."* Summaries and cover letters then have a voice source the way bullets have the bank. A common finding: people's own old summaries are their least human writing. Model on how you talk, not on how you used to write resumes.

## Step 5: Your two general resumes

Once the bank holds, ask Claude for your two general resumes (see "Two lanes" in `Resume_Process.md`): a tactical one for hands-on roles and a strategic one for senior roles. Both are bank-anchored and gate-passing. Put their file names in `profile.json` under `lanes`. Every untailored application uses one of them.

## Keep it alive

Every time an interview, a JD or a conversation surfaces a new fact, tell Claude: *"Bank this: ..."* It goes in with ✅ and the date. Every time you catch a wrong claim, say *"Never put X on paper"* and it goes in the registry.
