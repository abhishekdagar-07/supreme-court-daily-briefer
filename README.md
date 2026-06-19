# Supreme Court of India — Daily Judgment Briefer

Every day, this tool:

1. **Scrapes** the [Supreme Court judgment-date search](https://www.sci.gov.in/judgements-judgement-date/) for the previous court working day (auto-solving the site's math CAPTCHA with Claude).
2. **Downloads** every judgment PDF into a tidy folder on your Desktop, named by case.
3. **Briefs** each judgment with Claude (Haiku) into a structured law-report **headnote** (issues, facts, holding, ratio, final order).
4. **Builds one combined Word document** for the day (with a Contents page).
5. **Emails it to you** — a readable preview in the body plus the Word file attached. On empty/failed days it still sends a short status email.

## Output layout (on your Desktop)

```
Desktop\Supreme Court Judgments\
    2025-12 December\
        2025-12-10\
            The State Of West Bengal vs Anil Kumar Dey.pdf
            Dr Sohail Malik vs Union Of India.pdf
            ...
            Brief 2025-12-10.docx
```

## Setup

### 1. Install dependencies
```powershell
py -m pip install -r requirements.txt
```

### 2. API key
Put your Anthropic API key in a file named `.env` next to the scripts:
```
ANTHROPIC_API_KEY=sk-ant-...
```
(`.env` is gitignored and never committed.)

### 3. Email (to receive the briefs)
Briefs are emailed (via Gmail) to **adv.abhishekdagar@gmail.com**.
1. The **sending** Gmail account needs **2-Step Verification ON**.
2. Create an **App Password**: https://myaccount.google.com/apppasswords (Google shows a 16-char code).
3. Fill `.env`:
   ```
   EMAIL_ADDRESS=your_sending_account@gmail.com
   EMAIL_APP_PASSWORD=abcdefghijklmnop
   EMAIL_TO=adv.abhishekdagar@gmail.com
   ```
4. Test it: `py email_setup.py` (sends a test email to `EMAIL_TO`).

### 4. Google Drive archive (optional)
Archive each day's PDFs + Word brief to Drive (also syncs to your Desktop if you run Google Drive for Desktop). Files land in `My Drive/Supreme Court Judgments/<month>/<date>/`. Follow the steps in `gdrive_setup.py` to create a Google Cloud OAuth client, then:
```
GOOGLE_CLIENT_ID=...apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=...
GOOGLE_REFRESH_TOKEN=...        # printed by: py gdrive_setup.py
```
Uses the least-privilege `drive.file` scope (only sees files it creates). Skipped automatically if these are blank.

### 5. Run automatically in the cloud (recommended) — GitHub Actions
The scheduled run lives in `.github/workflows/daily-brief.yml`. It runs **daily at 17:05 UTC (10:35 PM IST)** via `python main.py --yesterday`, independent of your PC.
- Add your secrets in the repo: **Settings → Secrets and variables → Actions** — `ANTHROPIC_API_KEY`, `EMAIL_ADDRESS`, `EMAIL_APP_PASSWORD`, `EMAIL_TO`, and (optional) the three `GOOGLE_*` values. (Can be set with `gh secret set`.)
- GitHub cron is best-effort (may run a few minutes late).
- Note: GitHub auto-pauses scheduled workflows after **60 days of no repo activity** — push any commit to resume.

### 6. (Alternative) Run on this PC instead — Windows Task Scheduler
```powershell
.\register_task.ps1
```
Registers three tasks: build at 2 PM, fallback build at 10:30 PM (wakes PC), email at 10:35 PM (wakes PC, retries 3×, then sleeps the PC if you've been idle ≥ `SLEEP_MIN_IDLE_SECONDS`). Only works while the PC is on or asleep (not shut down), and wake-from-sleep depends on your power settings — which is why the cloud option above is more reliable. Disable with `Disable-ScheduledTask`.

## Run it on demand (any time)

**Easiest — double-click:** `Run SC Briefer.bat` (or the **"Run Supreme Court Briefer"** shortcut on your Desktop). It asks for a date — press **Enter** for the latest court day, or type a date like `10-12-2025`.

**From a terminal:**
```powershell
py main.py --latest            # the most recent court day with judgments (on demand)
py main.py --date 10-12-2025   # a specific date (DD-MM-YYYY or YYYY-MM-DD)
py main.py                     # scheduled mode: previous working day (+ catch up missed days)
py main.py --no-send           # save files only, skip email
py main.py --force             # ignore the "already ran today" guard
```

## How it works (files)
| File | Role |
|---|---|
| `config.py` | Paths, models, endpoints, Desktop folder layout |
| `sci_client.py` | CAPTCHA solving, date search, pagination, PDF download |
| `brief.py` | PDF text extraction (+ Vision OCR fallback) and Haiku headnotes |
| `worddoc.py` | Combined Word document builder |
| `email_notify.py` | Email preview + Word attachment delivery |
| `gdrive.py` | Google Drive archive uploader (OAuth, `drive.file`) |
| `main.py` | Orchestration, run modes, logging |
| `.github/workflows/daily-brief.yml` | Cloud daily schedule (GitHub Actions) |
| `register_task.ps1` | Windows Task Scheduler registration (PC alternative) |
| `email_setup.py` / `gdrive_setup.py` | One-time helpers (test email / get Drive token) |

## Cost
SCI judgments are text PDFs, so no expensive OCR. Each run uses Claude Haiku for one CAPTCHA read + one headnote per judgment — typically a few rupees to ~₹60 on a heavy day.

## Logs & state
- `logs\run_YYYYMM.log` — what happened each run.
- `state.json` — once-per-day guard and which dates were already delivered.
