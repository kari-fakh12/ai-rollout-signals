#!/usr/bin/env python3
"""
AI rollout signals.

Finds companies in Germany, Austria and Switzerland that look like they are about
to roll out AI to their staff, and scores them. Built from public job posts only.

Signals, each counted once per company:
  1. They are hiring someone to own AI inside the company (Head of AI,
     KI-Manager, AI Enablement, AI Transformation Lead and so on).
  2. A job post talks about an actual rollout: KI-Einführung, AI adoption,
     Microsoft Copilot, ChatGPT Enterprise, Azure OpenAI, generative KI for staff.
  3. The same post puts GDPR / DSGVO / EU AI Act next to AI.
  4. The company looks mid-size or large (a heuristic, see size_hint()).

Left out: AI vendors and AI startups (they build AI, they don't roll it out),
staffing and recruiting agencies, AI and IT consultancies, Langdock and its
competitors.

Sources, both free and public:
  - the Arbeitnow job board API (German-heavy, all kinds of roles), read page by page
  - the Bundesagentur für Arbeit job search (Germany), searched for AI-owner titles
Standard library only, no logins, no paid APIs. Every row keeps the URL of the
job post that earned the points. Companies already reported are remembered in
state/seen.txt.

Usage:
  python3 ai_rollout_signals.py
  python3 ai_rollout_signals.py --pages 20 --no-dedupe
  python3 ai_rollout_signals.py --no-ba             # Arbeitnow only
  python3 ai_rollout_signals.py --cache .cache      # keep raw responses, re-score offline
"""
import argparse, csv, html, json, os, re, sys, time, urllib.error, urllib.request
from collections import defaultdict
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
SEEN = os.path.join(HERE, "state", "seen.txt")
UA = "ai-rollout-signals/1.0 (+https://github.com/kari-fakh12/ai-rollout-signals)"
API = "https://www.arbeitnow.com/api/job-board-api?page={}"

POINTS = {
    "ai_owner": 40,     # hiring someone to own AI inside the company
    "rollout": 30,      # a job post talks about rolling AI out internally
    "gdpr_ai": 20,      # GDPR / DSGVO / EU AI Act next to AI in the same post
    "size": 10,         # looks mid-size or large (heuristic)
}
ORDER = ["ai_owner", "rollout", "gdpr_ai", "size"]

STATUS = {}   # source -> {"ok": n, "fail": n, "notes": [..]}


def note(source, ok=True, msg=None):
    s = STATUS.setdefault(source, {"ok": 0, "fail": 0, "notes": []})
    s["ok" if ok else "fail"] += 1
    if msg and msg not in s["notes"] and len(s["notes"]) < 5:
        s["notes"].append(msg)


FILLER = {"gmbh", "ag", "se", "kg", "kgaa", "co", "mbh", "ug", "haftungsbeschränkt", "inc", "ltd", "llc", "group",
          "gruppe", "holding", "personio", "ek", "e", "k", "v", "ev", "a", "g", "oh", "ohg", "recruiting", "de",
          "deutschland", "germany", "english", "careers", "karriere", "jobs", "mitarbeit", "zentrale", "und", "&"}


def tokens(name):
    """Name as a list of lowercase words, legal forms and filler dropped."""
    n = (name or "").lower().split(" - ")[0]
    return [t for t in re.split(r"[^a-z0-9äöüß]+", n) if t and t not in FILLER]


def key_of(name):
    """Company key for dedupe: lowercase letters and digits, legal form dropped."""
    return "".join(tokens(name))


def clean_company(name, title=""):
    """Tidy a company name from a job board. Never returns an email address."""
    name = re.sub(r"\s+", " ", name or "").strip()
    if "@" in name:
        name = name.split("@", 1)[1]            # bewerbung@firma.de -> firma.de
    if re.match(r"^(abteilung|bereich|personalabteilung)\b", name, re.I) and "," in title:
        name = title.rsplit(",", 1)[1].strip()  # "Abteilung 1" -> employer named in the title
    name = re.split(r"\s+vertreten durch\s+", name, flags=re.I)[0]
    if "," in name and len(name) > 30:
        name = name.split(",")[0]               # "Firma GmbH Zentrale Berlin, Park Corner" -> "Firma GmbH Zentrale Berlin"
    return name.strip()


def plain(text):
    text = html.unescape(text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def get_json(url, headers=None, tries=3):
    last = None
    h = {"User-Agent": UA, "Accept": "application/json"}
    h.update(headers or {})
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=h)
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.load(r), None
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}"
            if e.code in (400, 401, 404, 410):
                return None, last
        except Exception as e:
            last = type(e).__name__ + ": " + str(e)[:80]
        time.sleep(4 * (i + 1))
    return None, last


# ---------------------------------------------------------------- DACH filter

DACH_CODES = re.compile(r"\b(DE|AT|CH|DEU|AUT|CHE)\b")
DACH_WORDS = re.compile(
    r"\b(deutschland|germany|dach|österreich|oesterreich|austria|schweiz|switzerland|suisse|svizzera)\b|"
    r"\b(berlin|m[üu]nchen|munich|hamburg|k[öo]ln|cologne|frankfurt|stuttgart|d[üu]sseldorf|leipzig|dresden|"
    r"hannover|hanover|n[üu]rnberg|nuremberg|bremen|essen|dortmund|bochum|duisburg|bonn|mannheim|karlsruhe|"
    r"heidelberg|m[üu]nster|augsburg|wiesbaden|mainz|darmstadt|freiburg|aachen|kiel|l[üu]beck|rostock|"
    r"potsdam|magdeburg|erfurt|jena|halle|chemnitz|kassel|bielefeld|paderborn|osnabr[üu]ck|oldenburg|"
    r"braunschweig|wolfsburg|g[öo]ttingen|regensburg|ingolstadt|w[üu]rzburg|ulm|heilbronn|pforzheim|"
    r"reutlingen|t[üu]bingen|konstanz|saarbr[üu]cken|trier|koblenz|ludwigshafen|wuppertal|krefeld|"
    r"m[öo]nchengladbach|gelsenkirchen|oberhausen|hagen|hamm|siegen|leverkusen|neuss|ratingen|hürth|"
    r"garching|gilching|b[öo]blingen|sindelfingen|walldorf|erlangen|f[üu]rth|bayreuth|bamberg|passau|"
    r"rosenheim|landshut|dingolfing|eschborn|offenbach|bad homburg|unterf[öo]hring|ismaning|"
    r"bayern|bavaria|baden-w[üu]rttemberg|nordrhein|north rhine|hessen|hesse|sachsen|saxony|niedersachsen|"
    r"th[üu]ringen|brandenburg|schleswig|rheinland|saarland|mecklenburg|"
    r"wien|vienna|graz|linz|salzburg|innsbruck|klagenfurt|"
    r"z[üu]rich|basel|bern|genf|geneva|gen[eè]ve|lausanne|luzern|lucerne|zug|winterthur|st\. ?gallen|lugano)\b",
    re.I)
NON_DACH = re.compile(
    r"\b(london|uk|united kingdom|england|manchester|paris|france|amsterdam|netherlands|nederland|"
    r"madrid|barcelona|spain|lisbon|portugal|milan|italy|dublin|ireland|warsaw|poland|prague|"
    r"stockholm|copenhagen|oslo|helsinki|brussels|belgium|us|usa|united states|canada|new york|"
    r"remote-us|india|singapore|dubai)\b", re.I)
GERMAN_WORDS = re.compile(r"\b(und|wir|sie|die|der|das|für|mit|unser|unsere|ihre|deine|bei)\b", re.I)


def is_german_text(text):
    return len(GERMAN_WORDS.findall(text[:3000])) >= 25


def is_dach(location, text):
    loc = location or ""
    if DACH_WORDS.search(loc) or DACH_CODES.search(loc):
        return True
    if NON_DACH.search(loc):
        return False
    # Empty, "Remote", "Homeoffice" or a small town not in the list: keep it if
    # the post itself is written in German.
    return is_german_text(text)


# ---------------------------------------------------------------- signals

# Job titles that mean "this person owns AI inside the company".
OWNER_TITLE = re.compile(
    r"\bhead of (ai|a\.i\.|artificial intelligence|genai|generative ai|ki|künstliche intelligenz)\b|"
    r"\b(leiter|leiterin|leitung|referent|referentin|manager|managerin|koordinator|koordinatorin|"
    r"beauftragte[rn]?|verantwortliche[rn]?)\s+(für\s+)?(ki|künstliche intelligenz|ai)\b|"
    r"\b(ki|ai|genai|gen ai)[- ](lead|manager|managerin|beauftragte[rn]?|officer|champion|koordinator\w*|"
    r"referent\w*|verantwortliche[rn]?|owner|program(me)? (lead|manager)|project manager|projektleit\w*|"
    r"transformation\w*|enablement|adoption|governance|strategy|strategie|strateg\w+|innovation|"
    r"integration (lead|manager)|automation (lead|manager|specialist|spezialist\w*)|operations|"
    r"transformations?manager\w*|change)\b|"
    r"\b(ki|ai)[- ]?(&|und|and)\s+(automation|automatisierung|digitalisierung|digital\w*)\s+(lead|manager\w*|specialist|spezialist\w*|owner|operations)\b|"
    r"\bgenerative ai lead\b|\bgenai lead\b|"
    r"\b(ai|ki)[- ]transformation\b|\btransformation\w* (lead|manager\w*|&)\s*(ai|ki)?\b(?=.*\b(ai|ki)\b)|"
    r"\b(enablement|adoption|innovation|governance|strategy|strategie|automation|automatisierung|operations)\b[^|]{0,25}\b(ai|ki)\b|"
    r"\bproduct owner\b[^|]{0,25}\b(ai|ki)\b|\b(ai|ki)\b[^|]{0,15}\bproduct owner\b",
    re.I)
# Titles that build AI rather than roll it out. These never count as an owner.
BUILDER_TITLE = re.compile(
    r"\b(engineer|engineering|entwickler\w*|developer|scientist|research\w*|forscher\w*|architect\w*|"
    r"annotation|trainer|tester|evaluation|labell?ing|data annotator|phd|compiler|sales|account executive|"
    r"business development|vertrieb\w*|marketing|seo|geo|content|creator|video\w*|designer|recruit\w*|"
    r"consultant|\w*berater\w*|\w*beratung|presales|pre-sales|solution\w*|social media|performance|growth|"
    r"search|voice|vision|robotics|quant\w*|account manager|key account|security|cyber\w*|jurist\w*|"
    r"politi\w*|policy|public affairs|für (medienhäuser|kunden|mandanten))\b", re.I)
# Data science and analytics leads often run models, not a rollout to staff.
# They only count as an owner when the post also talks about a rollout.
DATA_TITLE = re.compile(r"\b(data science|analytics|data scientist|machine learning|ml)\b", re.I)
PRODUCT_TITLE = re.compile(r"\bproduct (owner|manager|lead)\b|\bproduktmanager\w*\b", re.I)
JUNIOR_TITLE = re.compile(r"\b(werkstudent\w*|working student|\w*praktik\w*|intern|internship|trainee|"
                          r"thesis|abschlussarbeit|azubi|ausbildung|student|junior|dual\w*|volontär\w*)\b", re.I)
TITLE_AI = re.compile(r"\b(ai|a\.i\.|ki|künstliche intelligenz|artificial intelligence|genai|llm)\b", re.I)
DIGITAL_TRANSFORMATION = re.compile(r"digital\w*[- ]transformation|transformation\w*manager|digitalisierung", re.I)

# What an AI rollout to staff sounds like in a job post. Only organization-level
# phrasing counts. "You use AI tools in your daily work" is a skill the company
# wants in a candidate, not a rollout, so it does not count.
# "AI-assisted coding" or "AI-generated code" is about building software, not
# about giving staff an AI tool, so those forms are skipped.
AI = r"(?:ki|ai|a\.i\.|genai|gen ai|generative[nrs]? (?:ki|ai)|künstliche[nr]? intelligenz|llms?|chatgpt|copilot)"\
     r"(?![- ](?:assisted|generated|powered|driven|native|based|basiert\w*|coding|code|search|engineer\w*|ml\b))"
AIX = AI + r"(?:[- ](?:tools?|lösungen|anwendungen|assistenten|assistants?|plattform|platform|initiativen|"\
           r"initiatives|projekte|projects|use[- ]cases|agenten|agents|hub|strategie|strategy|transformation|"\
           r"adoption|enablement|programm?e?|workflows?))?"
OUR = r"(?:our|unsere[nmrs]?|the company'?s|des unternehmens|im unternehmen|konzernweit\w*|unternehmensweit\w*)"
STAFF = r"(?:mitarbeitende\w*|mitarbeiter\w*|beschäftigte\w*|kolleg\w+|belegschaft|employees|staff|workforce|"\
        r"colleagues|fachbereiche\w*|fachabteilungen|abteilungen|teams|business units|geschäftsbereiche\w*|"\
        r"portfolio companies|tochtergesellschaften|subsidiaries|standorte)"
ROLLOUT_TERMS = [
    (r"\bki[- ]einführung\b|\beinführung (?:von |der |neuer )?(?:generativer |generativen )?(?:ki|künstlicher intelligenz|ai)\b|"
     r"\beinführung (?:von |der |neuer )?(?:ki|ai)[- ]\w+|\b(?:ki|ai)[- ]?(?:tools?|lösungen|anwendungen|assistenten)?\s*"
     r"(?:im unternehmen |bei uns )?einzuführen\b|\beinsatz von (?:ki|künstlicher intelligenz) (?:im unternehmen|bei uns)\b",
     "KI-Einführung"),
    (r"\b(?:ai|ki|genai)[- ]adoption\b[^.]{0,80}\b(?:across|throughout|within|in) (?:the |our )?"
     r"(?:company|organi[sz]ation|business|group|teams|portfolio)|"
     r"\b(?:drive|driving|lead|leading|accelerat\w+|scale|scaling|foster\w*|vorantreiben|treib\w+)\b (?:the )?"
     r"(?:(?:ai|genai|generative ai|ki)[- ]adoption|adoption (?:of|von) (?:generative[nr]? )?(?:ai|genai|ki|llms?))\b|"
     r"\badoption of (?:generative )?ai\b[^.]{0,60}\b(?:across|throughout|within)\b", "AI adoption across the company"),
    (r"\b(?:ai|ki|copilot|genai|llm)[- ]roll-?outs?\b|\broll(?:ing)?[- ]out (?:of )?(?:generative )?(?:ai|ki|copilot|genai|llms?)\b|"
     r"\brollout (?:of|von) (?:\w+ ){0,2}(?:ai|ki|copilot|genai|llm)", "AI rollout"),
    (OUR + r" (?:ki|ai|genai)[- ]transformation\b|\bki[- ]transformation (?:unseres|des) unternehmens\b|"
     r"\btransform\w* (?:our|the) (?:company|organi[sz]ation|business) (?:with|through|using) (?:ai|genai)\b", "AI transformation"),
    (r"\bchatgpt (?:enterprise|team|business|edu)\b", "ChatGPT Enterprise"),
    (r"\b(?:microsoft|ms|m365|microsoft 365|office 365) ?copilot\b|\bcopilot (?:for|für) (?:microsoft|m365|office)\b|\bcopilot studio\b",
     "Microsoft Copilot"),
    (r"\bazure openai\b", "Azure OpenAI"),
    (OUR + r" (?:ki|ai|genai)[- ](?:strategie|strategy|roadmap|initiativen|initiatives|programm?e?|agenda)\b|"
     r"\b(?:ki|ai)[- ]strategie (?:des|unseres) (?:unternehmens|konzerns)\b", "an internal AI strategy"),
    (r"\b(?:intern\w*|internal)[- ](?:ki|ai|genai|llm)[- ]?(?:tools?|lösungen|anwendungen|assistenten|assistants?|plattform|"
     r"platform|initiativen|initiatives|use[- ]cases|chatbots?|hub|agenten|agents)\b", "internal AI tools"),
    (r"\b" + AIX + r"\b[^.]{0,80}\b(?:across|throughout) (?:the |our |all )?(?:company|organi[sz]ation|business|group|" + STAFF + r")\b|"
     r"\b(?:unternehmensweit\w*|konzernweit\w*|company-wide|organi[sz]ation-wide|group-wide)\b[^.]{0,60}\b" + AI + r"\b|"
     r"\b" + AI + r"\b[^.]{0,60}\b(?:unternehmensweit\w*|konzernweit\w*|company-wide|organi[sz]ation-wide|group-wide)\b|"
     r"\b(?:für|for) (?:unsere|our|alle|all) " + STAFF + r"\b[^.]{0,60}\b" + AI + r"\b|"
     r"\b" + AIX + r"\b[^.]{0,60}\b(?:für|for) (?:unsere|our|alle|all) " + STAFF + r"\b|"
     r"\b(?:ki|ai|genai)[- ]use[- ]cases?\b[^.]{0,80}\b(?:in|mit|with|across) (?:den |unseren |our |the )?" + STAFF + r"\b|"
     r"\b(?:integrat\w+|embed\w*|einbinden|integrieren|einsetzen|verankern)\b[^.]{0,40}\b" + AI + r"\b[^.]{0,40}\b" + OUR +
     r" (?:prozesse|processes|workflows|abläufe|operations|arbeitsweise|organisation|organization)\b|"
     r"\b" + AI + r"\b[^.]{0,40}\b(?:in|into) " + OUR + r" (?:prozesse|processes|workflows|abläufe|operations|organisation|organization)\b",
     "AI for the whole company"),
    (r"\b(?:ki|ai)[- ](?:enablement|befähigung)\b|\bai champions?\b|\bki[- ](?:champions?|botschafter\w*|multiplikator\w*)\b|"
     r"\b(?:ki|ai)[- ]kompetenz\w* (?:der |unserer |in der )?(?:mitarbeitenden|mitarbeiter|belegschaft|organisation)\b|"
     r"\bai literacy\b|\bki[- ]schulung\w*\b|\bai training (?:for|of) (?:employees|staff|teams|colleagues)\b",
     "AI enablement / training for staff"),
    (r"\b(?:ki|ai)[- ]governance\b", "AI governance"),
]
ROLLOUT_TERMS = [(re.compile(p, re.I), label) for p, label in ROLLOUT_TERMS]

# Roles that talk about AI on behalf of customers. A rollout phrase in their
# post describes the customer, not the company, so it does not count.
CLIENT_FACING = re.compile(r"\b(sales|account executive|account manager|business development|vertrieb\w*|"
                           r"consultant|berater\w*|beratung|presales|pre-sales|solution\w*|forward deployed|"
                           r"customer success|implementation|deployment|trainer|dozent\w*|coach)\b", re.I)

AI_WORD = re.compile(r"\b(ki|ai|künstliche\w* intelligenz|artificial intelligence|genai|llms?|chatgpt|copilot|"
                     r"machine learning|generative\w*)\b", re.I)
GDPR = re.compile(r"\b(dsgvo|gdpr|datenschutz\w*|data protection|data privacy|eu ai act|ai act|ki-verordnung|"
                  r"eu-ki-verordnung)\b", re.I)
# A GDPR mention only counts near an AI word, so a privacy notice at the bottom
# of a post that also mentions AI somewhere does not count.
GDPR_NEAR = 250

SIZE_TEXT = re.compile(
    r"\b(konzern\w*|mittelstand\w*|mittelständisch\w*|marktführer\w*|market leader|weltmarktführer|"
    r"familienunternehmen|börsennotiert\w*|dax|mdax|sdax|listed company|standorten|locations in|"
    r"offices in|niederlassungen|tochtergesellschaft\w*|subsidiar\w*|enterprise-wide)\b|"
    r"\b(\d{1,3}[.,]?\d{3}|\d{3,})\+?\s*(mitarbeitende\w*|mitarbeiter\w*|beschäftigte\w*|employees|"
    r"colleagues|kolleg\w+|people|menschen)\b", re.I)


# ---------------------------------------------------------------- exclusions

# Langdock, its competitors and big AI vendors. Keys as key_of() makes them.
EXCLUDE = {
    "langdock", "openai", "microsoft", "microsoftdeutschland", "glean", "anthropic", "google", "alphabet",
    "alephalpha", "deepl", "deeplse", "mistral", "mistralai", "cohere", "nvidia", "amazon", "aws",
    "amazonwebservices", "meta", "ibm", "salesforce", "servicenow", "sap", "neuland", "neulandai",
    "workist", "celonis", "jetbrains", "datadog", "intercom", "cresta", "parloa", "helsing",
    "blackforestlabs", "n8n", "n8nio", "langfuse", "perplexity", "writer", "moveworks", "dust",
    "stackit", "ionos", "telekom", "tsystems", "ki", "jobgether", "testerwork", "welo", "weloglobal",
    "rwstrainai", "tsmg", "appen", "telusinternational", "toptal", "databricks", "snowflake", "nebius",
    "palantir", "uipath", "hugging face", "huggingface", "scaleai", "clickhouse", "elastic", "mongodb",
    # Big IT consultancies and system integrators. They sell AI projects.
    "accenture", "capgemini", "capgeminiinvent", "deloitte", "pwc", "kpmg", "ey", "ernstyoung", "mckinsey",
    "bcg", "bostonconsulting", "bain", "adesso", "msg", "msgsystems", "cgi", "soprasteria", "computacenter",
    "bechtle", "cancom", "allgeier", "materna", "nttdata", "atos", "infosys", "tcs", "wipro", "cognizant",
    "bridgingit", "communardo", "cbscorporatebusinesssolutions", "cbs", "valantic", "gft", "itelligence",
    "nagarro", "exxeta", "mhp", "umlaut", "sycor", "all-for-one", "allforone", "inneosolutions", "inneo",
}

# Company names that say "we are an AI company".
VENDOR_NAME = re.compile(r"(\.ai\b|\bai\b|\bki\b|\w+ai$|\bmachine learning\b|\bintelligence\b|"
                         r"\bgpt\b|\bllm\b|\bbuildai\b|\bmoinai\b|\bdeepmind\b)", re.I)
CONSULTANCY_NAME = re.compile(r"\b(consulting|consultants?|unternehmensberatung|beratungs\w*|advisory|reply|"
                              r"systemhaus|agentur|agency)\b", re.I)
# How an AI vendor describes itself. Only plain self-descriptions count. "Our AI
# platform" is left alone on purpose: at a retailer or an insurer that is the
# internal platform they are building, which is exactly the signal we want.
VENDOR_TEXT = re.compile(
    r"\b(ai|ki)[- ](startup|start-up|scale-?up|company|firma|native|first company|lab|labs)\b|"
    r"\b(we|wir) (are|sind) (an? |ein\w* )?(\w+ ){0,3}(ai|ki)[- ]?(startup|start-up|scale-?up|company|unternehmen|plattform|platform|anbieter|vendor|lab)\b|"
    r"\b(we|wir) (build|develop|entwickeln|bauen|are building)\s+(\w+ ){0,4}(ai|ki|llm|genai|agent\w*)[- ]?"
    r"(products?|platform|plattform|agents?|lösung\w*|solutions?|systems?|software|assistants?|models?|produkte?)\b|"
    r"\b(ai|ki|genai|llm)[- ](powered|native|driven|based|basiert\w*|gestützte?[nr]?)\s+(\w+ ){0,2}"
    r"(platform|plattform|software|saas|product|produkt|solution|lösung|assistant|assistent|startup)\b|"
    r"\b(leading|führende\w*) (\w+ ){0,3}(ai|ki|genai|llm) (platform|plattform|company|anbieter|provider|vendor)\b|"
    r"\b(enterprise|industrial|conversational|voice|legal|health|medical)[- ](ai|ki)[- ]?(platform|plattform|company|startup|provider|management)\b|"
    r"\b(ai|ki)[- ](platform|plattform) (for|für)\b|\bfoundation models?\b|\bvc-backed ai\b|\bworld'?s leading ai\b|"
    r"\bai health[- ]?tech\b|\bhealthcare ai\b",
    re.I)
# Staffing, recruiting and job-ad agencies. Their posts are for someone else.
AGENCY = re.compile(
    r"\b(personalvermittlung|personaldienstleist\w*|personalberatung|arbeitnehmerüberlassung|zeitarbeit|"
    r"headhunt\w*|executive search|recruiting agency|recruitment agency|staffing|direktvermittlung|"
    r"im auftrag (unseres|eines) (kunden|mandanten)|für unseren (kunden|mandanten),? (ein|eine|einen|der|die|das)\b|"
    r"on behalf of (our|a) client|our client,? (is|a|an)\b|unser (kunde|mandant),? (ist|ein)\b|für einen unserer kunden)\b", re.I)
# "Wir arbeiten nicht mit Personaldienstleistern" is common in German posts.
NEGATION = re.compile(r"\b(kein\w*|nicht|ohne|no|not|without|bitte keine)\b", re.I)
AGENCY_NAME = re.compile(r"\b(recruitment|recruiting (gmbh|ag|ug|ltd)|staffing|personalvermittlung|"
                         r"personaldienst\w*|personalberatung|personalservice|headhunt\w*|zeitarbeit|jobgether|"
                         r"talents? ?(connect|partners?|solutions)|hr-consulting|executive search)\b", re.I)
# Consultancies and IT service firms that sell AI projects to clients. They are
# partners, not buyers.
AI_CONSULTANCY = re.compile(
    r"\b(wir sind|we are|als) (ein\w* |an? )?(\w+ ){0,3}(beratungs\w*|unternehmensberatung|consultancy|consulting (firm|company)|"
    r"systemhaus|it-dienstleister|it-beratung|digitalagentur|digital agency|agentur|beratungshaus)\b|"
    r"\b(unterstützen|begleiten|beraten|helfen) (wir )?(unsere[nr]?|unseren) (kunden|mandanten)\b.{0,120}\b(ki|ai|künstliche\w* intelligenz|genai|copilot)\b|"
    r"\b(we help|helping|we support|supporting) (our )?(clients|customers)\b.{0,120}\b(ai|genai|copilot)\b|"
    r"\b(ki|ai|genai|copilot)\b.{0,120}\b(für|bei) (unsere[nr]?|unseren) (kunden|mandanten)\b|"
    r"\b(ai|genai|copilot)\b.{0,120}\bfor (our )?(clients|customers)\b|"
    r"\b(ai|ki|genai|llm|copilot)\b.{0,100}\b(kundenprojekt\w*|client projects?|customer projects?)\b|"
    r"\b(kundenprojekt\w*|client projects?|customer projects?)\b.{0,100}\b(ai|ki|genai|llm|copilot)\b",
    re.I)


AGENCY_NOTICE = re.compile(r"\b(hinweis (für|an)|gebeten|bitten|absehen|unaufgefordert\w*|keine|nicht|"
                           r"do not accept|unsolicited|not accept)\b", re.I)
INHOUSE = re.compile(r"\b(inhouse[- ]consulting|in-house consulting|internal clients|interne[nr]? kunden|"
                     r"internal customers|interne[nr]? beratung)\b", re.I)


def agency_match(text):
    for m in AGENCY.finditer(text):
        if NEGATION.search(text[max(0, m.start() - 60): m.start()]):
            continue
        if AGENCY_NOTICE.search(text[max(0, m.start() - 40): m.end() + 140]):
            continue
        return m
    return None


def exclusion_reason(name, jobs):
    """Return (reason, matched text) when a company is left out, else None."""
    k = key_of(name)
    if k in EXCLUDE or any(k.startswith(x) for x in ("langdock", "openai", "anthropic", "alephalpha", "deepl", "glean")):
        return "Langdock, a competitor, big tech or a big IT consultancy", name
    if VENDOR_NAME.search(name):
        return "name says AI company", name
    head = " ".join(j["title"] + " " + j["text"][:1500] for j in jobs[:5])
    m = VENDOR_TEXT.search(head)
    if m:
        return "describes itself as an AI vendor", m.group(0)
    if AGENCY_NAME.search(name):
        return "staffing or recruiting agency", name
    allt = " ".join(j["text"] for j in jobs)
    m = agency_match(allt)
    if m:
        return "staffing or recruiting agency", m.group(0)
    if CONSULTANCY_NAME.search(name):
        return "sells AI or IT consulting", name
    # Only the AI posts are checked here. A retailer's logistics post that says
    # "unsere Kunden" says nothing about who the AI work is for.
    # An in-house consulting team whose "clients" are other departments is a
    # buyer, so those posts are skipped.
    ai_text = " ".join(j["text"] for j in jobs if (TITLE_AI.search(j["title"]) or AI_WORD.search(j["text"][:4000]))
                       and not INHOUSE.search(j["title"] + " " + j["text"]))
    m = AI_CONSULTANCY.search(ai_text)
    if m:
        return "sells AI or IT consulting", m.group(0)
    return None


# ---------------------------------------------------------------- scoring

class Company:
    def __init__(self, name):
        self.name = name
        self.signals = {}      # signal -> (evidence text, url)
        self.extra = []
        self.locations = []
        self.website = ""

    def add(self, signal, text, url):
        if signal not in self.signals:
            self.signals[signal] = (text, url)
        elif url and url not in self.extra and url != self.signals[signal][1] and len(self.extra) < 4:
            self.extra.append(url)

    @property
    def score(self):
        return sum(POINTS[s] for s in self.signals)


def snippet(text, m, width=70):
    a, b = max(0, m.start() - width), min(len(text), m.end() + width)
    s = re.sub(r"[#*_\\]+|&#\d+;", " ", text[a:b])      # BA posts carry markdown
    s = re.sub(r"\s+", " ", s).strip()
    return ("..." if a else "") + s + ("..." if b < len(text) else "")


def owner_hit(title, text):
    if not TITLE_AI.search(title) and not DIGITAL_TRANSFORMATION.search(title):
        return False
    if BUILDER_TITLE.search(title) or JUNIOR_TITLE.search(title):
        return False
    # A product owner or product manager for AI usually builds an AI feature for
    # customers. It only counts when the post is about internal use.
    if PRODUCT_TITLE.search(title) or DATA_TITLE.search(title):
        return bool(rollout_hits(title, text)[0])
    if OWNER_TITLE.search(title):
        return True
    # "Digital Transformation Manager" counts when the post is about AI.
    if DIGITAL_TRANSFORMATION.search(title) and len(AI_WORD.findall(text)) >= 3:
        return True
    return False


def rollout_hits(title, text):
    """Labels of rollout phrases in one post, plus the first match for evidence."""
    labels, first = [], None
    if CLIENT_FACING.search(title):
        return labels, first
    for rx, label in ROLLOUT_TERMS:
        m = rx.search(text)
        if m:
            labels.append(label)
            first = first or (m, text)
    # A student or intern role with an owner-style AI title ("Working Student AI
    # Enablement") is a rollout signal, not an owner.
    if JUNIOR_TITLE.search(title) and OWNER_TITLE.search(title) and TITLE_AI.search(title) \
            and not BUILDER_TITLE.search(title):
        labels.append("a student role in AI enablement")
        first = first or (TITLE_AI.search(title), title)
    return labels, first


def gdpr_hit(text):
    for m in GDPR.finditer(text):
        window = text[max(0, m.start() - GDPR_NEAR): m.end() + GDPR_NEAR]
        if AI_WORD.search(window):
            return m
    return None


def size_hint(jobs):
    """Heuristic only: 3+ open roles on the board, or the text says Konzern,
    Mittelstand, a head count of 100+, or several locations."""
    if len(jobs) >= 3:
        return f"{len(jobs)} open roles on the board"
    for j in jobs:
        m = SIZE_TEXT.search(j["text"])
        if m:
            return f'post says "{m.group(0)}"'
    return None


def score_company(name, jobs):
    c = Company(name)
    c.locations = list(dict.fromkeys(j["location"] for j in jobs if j["location"]))[:3]
    c.sources = sorted({j["source"] for j in jobs})
    owner = [j for j in jobs if owner_hit(j["title"], j["text"])]
    if owner:
        j = owner[0]
        c.add("ai_owner", f'hiring "{j["title"]}"', j["url"])
        for j2 in owner[1:]:
            c.add("ai_owner", "", j2["url"])
    best = None
    for j in jobs:
        labels, first = rollout_hits(j["title"], j["text"])
        if labels and (best is None or len(labels) > len(best[1])):
            best = (j, labels, first)
    if best:
        j, labels, (m, src) = best
        c.add("rollout", f'"{j["title"]}" mentions {", ".join(dict.fromkeys(labels))}', j["url"])
        c.rollout_quote = snippet(src, m)
    # GDPR and size only add to a company that already has an AI signal.
    if not c.signals:
        return c
    for j in jobs:
        m = gdpr_hit(j["text"])
        if m:
            c.add("gdpr_ai", f'"{j["title"]}" mentions {m.group(0)} next to AI', j["url"])
            break
    hint = size_hint(jobs)
    if hint:
        c.add("size", f"looks mid-size or large ({hint}, heuristic)", jobs[0]["url"])
    return c


# ---------------------------------------------------------------- fetch

def fetch_arbeitnow(pages, cache=None):
    jobs = {}
    for page in range(1, pages + 1):
        data = None
        fn = os.path.join(cache, f"arbeitnow-{page}.json") if cache else None
        if fn and os.path.exists(fn):
            data = json.load(open(fn, encoding="utf-8"))
            note("arbeitnow", True, "read from cache")
        else:
            data, err = get_json(API.format(page))
            if data is None:
                note("arbeitnow", False, f"page {page}: {err}")
                time.sleep(6)
                continue
            note("arbeitnow", True)
            if fn:
                os.makedirs(cache, exist_ok=True)
                json.dump(data, open(fn, "w", encoding="utf-8"))
            time.sleep(1.5)
        rows = data.get("data", [])
        if not rows:
            break
        for j in rows:
            jobs[j.get("slug") or j.get("url")] = j
    return list(jobs.values())


# The Bundesagentur für Arbeit job search (Germany only). It is a free public
# API. The X-API-Key below is the public client id the BA publishes for everyone
# (see https://jobsuche.api.bund.dev), not a secret.
BA_SEARCH = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v6/jobs?"
BA_DETAIL = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobdetails/"
BA_PUBLIC = "https://www.arbeitsagentur.de/jobsuche/jobdetail/"
BA_HEADERS = {"X-API-Key": "jobboerse-jobsuche"}
# Searches for people who will own or run an AI rollout. zeitarbeit=false and
# pav=false already drop temp agencies and private recruiters on the BA side.
BA_QUERIES = [
    "KI-Manager", "KI Manager", "AI Manager", "Head of AI", "Leiter KI", "Leitung KI", "Leiter Künstliche Intelligenz",
    "KI-Beauftragter", "KI-Koordinator", "KI-Referent", "Referent KI", "KI-Transformation", "AI Transformation",
    "AI Enablement", "KI Enablement", "AI Adoption", "KI-Einführung", "AI Lead", "KI Lead", "AI Champion",
    "KI-Strategie", "AI Strategy Manager", "AI Governance", "KI Governance", "Generative AI Manager",
    "Microsoft Copilot", "Copilot Einführung", "ChatGPT", "Digital Workplace KI", "Digitalisierung KI Manager",
    "Innovationsmanager KI", "Prozessautomatisierung KI", "AI Product Owner", "Product Owner KI",
]


def ba_get(url, cache, name):
    fn = os.path.join(cache, name) if cache else None
    if fn and os.path.exists(fn):
        return json.load(open(fn, encoding="utf-8")), None
    data, err = get_json(url, BA_HEADERS)
    if data is not None and fn:
        os.makedirs(cache, exist_ok=True)
        json.dump(data, open(fn, "w", encoding="utf-8"))
    return data, err


def fetch_ba(per_query, max_details, days, cache=None):
    import base64, urllib.parse
    found = {}
    for q in BA_QUERIES:
        params = {"was": q, "size": per_query, "page": 1, "angebotsart": 1, "zeitarbeit": "false",
                  "pav": "false", "veroeffentlichtseit": days}
        name = "ba-q-" + re.sub(r"[^a-z0-9]+", "-", q.lower()) + f"-{per_query}-{days}.json"
        data, err = ba_get(BA_SEARCH + urllib.parse.urlencode(params), cache, name)
        if data is None:
            note("bundesagentur", False, f"search {q}: {err}")
            continue
        note("bundesagentur", True)
        for s in data.get("ergebnisliste") or []:
            ref = s.get("referenznummer") or s.get("refnr")
            title = s.get("stellenangebotsTitel") or s.get("titel") or ""
            # Only fetch details for titles that are about AI at all.
            if ref and ref not in found and (TITLE_AI.search(title) or re.search(r"copilot|chatgpt|openai", title, re.I)):
                found[ref] = s
        if not cache or not os.path.exists(os.path.join(cache, name)):
            time.sleep(0.4)
    jobs = []
    for i, (ref, s) in enumerate(found.items()):
        if i >= max_details:
            note("bundesagentur", True, f"stopped at {max_details} job details")
            break
        b64 = base64.b64encode(ref.encode()).decode()
        d, err = ba_get(BA_DETAIL + b64, cache, f"ba-d-{ref}.json")
        if d is None:
            note("bundesagentur", False, f"detail: {err}")
            d = {}
        locs = s.get("stellenlokationen") or d.get("stellenlokationen") or []
        a = (locs[0].get("adresse") if locs else None) or s.get("arbeitsort") or {}
        loc = ", ".join(x for x in (a.get("ort"), a.get("land")) if x)
        jobs.append({"company": s.get("firma") or s.get("arbeitgeber") or d.get("firma") or "",
                     "title": s.get("stellenangebotsTitel") or s.get("titel") or "",
                     "text": plain(d.get("stellenangebotsBeschreibung") or ""),
                     "url": BA_PUBLIC + ref, "location": loc or "Deutschland", "source": "bundesagentur"})
        if not cache or not os.path.exists(os.path.join(cache, f"ba-d-{ref}.json")):
            time.sleep(0.3)
    note("bundesagentur", True, f"{len(found)} AI job titles found, {len(jobs)} read")
    return jobs


def merge_groups(per_company, names):
    """Fold "SIGNAL IDUNA Krankenversicherung" into "SIGNAL IDUNA" and "Dirk
    Rossmann GmbH" into "ROSSMANN": one name's words are the start or the end of
    the other's. The shorter name wins."""
    toks = {k: tokens(names[k]) for k in per_company}
    roots = []
    for k in sorted(per_company, key=lambda k: (len(toks[k]), len(k))):
        t = toks[k]
        home = None
        for r in roots:
            rt = toks[r]
            if not rt or len(rt) >= len(t):
                continue
            if t[:len(rt)] == rt or (t[-len(rt):] == rt and len("".join(rt)) >= 5):
                home = r
                break
        if home:
            seen_urls = {j["url"] for j in per_company[home]}
            per_company[home] += [j for j in per_company.pop(k) if j["url"] not in seen_urls]
        else:
            roots.append(k)
    return per_company


def run(pages, cache=None, ba=True, ba_per_query=50, ba_max=400, ba_days=30):
    per_company = defaultdict(list)
    names = {}
    raw = fetch_arbeitnow(pages, cache) if pages else []
    dach = 0
    for j in raw:
        title = (j.get("title") or "").strip()
        name = clean_company(j.get("company_name"), title)
        if not name:
            continue
        text = plain(j.get("description"))
        loc = (j.get("location") or "").strip()
        if not is_dach(loc, f"{title} {text}"):
            continue
        dach += 1
        k = key_of(name)
        names.setdefault(k, name)
        per_company[k].append({"title": title, "text": text, "url": j.get("url", ""), "location": loc,
                               "source": "arbeitnow"})
    if pages:
        note("arbeitnow", True, f"{len(raw)} jobs, {dach} in DACH, {len(per_company)} companies")
    if ba:
        for j in fetch_ba(ba_per_query, ba_max, ba_days, cache):
            name = clean_company(j.pop("company"), j["title"])
            if not name:
                continue
            k = key_of(name)
            names.setdefault(k, name)
            if not any(x["url"] == j["url"] for x in per_company[k]):
                per_company[k].append(j)
    per_company = merge_groups(per_company, names)

    companies, excluded = [], defaultdict(list)
    for k, jobs in per_company.items():
        c = score_company(names[k], jobs)
        if not c.signals:
            continue
        why = exclusion_reason(names[k], jobs)
        if why:
            excluded[why[0]].append(f'{names[k]} ("{why[1][:50]}")')
            continue
        companies.append(c)
    return companies, excluded


# ---------------------------------------------------------------- output

def load_seen():
    if not os.path.exists(SEEN):
        return set()
    return {l.strip() for l in open(SEEN, encoding="utf-8") if l.strip()}


def save_seen(seen):
    os.makedirs(os.path.dirname(SEEN), exist_ok=True)
    with open(SEEN, "w", encoding="utf-8") as f:
        f.write("\n".join(sorted(seen)) + "\n")


FIELDS = ["found", "company", "score", "signals", "why", "evidence_url", "more_evidence",
          "website", "location", "sources", "quote"]


def to_row(c, today):
    top = next(s for s in ORDER if s in c.signals)
    why = " | ".join(f"+{POINTS[s]} {c.signals[s][0]}" for s in ORDER if s in c.signals)
    more = [c.signals[s][1] for s in ORDER if s in c.signals and s != top and c.signals[s][1]]
    more = [u for u in dict.fromkeys(more + c.extra) if u != c.signals[top][1]]
    return {
        "found": today, "company": c.name, "score": c.score,
        "signals": ";".join(s for s in ORDER if s in c.signals),
        "why": why, "evidence_url": c.signals[top][1],
        "more_evidence": " ".join(more)[:1500],
        "website": c.website, "location": "; ".join(c.locations), "sources": ";".join(c.sources),
        "quote": getattr(c, "rollout_quote", "")[:300],
    }


def write_md(path, rows, args, skipped_seen, skipped_low, excluded):
    day = rows[0]["found"] if rows else date.today().isoformat()
    lines = [f"# AI rollout signals, {day}", ""]
    lines.append(f"{len(rows)} companies in DACH scored {args.min_score} or more. "
                 f"{skipped_seen} skipped as already reported, {skipped_low} below the cutoff, "
                 f"{sum(len(v) for v in excluded.values())} left out by the exclusion rules.")
    lines += ["", "## Sources", "", "| Source | OK calls | Failed calls | Notes |", "|---|---|---|---|"]
    for s, v in sorted(STATUS.items()):
        lines.append(f"| {s} | {v['ok']} | {v['fail']} | {'; '.join(v['notes']) or '-'} |")
    lines += ["", "## Points", "", "| Signal | Points |", "|---|---|"]
    lines += [f"| {s} | +{POINTS[s]} |" for s in ORDER]
    lines += ["", "## Left out", "", "| Reason | Companies |", "|---|---|"]
    for why, names in sorted(excluded.items()):
        lines.append(f"| {why} | {len(names)} |")
    lines += ["", "## Top companies", "", "| # | Company | Score | Why | Evidence |", "|---|---|---|---|---|"]
    for i, r in enumerate(rows[:30], 1):
        lines.append(f"| {i} | {r['company']} | {r['score']} | {r['why'].replace('|', '/')} | {r['evidence_url']} |")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pages", type=int, default=15, help="Arbeitnow pages to read (about 100 jobs each)")
    ap.add_argument("--no-ba", action="store_true", help="skip the Bundesagentur für Arbeit search")
    ap.add_argument("--ba-per-query", type=int, default=50, help="BA results to read per search")
    ap.add_argument("--ba-max", type=int, default=400, help="most BA job details to fetch")
    ap.add_argument("--ba-days", type=int, default=30, help="only BA posts published in the last N days")
    ap.add_argument("--min-score", type=int, default=30)
    ap.add_argument("--out", default=None)
    ap.add_argument("--cache", default=None, help="folder to keep raw API pages in")
    ap.add_argument("--no-dedupe", action="store_true", help="ignore memory, report everything")
    ap.add_argument("--show-excluded", action="store_true", help="print the companies the rules left out")
    args = ap.parse_args()

    today = date.today().isoformat()
    print("reading job posts (Arbeitnow" + ("" if args.no_ba else ", Bundesagentur für Arbeit") + ") ...", file=sys.stderr)
    companies, excluded = run(args.pages, args.cache, not args.no_ba, args.ba_per_query, args.ba_max, args.ba_days)

    seen = set() if args.no_dedupe else load_seen()
    rows, skipped_seen, skipped_low = [], 0, 0
    for c in companies:
        if c.score < args.min_score:
            skipped_low += 1
            continue
        if key_of(c.name) in seen:
            skipped_seen += 1
            continue
        rows.append(to_row(c, today))
    rows.sort(key=lambda r: (-r["score"], r["company"].lower()))

    out = args.out or os.path.join(HERE, "output", f"signals-{today}.csv")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    if not rows and os.path.exists(out) and sum(1 for _ in open(out, encoding="utf-8")) > 1:
        print("nothing net-new, keeping the existing file:", out)
        return
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    md = os.path.splitext(out)[0] + ".md"
    write_md(md, rows, args, skipped_seen, skipped_low, excluded)

    if not args.no_dedupe:
        save_seen(seen | {key_of(r["company"]) for r in rows})

    for s, v in sorted(STATUS.items()):
        print(f"{s:10}: ok {v['ok']}, failed {v['fail']}  {'; '.join(v['notes'])}")
    print(f"companies : {len(rows)} new, {skipped_seen} already seen, {skipped_low} below {args.min_score}")
    for why, names in sorted(excluded.items()):
        print(f"left out  : {len(names):3}  {why}" + (f": {', '.join(sorted(names))}" if args.show_excluded else ""))
    print(f"written   : {out}\n            {md}")
    for r in rows[:20]:
        print(f"  {r['score']:>3}  {r['company']}  {r['evidence_url']}")


if __name__ == "__main__":
    main()
