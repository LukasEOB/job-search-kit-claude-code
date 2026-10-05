# Job Search Kit

A job search run with Claude Code. You build a bank of everything you have actually done, and Claude tailors a resume to each job from that bank only, behind automatic checks that block invented claims, AI-sounding phrases and keyword gaps. Every morning, a routine sweeps LinkedIn for new jobs, scores each one against your bank, reads the best ones, and puts them on a job board in your browser.

It was built and used for a real senior search, then emptied of that person's data. The example person in it, Alex Example, is invented.

## What is in here

| Piece | What it does | Where |
|---|---|---|
| **Career Bank** | Every fact you can defend, with status marks. The only source for anything on paper. | `Career_Bank.md`, guide in `docs/Build_Your_Bank.md` |
| **Tailoring process** | The step-by-step method Claude follows for every resume, cover letter and application answer. | `Resume_Process.md` |
| **Format spec** | Your researched resume format (it differs by field and country). | `docs/Resume_Format.md` |
| **Gates** | Hooks that block a render or a file when a rule is broken: unsourced bullet, never-claim phrase, em-dash, banned phrase, summary too long, JD phrases copied, keyword coverage under 85%, overwriting your hand edits, touching a sent application. | `.claude/hooks/` |
| **Job sweep and board** | Harvest, score, verify, read and save jobs; an HTML board with pay (P), fit (J) and mission (M) tags. | `resume-workspace/sourcing/`, guide in `Sourcing_Process.md` there |
| **Morning routine** | The scheduled prompt that runs the sweep daily. | `docs/Morning_Routine.md` |
| **LinkedIn rewrite** | A five-step method plus rules learned the hard way. | `docs/LinkedIn.md` |
| **Interview prep** | One running prep file per company, STAR stories, questions to ask. | `docs/Interview_Prep.md` |
| **Rules for Claude** | Loaded automatically every session. | `CLAUDE.md` |
| **Your settings** | Name, your two general resumes (lanes), resume-check thresholds, search keywords, regions, scoring lists, pay tiers. | `profile.json` (from `profile.example.json`) |

## What you need

- **The Claude desktop app** (Code tab) or Claude Code in a terminal, on a paid Claude plan.
- **Git**, **Python 3.10+** and **Node.js 18+**.
- **Chrome with the Claude in Chrome extension**, logged in to LinkedIn, for the job sweep. The resume side works without it.

## Set up (first day, about two hours plus bank sessions)

**1. Get the repo.** On GitHub click **"Use this template"** and choose **Private** (do not use Fork: a fork of a public repo stays public). Then clone your copy. Or download the ZIP and keep it local; git works fine without GitHub.

**2. Fill in your settings.** Copy `profile.example.json` to `profile.json` and replace Alex Example's details with yours. Every section has `_help` notes explaining each key.

**3. Install the renderer.**
```
cd resume-workspace
npm install
cd ..
python resume-workspace/smoke_test.py
```
The smoke test renders Alex Example's resume through every gate. It must end with `SMOKE TEST: PASS`.

**4. Build your bank.** Open the repo in Claude's Code tab and follow `docs/Build_Your_Bank.md`. Start with: *"Read CLAUDE.md, then help me build my Career Bank from the files in resume-workspace/inputs/."* Replace Alex's bank with yours as you go.

**5. Research your resume format.** Follow `docs/Resume_Format.md`.

**6. Make your two general resumes** (tactical and strategic, see `Resume_Process.md`) and put their file names in `profile.json` under `lanes`.

**7. First job sweep, by hand.** Fill in `search`, `scoring` and `pay` in `profile.json`. If you target a different job family than program management, rewrite the title and domain lists in `scoring`; each has a `_help` note with examples for other fields. Then, with Chrome logged in to LinkedIn, say: *"Run the morning routine in docs/Morning_Routine.md once, step by step, and stop after each step to show me the result."* Open `resume-workspace/sourcing/job-board-v2.html` when it finishes.

**8. Schedule it.** Follow "Set it up" in `docs/Morning_Routine.md`.

## Daily use: what to say to Claude

| You want | Say |
|---|---|
| A tailored resume | *"Tailor a resume for this job: <link or pasted JD>."* Claude triages it, shows a gap table, asks what it needs, banks your answers, builds the config, passes the gates, renders the .docx. |
| Which resume to send | *"Should I tailor this or send a general one? <link>"* |
| An application answer or cover letter | Paste the question. The formats and limits are in `Resume_Process.md` Step 9. |
| Record an application | *"I applied to <company>."* It goes in the tracker, and that resume is frozen. |
| Add a fact | *"Bank this: ..."* |
| Ban a claim forever | *"Never put X on paper."* It goes in the never-claim registry. |
| Interview prep | *"I have an interview with <company> on <date>; start the prep file."* Then dictate your notes after each round. |
| A reply to a recruiter | Paste the email. Claude answers only what it asks, through the channel it gives. |

## Keeping your data private

- Keep your copy of the repo **private**. Your bank, tracker, job pool and reports are committed on purpose (the morning routine commits every day, and the history is your audit trail), so a public copy would publish your whole search.
- Never make your copy public later, and never push it to someone else's repo.
- Before a file goes to a company, Claude lists anything hidden in it (speaker notes, comments, tracked changes) and makes a clean copy.

## Checks you can run any time

```
python resume-workspace/smoke_test.py                    # resume gates and renderer
python resume-workspace/sourcing/pipeline_selftest.py    # job sweep contracts
python .claude/hooks/verify_board.py --check             # board invariants on your live data
python .claude/hooks/verify_render.py resume-workspace/resume-configs/<name>.json
```

## When something blocks you

The gates print what failed and how to fix it. Fix the content, never the gate. If a rule truly does not fit you (a different summary length for your field, a different keyword floor), change it on purpose in `profile.json` under `gates`, and write down why.
