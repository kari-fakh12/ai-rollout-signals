# n8n version

`ai-rollout-signals.workflow.json` does the same thing as the Python script, as an
n8n workflow that runs every morning and posts the new companies to Slack.

## What it does

1. **Every day 07:00** (Schedule Trigger, Berlin time).
2. Two branches run side by side:
   - **Arbeitnow**: a Code node makes pages 1 to 10, and an HTTP Request node reads each page of the Arbeitnow job API.
   - **Bundesagentur für Arbeit**: a Code node lists the searches (KI-Manager, Head of AI, AI Enablement, Microsoft Copilot and so on), an HTTP Request node runs them, a Code node keeps only AI job titles, and a second HTTP Request node reads each job's full text.
3. **All job posts** (Merge) puts both branches together.
4. **Score companies** (Code, JavaScript) is a port of the Python rules: DACH filter, the four signals and their points, and the exclusions (AI vendors, agencies, consultancies, Langdock and competitors).
5. **Score 30 or more** (Filter).
6. **Only new companies** (Remove Duplicates, "remove items repeated in previous executions" on the company key). A company shows up once, the first day it qualifies.
7. **Build digest** (Code) writes one Slack message with the top 20, and **Post to Slack** sends it.
8. **Append to Google Sheet** keeps the full list, one row per company.

## Import it

1. In n8n: **Workflows > Import from File**, pick `ai-rollout-signals.workflow.json`.
   It needs a recent n8n (1.60 or newer) for the Remove Duplicates option used here.
2. Open **Post to Slack**, pick your own Slack credential and channel. The file has
   placeholders only, no tokens and no webhook.
3. Open **Append to Google Sheet**, pick your Google credential, set the sheet ID and
   make a tab called `signals`. Or delete the node if you only want Slack.
4. Run it once by hand with **Execute workflow** to check it, then switch it to active.

The Bundesagentur API needs the header `X-API-Key: jobboerse-jobsuche`. That is the
public client id the BA publishes for everyone (https://jobsuche.api.bund.dev), not
a secret, so it is already filled in.

## Differences from the Python script

- The Python script folds related names into one company ("SIGNAL IDUNA
  Krankenversicherung" into "SIGNAL IDUNA"). The n8n version does not, so the same
  group can show up twice.
- The Python script keeps a short quote from each post. The n8n digest links to the post instead.
- Everything else (signals, points, exclusions) is the same logic.
