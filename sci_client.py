"""Talks to the Supreme Court of India judgment-date search.

Handles the SIWP math-CAPTCHA (read by Claude, computed in Python), runs the
date search, parses the results table, walks pagination, and downloads PDFs.
"""
import re
import time
import base64
import datetime
import logging

import requests
import urllib3
from bs4 import BeautifulSoup
import anthropic

import config

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
log = logging.getLogger("sci")

_client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)


# ── session ────────────────────────────────────────────────────────────────────

def make_session() -> requests.Session:
    s = requests.Session()
    s.verify = False
    s.headers.update({
        "User-Agent": config.USER_AGENT,
        "Referer": config.SCI_PAGE,
        "X-Requested-With": "XMLHttpRequest",
        "Accept-Language": "en-US,en;q=0.9",
    })
    return s


# ── captcha ────────────────────────────────────────────────────────────────────

def _read_captcha_expression(img_bytes: bytes, media: str) -> str:
    msg = _client.messages.create(
        model=config.CAPTCHA_MODEL, max_tokens=30,
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": media,
                                         "data": base64.standard_b64encode(img_bytes).decode()}},
            {"type": "text", "text": "This CAPTCHA shows a simple arithmetic expression "
                                     "(two numbers with + - or x). Output ONLY the expression "
                                     "as digits and the operator, e.g. '10-3'. No spaces, no answer, no words."}]}])
    return msg.content[0].text.strip().replace(" ", "")


def _solve_captcha(session: requests.Session, scid: str) -> str | None:
    """Fetch the captcha image, read the expression, return the computed answer."""
    ir = session.get(config.SCI_CAPTCHA_IMG.format(scid=scid), timeout=config.REQUEST_TIMEOUT)
    media = ir.headers.get("Content-Type", "image/png").split(";")[0]
    expr = _read_captcha_expression(ir.content, media)
    m = re.match(r'^(\d+)\s*([+\-xX*])\s*(\d+)$', expr)
    if not m:
        log.warning("captcha expression unparseable: %r", expr)
        return None
    a, op, b = int(m.group(1)), m.group(2), int(m.group(3))
    ans = a + b if op == "+" else (a - b if op == "-" else a * b)
    log.debug("captcha %s = %s", expr, ans)
    return str(ans)


# ── page tokens ────────────────────────────────────────────────────────────────

def _load_search_tokens(session: requests.Session) -> tuple[str, str, str]:
    """Return (scid, tok_name, tok_value) freshly from the search page."""
    t = session.get(config.SCI_PAGE, timeout=config.REQUEST_TIMEOUT).text
    scid = re.search(r'name="scid"\s+value="([^"]+)"', t).group(1)
    tok = re.search(r'name="(tok_[0-9a-f]+)"\s+value="([^"]+)"', t)
    return scid, tok.group(1), tok.group(2)


# ── row parsing ────────────────────────────────────────────────────────────────

def _clean(s: str) -> str:
    return " ".join((s or "").split()).strip()


def _parse_rows(results_html: str) -> list[dict]:
    soup = BeautifulSoup(results_html, "html.parser")
    out = []
    for tr in soup.select("table tr"):
        tds = tr.find_all("td")
        if len(tds) < 8:
            continue  # header / spacer
        cell = [_clean(td.get_text(" ", strip=True)) for td in tds]
        # all pdf links in the judgment cell; prefer English
        links = [a["href"] for a in tds[7].find_all("a", href=True) if ".pdf" in a["href"].lower()]
        pdf_url = links[0] if links else ""
        citation = ""
        cm = re.search(r"\d{4}\s+INSC\s+\d+", cell[7])
        if cm:
            citation = cm.group(0)
        jdate = ""
        dm = re.search(r"\d{2}-\d{2}-\d{4}", cell[7])
        if dm:
            jdate = dm.group(0)
        out.append({
            "serial": cell[0],
            "diary": cell[1],
            "case_number": cell[2],
            "parties": cell[3],
            "advocates": cell[4],
            "bench": cell[5],
            "judgment_by": cell[6],
            "citation": citation,
            "judgment_date": jdate,
            "pdf_url": pdf_url,
        })
    return out


# ── search ─────────────────────────────────────────────────────────────────────

def _do_search(session, scid, tok_name, tok_value, answer, ddmmyyyy) -> dict:
    params = {
        "action": config.SEARCH_ACTION,
        "es_ajax_request": "1",
        "language": "en",
        "from_date": ddmmyyyy,
        "to_date": ddmmyyyy,
        "scid": scid,
        "siwp_captcha_value": answer,
        tok_name: tok_value,
        "submit": "Search",
    }
    r = session.get(config.SCI_AJAX, params=params, timeout=config.REQUEST_TIMEOUT)
    return r.json()


def _fetch_extra_pages(session, ddmmyyyy, pagination_html) -> list[dict]:
    """Follow pagination links (no captcha needed once the session is validated)."""
    soup = BeautifulSoup(pagination_html, "html.parser")
    pag = soup.find(attrs={"data-nonce": True})
    if not pag:
        return []
    nonce = pag["data-nonce"]
    page_ids = sorted({a.get("data-page-id") for a in soup.find_all(attrs={"data-page-id": True})
                       if a.get("data-page-id") and a.get("data-page-id") != "1"})
    rows = []
    for pid in page_ids:
        params = {
            "action": config.SEARCH_ACTION, "es_ajax_request": "1", "language": "en",
            "from_date": ddmmyyyy, "to_date": ddmmyyyy,
            "sci_page": pid, "sci_pagination_nonce": nonce,
        }
        try:
            j = session.get(config.SCI_AJAX, params=params, timeout=config.REQUEST_TIMEOUT).json()
            rows.extend(_parse_rows(j.get("data", {}).get("resultsHtml", "")))
        except Exception as e:
            log.warning("pagination page %s failed: %s", pid, e)
    return rows


def fetch_judgments(date: datetime.date) -> list[dict]:
    """Return all judgments for a single date. May be an empty list."""
    ddmmyyyy = date.strftime("%d-%m-%Y")
    session = make_session()
    for attempt in range(1, config.MAX_CAPTCHA_RETRIES + 1):
        try:
            scid, tname, tval = _load_search_tokens(session)
            answer = _solve_captcha(session, scid)
            if answer is None:
                continue
            j = _do_search(session, scid, tname, tval, answer, ddmmyyyy)
        except Exception as e:
            log.warning("search attempt %d errored: %s", attempt, e)
            time.sleep(1)
            continue
        if j.get("success"):
            data = j.get("data", {})
            rows = _parse_rows(data.get("resultsHtml", ""))
            if data.get("paginationHtml"):
                rows += _fetch_extra_pages(session, ddmmyyyy, data["paginationHtml"])
            # de-dup by pdf_url / case_number
            seen, uniq = set(), []
            for r in rows:
                key = r["pdf_url"] or (r["case_number"] + r["parties"])
                if key in seen:
                    continue
                seen.add(key)
                uniq.append(r)
            log.info("%s -> %d judgments", ddmmyyyy, len(uniq))
            return uniq
        msg = (j.get("data") or {})
        msg = msg.get("message", "") if isinstance(msg, dict) else str(msg)
        if "captcha" in msg.lower():
            log.info("captcha attempt %d wrong, retrying", attempt)
            continue
        # genuine 'no records' style response -> treat as empty day
        log.info("search returned success=False (%s) -> empty", msg[:80])
        return []
    raise RuntimeError(f"Could not solve captcha after {config.MAX_CAPTCHA_RETRIES} attempts")


# ── filenames + download ────────────────────────────────────────────────────────

_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def case_filename(parties: str, existing: set[str]) -> str:
    """Turn 'THE STATE OF WEST BENGAL VS ANIL KUMAR DEY' into a clean, unique
    'The State Of West Bengal vs Anil Kumar Dey.pdf'."""
    name = _clean(parties).title()
    name = re.sub(r'\bVs\b', 'vs', name)
    name = _ILLEGAL.sub("", name).strip(" .")
    if not name:
        name = "Judgment"
    if len(name) > 120:
        name = name[:120].rstrip(" .")
    base, candidate, n = name, name + ".pdf", 2
    while candidate.lower() in existing:
        candidate = f"{base} ({n}).pdf"
        n += 1
    existing.add(candidate.lower())
    return candidate


def download_pdf(session: requests.Session, url: str, dest) -> bool:
    if dest.exists() and dest.stat().st_size > 0:
        return True
    try:
        r = session.get(url, timeout=config.DOWNLOAD_TIMEOUT)
        r.raise_for_status()
        dest.write_bytes(r.content)
        return True
    except Exception as e:
        log.warning("download failed %s: %s", url, e)
        return False
