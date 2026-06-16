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

### 4. Schedule it (runs automatically)
```powershell
.\register_task.ps1
```
This registers **three** Windows tasks so the brief reaches your phone at **10:35 PM** every day:

| Task | Time | Wakes PC? | What it does |
|---|---|---|---|
| `SupremeCourtBrief-Prepare-2PM` | 2:00 PM | No (only if PC already on) | Gather + build the brief (no send) |
| `SupremeCourtBrief-Prepare-Late` | 10:30 PM | Yes | Build the brief if 2 PM was missed (no send) |
| `SupremeCourtBrief-Send` | 10:35 PM | Yes | Email the brief (the only send) |

Behaviour:
- **PC on at 2 PM** → brief is built then; at 10:35 PM it's sent.
- **PC off/asleep at 2 PM** → the PC wakes at 10:30 PM, builds the brief, and sends at 10:35 PM.
- **PC fully shut down** → Windows runs the missed tasks as soon as you turn it on; Send prepares first if needed, then sends.

> Waking from sleep needs the PC asleep, not fully shut down. The tool is cloud-portable if you later move it to an always-on server.

**After sending (power management):** the 10:35 PM Send step retries the email send up to **3 times** (`SEND_MAX_ATTEMPTS`), then — if the tool had to wake the PC — **puts the PC back to sleep**. It only sleeps when you've been idle for at least `SLEEP_MIN_IDLE_SECONDS` (default 5 min), so it will never sleep the machine while you're actively using it (e.g. if you powered it on yourself late at night). Set `SLEEP_AFTER_SEND = False` in `config.py` to disable auto-sleep. (Depending on your Windows power settings the machine may hibernate rather than sleep; daily wake-to-run still works from either.)

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
| `main.py` | Orchestration, once-per-day guard, catch-up, logging |
| `register_task.ps1` | Windows Task Scheduler registration |
| `email_setup.py` | One-time helper to test email delivery |

## Cost
SCI judgments are text PDFs, so no expensive OCR. Each run uses Claude Haiku for one CAPTCHA read + one headnote per judgment — typically a few rupees to ~₹60 on a heavy day.

## Logs & state
- `logs\run_YYYYMM.log` — what happened each run.
- `state.json` — once-per-day guard and which dates were already delivered.
