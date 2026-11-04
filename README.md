# Market Research Lead Generation

Finds companies that may need market research / competitor analysis, qualifies and scores them with an LLM on Groq,
verifies every contact field against the source text, removes duplicates, and gives you a Streamlit dashboard,
Excel exports and a daily email summary. **It never sends outreach** - it only drafts messages for your review.

```
Brave Search -> normalise/dedupe -> fetch page (robots.txt respected) -> Groq LLM extracts facts
  -> code verifies + scores 0-100 -> look for published business emails on the company's own site
  -> SQLite -> Excel (new leads + master) -> email summary
```

## Using the app
1. **Find leads** tab: type an **industry / niche** (e.g. `fintech`, `e-commerce fashion`, `HR software`), optional
   **extra keywords**, pick **countries** and the **buying signals** to look for (expansion, product launch, hiring
   strategy/research roles, funding). Your industry drives the search queries *and* the fit score.
2. Press **Find leads**. Results appear as scored cards (green 75+, amber 60+), with verified facts and assumptions
   kept separate in each lead's *Details* panel.
3. **Download Excel** straight from the app after every run: *New leads*, *Master sheet* (all stored + new), and
   *Full analysis* (every page analysed, including why it was rejected).
4. **Lead database** tab: search, filter, and download the filtered view or all saved leads.
5. CLI equivalent: `python run_daily.py --industry fintech --keywords "Series A" --countries CA,GB --signals expansion,funding`

## Rules built in
- Only public pages are fetched; `robots.txt` is honoured; 401/403/CAPTCHA pages are skipped, never bypassed.
- LinkedIn, Crunchbase, ZoomInfo and social sites are never fetched.
- An email, contact name, website or LinkedIn URL is kept **only if it appears verbatim in the fetched text**
  (emails must also be on the company's own domain; free-mail addresses are dropped). Otherwise: `Not found`.
- Inferred websites are labelled "inferred ... please verify". Verified facts and assumptions are stored separately.
- Dry run is the default everywhere. Nothing is stored unless you choose live mode.

## Files
| Path | Purpose |
|---|---|
| `app.py` | Streamlit dashboard (run, leads, drafts, run log) behind a password |
| `run_daily.py` | CLI used by GitHub Actions / cron |
| `leadgen/` | Pipeline modules (search, scrape, qualify, verify, enrich, db, export, report) |
| `mcp_server.py` | Optional: lets Claude Desktop / Claude Code drive the pipeline |
| `.github/workflows/daily.yml` | Daily scheduled run (07:00 Bangladesh time) |
| `tests/` | `pytest` tests (run offline) |

## Keys you need
| Secret | Required | Where |
|---|---|---|
| `GROQ_API_KEY` | yes | console.groq.com/keys |
| `BRAVE_API_KEY` | yes | brave.com/search/api |
| `APP_PASSWORD` | yes (Streamlit) | choose one |
| `SMTP_USER`, `SMTP_PASSWORD` | for email | Gmail address + a Google **App Password** (needs 2-step verification) |
| `NOTIFY_EMAIL`, `SENDER_NAME`, `POSTAL_ADDRESS` | recommended | postal address is required in drafts by CAN-SPAM-style laws |

## Deploy
**1. Create a PRIVATE GitHub repo** and push this folder. This matters: the lead database contains names and
business emails of real people, so do not put it in a public repo.

**2. Streamlit Community Cloud** (share.streamlit.io): New app -> pick the repo -> main file `app.py`.
Advanced settings -> Secrets: paste the contents of `.streamlit/secrets.toml.example` with your real values.
Private repos are supported (you grant Streamlit access to the repo).

**3. Daily run (GitHub Actions).** Streamlit Cloud apps sleep when idle and cannot run on a schedule, so the daily
job runs in GitHub Actions. Repo -> Settings -> Secrets and variables -> Actions -> add the same secrets
(`GROQ_API_KEY`, `BRAVE_API_KEY`, `SMTP_USER`, `SMTP_PASSWORD`, `NOTIFY_EMAIL`, `SENDER_NAME`, `POSTAL_ADDRESS`).
Then Actions -> "Daily lead generation" -> Run workflow (leave "live" unticked for a first dry run).
Scheduled runs are live: they store leads in `data/leads.db` and commit it back, and Streamlit redeploys with the new data.

**Important about storage:** Streamlit Cloud's disk is temporary. Leads stored from the *app's* live mode are lost
when the app restarts. The durable copy is `data/leads.db` committed by the Action. For heavy use, swap SQLite for a
hosted database (Supabase/Postgres) - `leadgen/db.py` is the only file that would change.

## Run locally
```bash
pip install -r requirements.txt
cp .env.example .env            # fill in keys
python run_daily.py             # dry run
python run_daily.py --live      # store leads
streamlit run app.py            # dashboard (set APP_PASSWORD in .env or .streamlit/secrets.toml)
pytest                          # needs: pip install -r requirements-dev.txt
```

## Optional: MCP server
```bash
pip install -r requirements-mcp.txt
```
Claude Desktop `claude_desktop_config.json`:
```json
{ "mcpServers": { "lead-generation": { "command": "python", "args": ["/full/path/to/mcp_server.py"] } } }
```
Tools: `run_discovery`, `list_leads`, `export_master_excel`, `set_outreach_status`.

## Known limits
- The model is `llama-3.3-70b-versatile` by default (set `GROQ_MODEL` to change it). Open models follow strict
  instructions a little less reliably than frontier models, which is why every field is re-verified in code. Groq's free
  tier has per-minute token limits; the code waits and retries on rate-limit (429) responses, so big runs are slower.
- Contact emails are often `Not found`: most companies hide them behind forms. For reliably verified emails use a
  lawful provider (Hunter, Apollo, ...) with your own key - add it in `leadgen/enrich.py`.
- Search results are mostly news articles, so leads skew toward companies that make news (often larger than SMEs).
  Tune the queries in `leadgen/search.py`.
- Before contacting anyone check the rules that apply to them (CAN-SPAM, CASL in Canada, UK PECR/GDPR, Australian Spam Act).
