# LinkedIn rewrite

LinkedIn is its own surface. Recruiters search it, read it on a phone, and judge it in seconds; a resume pasted into it reads badly. This guide combines a published five-step method with rules learned rewriting a real profile.

## Sources for the method

The five-step structure comes from these posts. Read them; they explain the reasoning better than a summary can:
- Abhijay Arora Vuyyuru, "I rewrote my LinkedIn with 5 Claude prompts" (AI Action Letter #29): https://abhijayvuyyuru.substack.com/p/i-rewrote-my-linkedin-with-5-claude
- Basia Kubicka, LinkedIn post on five Claude or ChatGPT prompts for a profile: https://www.linkedin.com/posts/basiakubicka_5-claude-or-chatgpt-prompts-to-optimise-your-share-7456770486765719552-vSWs/
- Harish Kumar, LinkedIn post on five Claude prompts for a profile: https://www.linkedin.com/posts/harishkumar-sh_5-claude-prompts-to-optimise-your-linkedin-share-7456894834268614656-RX7b/

The core ideas: run it as a sequence, one section per step, never one giant prompt; aim at real job descriptions, not "a better job"; never let numbers be invented.

## Setup

1. Save your profile as a PDF (your profile, then More or Resources, then Save to PDF) into `resume-workspace/inputs/`.
2. Save 3 to 5 job descriptions for roles you actually want into the same folder.
3. Your `Career_Bank.md` is the fact source. Every number on LinkedIn must exist in the bank. In this kit, missing numbers are not left as placeholders for you to invent: Claude asks you, and banks the answer first.

## The five steps (one at a time, in this order)

1. **Audit, no rewriting.** Ask Claude for a blunt diagnostic, quoting your own lines back to you: what identity the profile projects versus what the JDs hire for; terms that appear in several JDs but not in your profile; proof points the JDs care about that you bury; whether you would appear in a recruiter's top search results for these roles; and the one sentence your profile should win on.
2. **Headline and About.** Headline: under the length limit, the role keyword the JDs share, your most credibility-dense fact first (the first 40 or so characters are all that search results show), no banned words. About: a hook as the first line (never "I'm a [title]"), what you build and at what scale, a short origin only if it differentiates you, what you want to talk about now, one specific call to action, and line breaks every sentence or two because most people read it on a phone. Ask for two or three versions.
3. **Experience, impact first.** For each role: at most three lines, each with a number, most impressive first, in the JDs' vocabulary where it is true. Write it as short narrative, not pasted resume bullets: no geography lists, end lines on the impact. Show before and after side by side.
4. **Featured and Skills.** What goes in each Featured slot and why, plus what to create for empty slots (a one-page case study, a post, a portfolio link). Skills ranked by relevance to the JDs, with the top three to put first, and any skill several JDs share that you lack.
5. **A month of posts.** A recent, coherent activity feed makes the profile believable. Twelve post ideas over four weeks: things you shipped, lessons, opinions you would defend in an interview, and behind the scenes. Each with a first line that works on a phone and one closing question.

## Rules learned the hard way

- **Order by dependency, not by page layout.** Do the Skills section first: the skill pickers on each job entry and in the About section only offer skills already in your Skills list.
- **Fill every field a section has.** Each job entry takes up to 5 attached skills; the About section shows up to 5 top skills. Empty fields are wasted search signal.
- **Check the live screen before giving click-by-click steps.** LinkedIn's interface changes often. Claude should verify each step against your current profile (or ask you what you see) rather than describe menus from memory.
- **Dates and titles must match your resume exactly.** Mismatched dates are what background checks flag. One entry per company; a promotion is a second position nested under the same company, so it shows.
- **Open to Work** lists only the titles you are targeting. Each extra title pulls recruiters for the wrong roles.
- **Certifications:** an expired certification is displayed as expired. Renew it, or list it honestly; never imply it is current.
- **Languages** need a proficiency level, and your native language belongs on the list too.
- **Recommendations, photo, banner:** zero recommendations reads as a gap. A plain, well-lit headshot with your face filling most of the frame beats a holiday photo.
- **Never-claim registry applies.** Anything in the bank's 🚫 registry stays off LinkedIn too.

## Keep it current

Keep the LinkedIn PDF, your target JDs and `docs/Voice_Profile.md` in the repo. When something new ships, ask Claude to update the affected section from the bank. Refresh the whole profile once a quarter.
