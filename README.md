# ai-rollout-signals

Live page: https://ai-rollout-signals.vercel.app

I built this for my application to the GTM Engineer role at Langdock. It finds
companies in Germany, Austria and Switzerland that are getting ready to roll out
AI to their staff.

The idea is simple. A company that is hiring a KI-Manager, a Head of AI or an AI
Enablement lead has decided to do this and is about to pick a tool. The same goes
for a company whose job posts talk about "KI-Einführung" or about bringing Copilot
to every team. That is the moment to talk to them, before the choice is made.

It is one Python script. Standard library only, free public job data, no logins,
no paid APIs. Every company in the output links to the job post that put it on
the list, so nobody has to trust the score.

I have no relationship with Langdock. This is my own work, built from public data.

## The signals

| Signal | Points |
|---|---|
| Hiring someone to own AI inside the company: Head of AI, KI-Manager, KI-Beauftragte(r), Leiter KI, AI Enablement, AI Transformation, AI Governance | +40 |
| A job post talks about a rollout to staff: KI-Einführung, AI adoption across the company, Microsoft Copilot, ChatGPT Enterprise, Azure OpenAI, company-wide AI strategy, AI training for staff | +30 |
| The same post puts GDPR, DSGVO or the EU AI Act next to AI | +20 |
| Looks mid-size or large: 3+ open roles, or the post says Konzern, Mittelstand, a head count or several locations. This one is a rough guess | +10 |

Each signal counts once per company. Default cutoff is 30 points.

A few rules keep the list clean:

- A rollout only counts when the post talks about the company. "You use AI tools in
  your daily work" is a skill they want from a candidate, not a rollout, so it does
  not count. "AI-assisted coding" does not count either.
- Engineer, researcher, sales and consultant titles never count as an AI owner.
  They build or sell AI. Students and juniors in an AI enablement role count as a
  rollout, not as the owner.
- Product owner and data science titles only count as an owner when the post is
  about internal use.
- GDPR only counts within a few lines of an AI word, so the privacy notice at the
  bottom of a post does not count.

## Left out

- AI vendors and AI startups. They build AI, they don't roll it out.
- IT consultancies and system integrators that sell AI projects to clients.
- Staffing and recruiting agencies.
- Langdock and its competitors (OpenAI, Microsoft, Glean, Anthropic, Google, Aleph
  Alpha, DeepL, Mistral and a few more).

These are keyword rules, so they will miss some and catch a few they shouldn't.
The summary file says how many companies each rule removed.

## Sources

- **Arbeitnow job API.** Free, German-heavy, all kinds of roles. The script reads
  the newest pages and keeps DACH locations only.
- **Bundesagentur für Arbeit job search.** Free and public, Germany only. The script
  searches for AI owner titles (KI-Manager, Head of AI, AI Enablement and so on),
  leaves out temp agencies and private recruiters, and reads each post's full
  text. The API needs the header `X-API-Key: jobboerse-jobsuche`, which is the
  public client id the BA gives everyone, not a secret.

## Run it

```
python3 ai_rollout_signals.py
```

Output goes to `output/signals-<date>.csv` plus a short `.md` summary. Companies
already reported are saved in `state/seen.txt` and skipped next time, so each day
only shows new ones. Use `--no-dedupe` to see everything.

```
python3 ai_rollout_signals.py --pages 15 --ba-max 400 --no-dedupe
python3 ai_rollout_signals.py --no-ba          # Arbeitnow only
python3 ai_rollout_signals.py --help
```

A full run takes about five minutes because it waits between requests.

`examples/sample-run.csv` and `examples/sample-run.md` are one real run.

`.github/workflows/daily.yml` runs it every morning and commits the new results.

## The page

`python3 build_page.py --csv examples/sample-run.csv` builds `site/index.html`, the
page that is live on Vercel. You can search and filter by signal, and each company
links to its job post.

## The n8n version

`n8n/ai-rollout-signals.workflow.json` is the same flow as an n8n workflow:
schedule at 07:00, read both job sources, score in a Code node, keep 30 or more,
drop companies seen in earlier runs, post a digest to Slack and append to a Google
Sheet. Credentials are placeholders. See `n8n/README.md` for how to import it.

## What I would add with Langdock's data

- Match the list against signups and product usage. A company that scores 90 and
  already has a trial running is a different call from one that has never heard of
  Langdock.
- Route each company to the right AE by region and size, and create the account in
  the CRM with the job post attached, so the first email can point at it.
- Only after a company qualifies, find the person on the job post (the new KI-Manager
  or the Head of IT they report to) with a contact tool. Not before.
- Check which scores turned into meetings and deals, and change the points to match.
  The numbers above are my guess. The data should set them.
