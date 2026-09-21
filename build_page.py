#!/usr/bin/env python3
"""Build a one-page site from an ai_rollout_signals.py CSV.

Usage: python3 build_page.py [--csv examples/sample-run.csv] [--out site/index.html]
Standard library only. Every company links to the job post that put it on the list.
"""
import argparse, csv, glob, html, os

HERE = os.path.dirname(os.path.abspath(__file__))

LABELS = {
    "ai_owner": ("Hiring an AI owner", "owner"),
    "rollout": ("Mentions a rollout", "roll"),
    "gdpr_ai": ("GDPR + AI", "gdpr"),
    "size": ("Mid-size or large", "size"),
}


def latest_csv():
    runs = sorted(glob.glob(os.path.join(HERE, "output", "signals-*.csv")))
    return runs[-1] if runs else os.path.join(HERE, "examples", "sample-run.csv")


def host(url):
    u = url.split("//", 1)[-1]
    return u.split("/", 1)[0].replace("www.", "")


def row_html(i, r):
    tags = "".join(
        f'<span class="tag t-{LABELS[s][1]}">{LABELS[s][0]}</span>'
        for s in r["signals"].split(";") if s in LABELS)
    why = "".join(f"<li>{html.escape(w.strip())}</li>" for w in r["why"].split("|") if w.strip())
    ev = html.escape(r["evidence_url"])
    more = [u for u in r.get("more_evidence", "").split() if u.startswith("http")][:2]
    more_html = "".join(f' · <a href="{html.escape(u)}" target="_blank" rel="noopener">another post</a>' for u in more)
    quote = (r.get("quote") or "").strip()
    quote_html = f'<blockquote>{html.escape(quote)}</blockquote>' if quote else ""
    site = r.get("website", "").strip()
    name = html.escape(r["company"])
    name_html = (f'<a href="{html.escape(site)}" target="_blank" rel="noopener">{name}</a>'
                 if site.startswith("http") else name)
    loc = html.escape(r.get("location", "").split(";")[0].strip().title())
    loc_html = f'<span class="loc">{loc}</span>' if loc else ""
    score = int(r["score"])
    return f"""
<article class="row" data-signals="{html.escape(r['signals'])}" data-name="{name.lower()}">
  <div class="rank">{i}</div>
  <div class="main">
    <h3>{name_html} {loc_html}</h3>
    <div class="tags">{tags}</div>
    <ul class="why">{why}</ul>
    {quote_html}
    <p class="ev">Job post: <a href="{ev}" target="_blank" rel="noopener">{html.escape(host(r['evidence_url']))}</a>{more_html}</p>
  </div>
  <div class="score"><span>{score}</span><small>points</small></div>
</article>"""


def build(rows, run_date):
    n = len(rows)
    counts = {k: sum(1 for r in rows if k in r["signals"].split(";")) for k in LABELS}
    body = "".join(row_html(i + 1, r) for i, r in enumerate(rows))
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI Rollout Signals</title>
<meta name="description" content="Companies in Germany, Austria and Switzerland that look ready to roll out AI to their staff, found from public job posts.">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><rect width='32' height='32' rx='7' fill='%232f5bd3'/><path d='M9 21l5-10 4 7 2-3 3 6' stroke='white' stroke-width='2.4' fill='none' stroke-linecap='round' stroke-linejoin='round'/></svg>">
<style>
:root {{
  --bg:#f7f7f5; --card:#fff; --ink:#1b1c1f; --muted:#62656d; --line:#e4e4e0;
  --accent:#2f5bd3; --owner:#b4381f; --owner-bg:#fbe9e4; --roll:#1f6b45; --roll-bg:#e3f3ea;
  --gdpr:#5a3fb0; --gdpr-bg:#eee9fb; --size:#6b5a12; --size-bg:#f6f0d6; --quote:#f1f1ee;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    --bg:#131417; --card:#1c1d21; --ink:#ececea; --muted:#a2a5ad; --line:#2d2f35;
    --accent:#7d9cff; --owner:#ff9b84; --owner-bg:#3a211b; --roll:#7fd6a6; --roll-bg:#17302a;
    --gdpr:#bba6ff; --gdpr-bg:#2a2340; --size:#e6cf73; --size-bg:#332c12; --quote:#23252a;
  }}
}}
* {{ box-sizing:border-box }}
body {{ margin:0; background:var(--bg); color:var(--ink);
  font:16px/1.55 ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }}
a {{ color:var(--accent) }}
.wrap {{ max-width:880px; margin:0 auto; padding:40px 16px 64px }}
header h1 {{ font-size:30px; line-height:1.2; margin:0 0 12px; letter-spacing:-.01em }}
header p {{ color:var(--muted); margin:0 0 10px; max-width:680px }}
.stats {{ display:flex; gap:12px; flex-wrap:wrap; margin:24px 0 }}
.stat {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:12px 16px; min-width:150px; flex:1 1 150px }}
.stat b {{ display:block; font-size:24px }}
.stat span {{ color:var(--muted); font-size:14px }}
.controls {{ display:flex; gap:8px; flex-wrap:wrap; margin:8px 0 16px; align-items:center }}
.controls input {{ flex:1 1 220px; padding:9px 12px; border:1px solid var(--line); border-radius:8px;
  background:var(--card); color:var(--ink); font:inherit }}
.controls button {{ padding:8px 12px; border:1px solid var(--line); border-radius:999px; background:var(--card);
  color:var(--ink); font:inherit; font-size:14px; cursor:pointer }}
.controls button[aria-pressed="true"] {{ background:var(--ink); color:var(--bg); border-color:var(--ink) }}
.row {{ display:grid; grid-template-columns:36px 1fr 70px; gap:12px; background:var(--card);
  border:1px solid var(--line); border-radius:12px; padding:16px; margin-bottom:10px }}
.rank {{ color:var(--muted); font-variant-numeric:tabular-nums; padding-top:2px }}
.row h3 {{ margin:0 0 6px; font-size:18px }}
.row h3 a {{ color:var(--ink); text-decoration:none }}
.row h3 a:hover {{ text-decoration:underline }}
.loc {{ font-size:13.5px; font-weight:400; color:var(--muted); margin-left:4px }}
.tags {{ display:flex; gap:6px; flex-wrap:wrap; margin-bottom:8px }}
.tag {{ font-size:12.5px; padding:2px 8px; border-radius:999px }}
.t-owner {{ color:var(--owner); background:var(--owner-bg) }}
.t-roll {{ color:var(--roll); background:var(--roll-bg) }}
.t-gdpr {{ color:var(--gdpr); background:var(--gdpr-bg) }}
.t-size {{ color:var(--size); background:var(--size-bg) }}
.why {{ margin:0 0 6px; padding-left:18px; color:var(--muted); font-size:14.5px; overflow-wrap:anywhere }}
blockquote {{ margin:6px 0 8px; padding:8px 12px; background:var(--quote); border-radius:8px;
  font-size:14px; color:var(--ink); overflow-wrap:anywhere }}
.ev {{ margin:0; font-size:14px; overflow-wrap:anywhere }}
.score {{ text-align:right }}
.score span {{ font-size:26px; font-weight:650; font-variant-numeric:tabular-nums }}
.score small {{ display:block; color:var(--muted); font-size:12px }}
section.how {{ margin-top:40px; border-top:1px solid var(--line); padding-top:24px }}
section.how h2 {{ font-size:20px; margin:0 0 10px }}
section.how p {{ max-width:680px }}
table {{ border-collapse:collapse; width:100%; max-width:560px; font-size:15px }}
td, th {{ text-align:left; padding:6px 8px; border-bottom:1px solid var(--line) }}
td:last-child {{ text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap }}
footer {{ margin-top:32px; color:var(--muted); font-size:14px }}
.empty {{ display:none; color:var(--muted); padding:16px 0 }}
@media (max-width:560px) {{
  .row {{ grid-template-columns:1fr 56px }}
  .rank {{ display:none }}
  header h1 {{ font-size:25px }}
}}
</style>
</head>
<body>
<div class="wrap">
<header>
  <h1>Which companies in DACH are getting ready to roll out AI?</h1>
  <p>I built this for my application to the GTM Engineer role at Langdock. It's a list of companies in Germany, Austria and Switzerland that are hiring someone to own AI, or whose job posts talk about bringing AI to their staff. A company at that point is choosing a tool right now. It's built from public job posts only. Every company links to the job post that put it on the list, so you don't have to trust the score.</p>
  <p>I have no relationship with Langdock. This is my own work from public data. Run from {html.escape(run_date)}.</p>
</header>

<div class="stats">
  <div class="stat"><b>{n}</b><span>companies scored 30+</span></div>
  <div class="stat"><b>{counts['ai_owner']}</b><span>hiring an AI owner</span></div>
  <div class="stat"><b>{counts['gdpr_ai']}</b><span>mention GDPR with AI</span></div>
</div>

<div class="controls">
  <input id="q" type="search" placeholder="Search a company" aria-label="Search a company">
  <button data-f="" aria-pressed="true">All</button>
  <button data-f="ai_owner" aria-pressed="false">Hiring an AI owner</button>
  <button data-f="rollout" aria-pressed="false">Mentions a rollout</button>
  <button data-f="gdpr_ai" aria-pressed="false">GDPR + AI</button>
</div>

<main id="list">{body}
</main>
<p class="empty" id="empty">Nothing matches that.</p>

<section class="how">
  <h2>How the points work</h2>
  <table>
    <tr><td>Hiring someone to own AI inside the company (KI-Manager, Head of AI, AI Enablement, AI Transformation)</td><td>+40</td></tr>
    <tr><td>A job post talks about a rollout to staff (KI-Einführung, Microsoft Copilot, ChatGPT Enterprise, company-wide AI)</td><td>+30</td></tr>
    <tr><td>The same post puts GDPR, DSGVO or the EU AI Act next to AI</td><td>+20</td></tr>
    <tr><td>Looks mid-size or large (3+ open roles, or the post says Konzern, Mittelstand or a head count). A rough guess</td><td>+10</td></tr>
  </table>
  <p>Each signal counts once per company. AI vendors, AI startups, IT consultancies, recruiting agencies, Langdock and its competitors are left out: they build or resell AI, they don't roll it out to their own people.</p>
  <h2>Why these signals</h2>
  <p>A company that hires a KI-Manager or an AI Enablement lead has a budget and one person whose job is to pick the tools. That person will compare options in their first months, so that is the week to talk to them. A post that mentions Copilot or ChatGPT Enterprise tells you what they have now, which is the thing you'd replace. And a company that writes DSGVO and AI in the same sentence cares where the data sits, which is where an EU-hosted platform wins. The points are my guess. With real deal data they should be tuned to what actually turned into meetings.</p>
</section>

<footer>
  Karim Fakhri · <a href="https://github.com/kari-fakh12/ai-rollout-signals">Code on GitHub</a> ·
  <a href="https://www.linkedin.com/in/karim-fakhrii">LinkedIn</a>
</footer>
</div>
<script>
(function () {{
  var q = document.getElementById('q'), rows = [].slice.call(document.querySelectorAll('.row')),
      btns = [].slice.call(document.querySelectorAll('.controls button')), f = '';
  function apply() {{
    var t = q.value.trim().toLowerCase(), shown = 0;
    rows.forEach(function (r) {{
      var ok = (!t || r.dataset.name.indexOf(t) > -1) && (!f || r.dataset.signals.split(';').indexOf(f) > -1);
      r.style.display = ok ? '' : 'none'; if (ok) shown++;
    }});
    document.getElementById('empty').style.display = shown ? 'none' : 'block';
  }}
  q.addEventListener('input', apply);
  btns.forEach(function (b) {{ b.addEventListener('click', function () {{
    f = b.dataset.f; btns.forEach(function (x) {{ x.setAttribute('aria-pressed', x === b); }}); apply();
  }}); }});
}})();
</script>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--csv", default=None)
    ap.add_argument("--out", default=os.path.join(HERE, "site", "index.html"))
    a = ap.parse_args()
    path = a.csv or latest_csv()
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    rows.sort(key=lambda r: (-int(r["score"]), r["company"].lower()))
    run_date = rows[0]["found"] if rows else "-"
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as fh:
        fh.write(build(rows, run_date))
    print(f"wrote {a.out} from {os.path.relpath(path, HERE)} ({len(rows)} companies)")


if __name__ == "__main__":
    main()
