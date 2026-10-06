"""Certificate rendering. Single predefined template, drawn with reportlab."""
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas


def _fit_font_size(text: str, font: str, max_size: float, max_width: float) -> float:
    size = max_size
    while size > 12 and stringWidth(text, font, size) > max_width:
        size -= 1
    return size


def generate_certificate_pdf(
    path: Path,
    *,
    name: str,
    event_name: str,
    issue_date: str,
    issued_by: str = "",
    course: str | None = None,
    certificate_id: str = "",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    w, h = landscape(A4)
    c = canvas.Canvas(str(path), pagesize=(w, h))
    c.setTitle(f"Certificate - {name}")

    navy, gold, grey = colors.HexColor("#1f3a5f"), colors.HexColor("#b8923a"), colors.HexColor("#444444")

    # Double border
    c.setStrokeColor(navy); c.setLineWidth(6); c.rect(25, 25, w - 50, h - 50)
    c.setStrokeColor(gold); c.setLineWidth(1.5); c.rect(40, 40, w - 80, h - 80)

    c.setFillColor(navy)
    c.setFont("Helvetica-Bold", 38)
    c.drawCentredString(w / 2, h - 130, "CERTIFICATE OF COMPLETION")

    c.setFillColor(grey)
    c.setFont("Helvetica", 16)
    c.drawCentredString(w / 2, h - 185, "This is proudly presented to")

    max_w = w - 160
    size = _fit_font_size(name, "Helvetica-BoldOblique", 40, max_w)
    c.setFillColor(gold)
    c.setFont("Helvetica-BoldOblique", size)
    c.drawCentredString(w / 2, h - 250, name)
    c.setStrokeColor(gold); c.setLineWidth(1)
    c.line(w / 2 - 220, h - 262, w / 2 + 220, h - 262)

    c.setFillColor(grey)
    c.setFont("Helvetica", 16)
    c.drawCentredString(w / 2, h - 305, "for successfully completing")
    ev_size = _fit_font_size(event_name, "Helvetica-Bold", 24, max_w)
    c.setFillColor(navy); c.setFont("Helvetica-Bold", ev_size)
    c.drawCentredString(w / 2, h - 340, event_name)
    if course:
        c.setFillColor(grey); c.setFont("Helvetica", 14)
        c.drawCentredString(w / 2, h - 368, course)

    c.setFillColor(grey); c.setFont("Helvetica", 12)
    c.drawString(80, 80, f"Date: {issue_date}")
    if issued_by:
        c.drawRightString(w - 80, 80, f"Issued by: {issued_by}")
    c.setFont("Helvetica", 8); c.setFillColor(colors.grey)
    c.drawCentredString(w / 2, 55, f"Certificate ID: {certificate_id}")

    c.showPage()
    c.save()
