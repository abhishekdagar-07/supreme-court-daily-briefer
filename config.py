"""Central configuration for the Supreme Court Daily Judgment Briefer.

All secrets come from the .env file (never committed). Everything else is a
plain constant you can tweak here.
"""
import os
import pathlib
import datetime
from dotenv import load_dotenv

# Load .env that sits next to this file
BASE_DIR = pathlib.Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# ── Secrets (from .env) ────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()

# Email delivery (Gmail SMTP with an app password)
EMAIL_ADDRESS = os.environ.get("EMAIL_ADDRESS", "").strip()        # the sending Gmail account
EMAIL_APP_PASSWORD = os.environ.get("EMAIL_APP_PASSWORD", "").strip()  # 16-char Google app password
EMAIL_TO = os.environ.get("EMAIL_TO", "").strip() or EMAIL_ADDRESS    # recipient (defaults to sender)
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com").strip()
SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))

# ── Models ─────────────────────────────────────────────────────────────────────
# Haiku for both captcha-reading and headnote generation (cheap, fast).
CAPTCHA_MODEL = "claude-haiku-4-5-20251001"
BRIEF_MODEL = "claude-haiku-4-5-20251001"

# ── Supreme Court endpoints ────────────────────────────────────────────────────
SCI_PAGE = "https://www.sci.gov.in/judgements-judgement-date/"
SCI_AJAX = "https://www.sci.gov.in/wp-admin/admin-ajax.php"
SCI_CAPTCHA_IMG = "https://www.sci.gov.in/?_siwp_captcha&id={scid}"
SEARCH_ACTION = "get_judgements_judgement_date"

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# ── Behaviour ──────────────────────────────────────────────────────────────────
MAX_CAPTCHA_RETRIES = 8       # captcha read attempts before giving up a run
MAX_PDF_PAGES = 60           # cap pages sent to the model per judgment
LOOKBACK_DAYS = 7            # how far back to hunt for the latest day with judgments
REQUEST_TIMEOUT = 60
DOWNLOAD_TIMEOUT = 120
POLITE_DELAY = 0.5           # seconds between PDF downloads

# Email send retries (the 10:35 PM send step)
SEND_MAX_ATTEMPTS = 3        # try sending the brief this many times before giving up
SEND_RETRY_DELAY = 20        # seconds between send attempts

# Power management — after the 10:35 PM send, sleep the PC if the tool woke it.
SLEEP_AFTER_SEND = True       # set False to never auto-sleep
SLEEP_MIN_IDLE_SECONDS = 300  # only sleep if no user input for this long (i.e. PC was woken / you're away)

# ── Output location (on the Desktop) ───────────────────────────────────────────
# One main folder -> month subfolders -> date subfolders. Each date folder holds
# that day's judgment PDFs (named "Petitioner vs Respondent.pdf") plus the brief.
MAIN_FOLDER_NAME = "Supreme Court Judgments"


def _desktop_dir() -> pathlib.Path:
    """Best-effort Desktop path, handling OneDrive-redirected Desktops."""
    home = pathlib.Path.home()
    onedrive = os.environ.get("OneDrive") or os.environ.get("OneDriveConsumer")
    candidates = []
    if onedrive:
        candidates.append(pathlib.Path(onedrive) / "Desktop")
    candidates.append(home / "Desktop")
    for c in candidates:
        if c.exists():
            return c
    return home / "Desktop"


OUTPUT_ROOT = _desktop_dir() / MAIN_FOLDER_NAME

MONTH_NAMES = ["", "January", "February", "March", "April", "May", "June",
               "July", "August", "September", "October", "November", "December"]


def date_folder(d: datetime.date) -> pathlib.Path:
    """Return (and create) the date folder for a given date:
    <Desktop>/<Main>/<YYYY-MM Monthname>/<YYYY-MM-DD>/
    """
    month_dir = OUTPUT_ROOT / f"{d.year}-{d.month:02d} {MONTH_NAMES[d.month]}"
    day_dir = month_dir / d.strftime("%Y-%m-%d")
    day_dir.mkdir(parents=True, exist_ok=True)
    return day_dir


# ── Bookkeeping (kept inside the project, not on the Desktop) ───────────────────
LOG_DIR = BASE_DIR / "logs"
STATE_FILE = BASE_DIR / "state.json"    # once-per-day guard / delivered dates
LOG_DIR.mkdir(exist_ok=True)
