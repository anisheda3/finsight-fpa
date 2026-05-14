"""HTML email + PDF attachment via SMTP."""
from __future__ import annotations

import base64
import logging
import smtplib
from email.message import EmailMessage
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def send_email(*, to: str, subject: str, html_body: str,
               pdf_attachment_b64: str | None = None) -> dict[str, Any]:
    s = get_settings()
    if not s.smtp_host:
        logger.info("smtp not configured; would email %s subject=%r", to, subject)
        return {"channel": "email", "target": to, "delivery_status": "PENDING"}

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = s.smtp_user or "noreply@example.com"
    msg["To"] = to
    msg.set_content("View this message in HTML.")
    msg.add_alternative(html_body, subtype="html")
    if pdf_attachment_b64:
        try:
            data = base64.b64decode(pdf_attachment_b64)
            msg.add_attachment(data, maintype="application", subtype="pdf",
                               filename="finsight_report.pdf")
        except Exception as e:
            logger.warning("could not attach pdf: %s", e)

    try:
        with smtplib.SMTP(s.smtp_host, s.smtp_port) as srv:
            srv.starttls()
            if s.smtp_user and s.smtp_password:
                srv.login(s.smtp_user, s.smtp_password)
            srv.send_message(msg)
        return {"channel": "email", "target": to, "delivery_status": "SENT"}
    except Exception as e:                                   # pragma: no cover
        logger.exception("smtp send failed: %s", e)
        return {"channel": "email", "target": to,
                "delivery_status": "FAILED", "error": str(e)}


def render_pdf_from_html(html: str) -> bytes:
    """Best-effort PDF render — tries weasyprint first, then xhtml2pdf."""
    try:                                                     # pragma: no cover
        from weasyprint import HTML
        return HTML(string=html).write_pdf()
    except Exception:
        pass
    try:
        from io import BytesIO
        from xhtml2pdf import pisa                          # type: ignore
        buf = BytesIO()
        pisa.CreatePDF(html, dest=buf)
        return buf.getvalue()
    except Exception as e:                                   # pragma: no cover
        logger.warning("no PDF backend available: %s", e)
        return b""
