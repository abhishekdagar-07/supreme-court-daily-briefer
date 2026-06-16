"""Supreme Court Daily Judgment Briefer — main entry point.

Scheduled modes (used by Task Scheduler):
  --prepare   Gather + brief the most recent court day. Saves to Desktop. No send.
              Runs at 2 PM, and again at 10:30 PM as a fallback (idempotent).
  --send      Ensure the brief is prepared, then email it. Runs at 10:35 PM.
              This is the ONLY mode that sends the email.

On-demand modes (used by the double-click runner / terminal):
  --latest        Most recent court day with judgments — gather, brief AND send now.
  --date 10-12-2025   A specific date — gather, brief AND send now.
  --no-send       With --latest/--date: save files only, don't send email.
  --force         Ignore the once-per-day guards (prepare/send).
"""
import sys
import time
import json
import logging
import argparse
import datetime
import pathlib

import config
import sci_client
import brief
import worddoc
import email_notify as notify
import power


# ── logging ────────────────────────────────────────────────────────────────────

def setup_logging():
    logfile = config.LOG_DIR / f"run_{datetime.date.today():%Y%m}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        handlers=[logging.FileHandler(logfile, encoding="utf-8"),
                  logging.StreamHandler(sys.stdout)])
    return logging.getLogger("main")


# ── state ───────────────────────────────────────────────────────────────────────
# done_dates : judgment-dates already delivered OR confirmed empty (won't re-check)
# pending    : a prepared brief waiting to be sent (or a "no new" marker)
# prepared_on/sent_on : calendar dates of the last prepare/send (once-per-day guards)

def load_state() -> dict:
    if config.STATE_FILE.exists():
        try:
            s = json.loads(config.STATE_FILE.read_text())
        except Exception:
            s = {}
    else:
        s = {}
    s.setdefault("done_dates", [])
    s.setdefault("pending", None)
    s.setdefault("prepared_on", "")
    s.setdefault("sent_on", "")
    return s


def save_state(state: dict):
    config.STATE_FILE.write_text(json.dumps(state, indent=2))


# ── core: build the brief for one date ──────────────────────────────────────────

def _build_for(date: datetime.date, rows: list[dict], log) -> dict:
    """Download PDFs + headnotes + Word doc for a date whose rows are known.
    Returns {count, doc_path, items}."""
    day_dir = config.date_folder(date)
    session = sci_client.make_session()
    items, names = [], set()
    for i, r in enumerate(rows, 1):
        fname = sci_client.case_filename(r["parties"], names)
        log.info("[%d/%d] %s", i, len(rows), fname)
        pdf_path = day_dir / fname
        ok = sci_client.download_pdf(session, r["pdf_url"], pdf_path) if r["pdf_url"] else False
        text = brief.extract_text(pdf_path)[0] if ok else ""
        headnote = brief.generate_headnote(r, text, pdf_path if ok else None)
        items.append({"meta": r, "headnote": headnote, "filename": fname if ok else ""})
        time.sleep(config.POLITE_DELAY)
    doc_path = worddoc.build_document(date, items)
    log.info("brief ready: %s", doc_path)
    return {"count": len(items), "doc_path": doc_path, "items": items}


def process_date(date: datetime.date, log) -> dict:
    """Fetch rows then build the brief for a date. {count, doc_path, items}."""
    rows = sci_client.fetch_judgments(date)
    if not rows:
        log.info("no judgments for %s", date)
        return {"count": 0, "doc_path": None, "items": []}
    return _build_for(date, rows, log)


# ── scheduled mode: PREPARE (no send) ───────────────────────────────────────────

def do_prepare(log, state: dict, force: bool) -> dict:
    today = datetime.date.today()
    if not force and state["prepared_on"] == today.isoformat() and state["pending"] is not None:
        log.info("already prepared today; skipping prepare.")
        return state

    done = set(state["done_dates"])
    target, rows = None, None
    for k in range(1, config.LOOKBACK_DAYS + 1):
        d = today - datetime.timedelta(days=k)
        if d.isoformat() in done:
            continue
        found = sci_client.fetch_judgments(d)
        if found:
            target, rows = d, found
            break
        # confirmed-empty day: never re-check it
        done.add(d.isoformat())
        state["done_dates"] = sorted(done)[-90:]
        save_state(state)

    if target:
        res = _build_for(target, rows, log)
        preview = notify.build_preview(target, res["items"])
        state["pending"] = {
            "judgment_date": target.isoformat(),
            "doc_path": str(res["doc_path"]),
            "preview": preview,
            "count": res["count"],
        }
        log.info("prepared brief for %s (%d judgment(s)) — awaiting 10:35 PM send",
                 target, res["count"])
    else:
        state["pending"] = {"judgment_date": None, "doc_path": None, "preview": None, "count": 0}
        log.info("nothing new to prepare in the last %d days", config.LOOKBACK_DAYS)

    state["prepared_on"] = today.isoformat()
    save_state(state)
    return state


# ── scheduled mode: SEND (the only phone message) ───────────────────────────────

def do_send(log, state: dict, force: bool):
    today = datetime.date.today()
    if not force and state["sent_on"] == today.isoformat():
        log.info("already sent today; skipping send.")
        return

    # Make sure a brief was prepared today (self-heal after a missed 2 PM / shutdown).
    if state["prepared_on"] != today.isoformat() or state["pending"] is None:
        log.info("not prepared yet today — preparing now before send.")
        state = do_prepare(log, state, force=True)

    pending = state["pending"] or {}
    jdate = pending.get("judgment_date")

    if jdate:
        doc = pathlib.Path(pending["doc_path"]) if pending.get("doc_path") else None
        if not doc or not doc.exists():
            log.warning("prepared file missing — re-preparing before send.")
            state = do_prepare(log, state, force=True)
            pending = state["pending"] or {}
            jdate = pending.get("judgment_date")
            doc = pathlib.Path(pending["doc_path"]) if pending.get("doc_path") else None

    if jdate and doc and doc.exists():
        subject = f"Supreme Court Daily Brief — {jdate} ({pending['count']} judgment(s))"
        if not notify.is_configured():
            log.warning("Email not configured — cannot send. Keeping brief pending for %s.", jdate)
        elif _send_with_retries(subject, pending["preview"], doc, log):
            done = set(state["done_dates"]); done.add(jdate)
            state["done_dates"] = sorted(done)[-90:]
            state["pending"] = None
            log.info("emailed brief for %s", jdate)
        else:
            log.warning("Email send failed after %d attempts — keeping brief pending.",
                        config.SEND_MAX_ATTEMPTS)
    else:
        d = today - datetime.timedelta(days=1)
        if notify.is_configured():
            notify.deliver_status(f"No new Supreme Court judgments to report (checked up to {d:%d %b %Y}).")
            log.info("sent 'no new judgments' status email")
        else:
            log.warning("Email not configured — skipping 'no new judgments' status.")

    state["sent_on"] = today.isoformat()
    save_state(state)


def _send_with_retries(subject: str, body: str, doc, log) -> bool:
    """Email the prepared brief, retrying up to SEND_MAX_ATTEMPTS."""
    for attempt in range(1, config.SEND_MAX_ATTEMPTS + 1):
        if notify.send_prepared(subject, body, doc):
            return True
        log.warning("email attempt %d/%d failed", attempt, config.SEND_MAX_ATTEMPTS)
        if attempt < config.SEND_MAX_ATTEMPTS:
            time.sleep(config.SEND_RETRY_DELAY)
    return False


# ── on-demand modes ─────────────────────────────────────────────────────────────

def parse_date(s: str) -> datetime.date:
    for fmt in ("%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise SystemExit(f"Bad --date '{s}'. Use DD-MM-YYYY or YYYY-MM-DD.")


def run_immediate(date: datetime.date, log, send: bool):
    """Gather + brief + (optionally) send right now — used by --date / --latest."""
    res = process_date(date, log)
    if res["count"] > 0:
        if send and notify.deliver_brief(date, res["items"], res["doc_path"]):
            log.info("emailed brief")
        elif send:
            log.warning("Email delivery skipped/failed (see config)")
    elif send:
        notify.deliver_status(f"No Supreme Court judgments found for {date:%d %b %Y}.")
    return res["count"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prepare", action="store_true")
    ap.add_argument("--send", action="store_true")
    ap.add_argument("--latest", action="store_true")
    ap.add_argument("--date")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--no-send", action="store_true")
    args = ap.parse_args()
    log = setup_logging()

    try:
        if args.prepare:
            log.info("=== PREPARE ===")
            do_prepare(log, load_state(), force=args.force)
            return
        if args.send:
            log.info("=== SEND ===")
            try:
                do_send(log, load_state(), force=args.force)
            except Exception:
                log.exception("send run failed")
            finally:
                # This step may have woken the PC; sleep it again if the user is away.
                power.maybe_sleep("after 10:35 PM send")
            return

        send = not args.no_send
        if args.latest:
            log.info("=== on-demand latest run ===")
            today = datetime.date.today()
            for k in range(1, config.LOOKBACK_DAYS + 1):
                if run_immediate(today - datetime.timedelta(days=k), log, send) > 0:
                    return
            if send:
                notify.deliver_status(f"No Supreme Court judgments found in the last {config.LOOKBACK_DAYS} days.")
            return
        if args.date:
            d = parse_date(args.date)
            log.info("=== manual run for %s ===", d)
            run_immediate(d, log, send)
            return

        # Default with no mode flag: behave like an immediate latest run.
        log.info("=== default run (latest) ===")
        today = datetime.date.today()
        for k in range(1, config.LOOKBACK_DAYS + 1):
            if run_immediate(today - datetime.timedelta(days=k), log, True) > 0:
                return
        notify.deliver_status(f"No Supreme Court judgments found in the last {config.LOOKBACK_DAYS} days.")
    except Exception as e:
        log.exception("run failed")
        if not args.no_send:
            notify.deliver_status(f"Supreme Court brief run failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
