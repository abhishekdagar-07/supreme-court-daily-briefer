"""Extracts judgment text and asks Claude (Haiku) for a structured headnote.

Most SCI judgments are born-digital PDFs with a real text layer, so we read the
text directly. For the rare scanned/garbled one we fall back to Claude Vision.
"""
import json
import re
import base64
import logging

import fitz  # PyMuPDF
import anthropic

import config

log = logging.getLogger("brief")
_client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

MAX_TEXT_CHARS = 150_000  # cap input per judgment (~38k tokens) to control cost


# ── text extraction ────────────────────────────────────────────────────────────

def extract_text(pdf_path) -> tuple[str, int]:
    """Return (text, page_count). Empty/garbled text signals a scanned PDF."""
    doc = fitz.open(str(pdf_path))
    pages = min(len(doc), config.MAX_PDF_PAGES)
    parts = [doc[i].get_text() for i in range(pages)]
    n = len(doc)
    doc.close()
    return "\n".join(parts), n


def _looks_scanned(text: str) -> bool:
    return len(text.strip()) < 400


def _vision_text(pdf_path, max_pages: int = 12) -> str:
    """Fallback OCR via Claude Vision for scanned judgments."""
    doc = fitz.open(str(pdf_path))
    content = []
    for i in range(min(len(doc), max_pages)):
        pix = doc[i].get_pixmap(matrix=fitz.Matrix(200/72, 200/72), colorspace=fitz.csRGB)
        content.append({"type": "image", "source": {
            "type": "base64", "media_type": "image/png",
            "data": base64.standard_b64encode(pix.tobytes("png")).decode()}})
    doc.close()
    content.append({"type": "text", "text": "Transcribe all readable text from these "
                                            "judgment pages verbatim. Output only the text."})
    msg = _client.messages.create(model=config.BRIEF_MODEL, max_tokens=4000,
                                  messages=[{"role": "user", "content": content}])
    return msg.content[0].text


# ── headnote generation ────────────────────────────────────────────────────────

_PROMPT = """You are a senior legal editor preparing a law-report headnote for a Supreme Court of India judgment.

Known metadata (already verified, use as-is):
- Case: {parties}
- Case number: {case_number}
- Neutral citation: {citation}
- Date of judgment: {judgment_date}
- Bench: {bench}
- Judgment authored by: {judgment_by}
- Counsel on record: {advocates}

Below is the full text of the judgment. Read it and produce a precise, neutral headnote.

Return ONLY a valid JSON object (no markdown fences) with these exact keys:
- "one_line_holding": one crisp sentence (max 30 words) stating what the Court decided. For a phone preview.
- "issues": the legal question(s) before the Court, as 1-3 short bullet-style sentences.
- "facts": 3-6 sentences of the relevant background and procedural history.
- "holding": what the Court held and the outcome (allowed/dismissed/etc.), 2-4 sentences.
- "ratio": the core legal reasoning / principle laid down, 2-5 sentences.
- "final_order": the operative directions actually ordered by the Court.
- "subject": a short subject tag (e.g. "Criminal - Bail", "Service Law", "Tax").

If something genuinely cannot be determined from the text, use "Not stated in judgment".

JUDGMENT TEXT:
{text}
"""

_FIELDS = ["one_line_holding", "issues", "facts", "holding", "ratio", "final_order", "subject"]


def generate_headnote(meta: dict, text: str, pdf_path=None) -> dict:
    if _looks_scanned(text) and pdf_path is not None:
        log.info("text layer thin, using Vision OCR fallback for %s", meta.get("parties", "")[:40])
        try:
            text = _vision_text(pdf_path)
        except Exception as e:
            log.warning("vision fallback failed: %s", e)
    text = text[:MAX_TEXT_CHARS]

    prompt = _PROMPT.format(
        parties=meta.get("parties", ""), case_number=meta.get("case_number", ""),
        citation=meta.get("citation", ""), judgment_date=meta.get("judgment_date", ""),
        bench=meta.get("bench", ""), judgment_by=meta.get("judgment_by", ""),
        advocates=meta.get("advocates", ""), text=text)
    try:
        msg = _client.messages.create(model=config.BRIEF_MODEL, max_tokens=1500,
                                      messages=[{"role": "user", "content": prompt}])
        raw = msg.content[0].text.strip()
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
        data = json.loads(raw)
    except Exception as e:
        log.warning("headnote generation failed for %s: %s", meta.get("parties", "")[:40], e)
        data = {}
    # ensure all keys exist
    for k in _FIELDS:
        data.setdefault(k, "Not stated in judgment")
    return data
