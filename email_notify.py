"""Delivers the daily brief by email (Gmail SMTP with an app password).

Sends one email per day: a readable text preview (one line per judgment) in the
body, with the combined Word document attached. On empty/failure days it sends a
short status email instead.
"""
import ssl
import smtplib
import logging
from email.message import EmailMessage

import config

log = logging.getLogger("email")

DOCX_MIME = ("application", "vnd.openxmlformats-officedocument.wordprocessingml.document")


def is_configured() -> bool:
    return bool(config.EMAIL_ADDRESS and config.EMAIL_APP_PASSWORD and config.EMAIL_TO)


def build_preview(date, items: list[dict]) -> str:
    """Plain-text body listing each case + a one-line holding."""
    lines = [f"Supreme Court of India — Daily Judgments Brief",
             date.strftime("%A, %d %B %Y"),
             f"{len(items)} judgment(s)", ""]
    for i, it in enumerate(items, 1):
        m, h = it["meta"], it["headnote"]
        one = h.get("one_line_holding")
        if isinstance(one, list):
            one = one[0] if one else ""
        cite = f" ({m.get('citation','')})" if m.get("citation") else ""
        lines.append(f"{i}. {m.get('parties','')}{cite}")
        lines.append(f"   {one}")
        lines.append("")
    lines.append("— The full headnotes are in the attached Word document.")
    return "\n".join(lines)


def _send(subject: str, body: str, attachment=None) -> bool:
    if not is_configured():
        log.info("email not configured; would send: %s", subject)
        return False
    msg = EmailMessage()
    msg["From"] = config.EMAIL_ADDRESS
    msg["To"] = config.EMAIL_TO
    msg["Subject"] = subject
    msg.set_content(body)
    if attachment is not None:
        with open(attachment, "rb") as f:
            data = f.read()
        name = attachment.name if hasattr(attachment, "name") else str(attachment)
        msg.add_attachment(data, maintype=DOCX_MIME[0], subtype=DOCX_MIME[1], filename=name)
    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT, context=ctx, timeout=60) as s:
            s.login(config.EMAIL_ADDRESS, config.EMAIL_APP_PASSWORD)
            s.send_message(msg)
        log.info("email sent: %s", subject)
        return True
    except Exception as e:
        log.warning("email send failed: %s", e)
        return False


def send_prepared(subject: str, body: str, doc_path) -> bool:
    """Send the prepared brief (body + attached Word doc). Used by the retry loop."""
    return _send(subject, body, attachment=doc_path)


def deliver_brief(date, items: list[dict], doc_path) -> bool:
    """One-shot deliver (manual on-demand runs)."""
    subject = f"Supreme Court Daily Brief — {date:%d %b %Y} ({len(items)} judgment(s))"
    return _send(subject, build_preview(date, items), attachment=doc_path)


def deliver_status(text: str) -> bool:
    """Plain status email (no judgments / failure)."""
    return _send("Supreme Court Daily Brief — status", text)
