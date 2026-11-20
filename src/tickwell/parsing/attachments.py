"""Turn order attachments (PDF, Excel, CSV, text) into plain text for the extractor."""

import io
import logging

log = logging.getLogger(__name__)


def extract_attachment_text(filename: str, content_type: str, data: bytes) -> str:
    name = filename.lower()
    try:
        if name.endswith(".pdf") or content_type == "application/pdf":
            return _pdf(data)
        if name.endswith((".xlsx", ".xlsm")):
            return _xlsx(data)
        if name.endswith((".csv", ".txt")) or content_type.startswith("text/"):
            return data.decode("utf-8", errors="replace")
    except Exception as exc:  # a broken attachment must never stop the email
        log.warning("Could not read attachment %s: %s", filename, exc)
    return ""


def _pdf(data: bytes) -> str:
    import pdfplumber

    pages = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            pages.append(page.extract_text() or "")
    return "\n".join(pages).strip()


def _xlsx(data: bytes) -> str:
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    rows = []
    for ws in wb.worksheets:
        for row in ws.iter_rows(values_only=True):
            cells = ["" if c is None else str(c) for c in row]
            if any(cells):
                rows.append("\t".join(cells).rstrip())
    return "\n".join(rows)
