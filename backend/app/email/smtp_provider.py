from __future__ import annotations

import smtplib
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config.settings import settings
from app.email.interfaces import EmailProvider
from app.logging_config import get_logger

logger = get_logger(__name__)


class SmtpEmailProvider(EmailProvider):
    def send_email(
        self,
        recipients: list[str],
        subject: str,
        html_body: str,
        text_body: str,
        images: list[tuple[str, bytes]] | None = None,
    ) -> bool:
        # Build multipart/related (wrapping alternative) when images are present
        if images:
            msg = MIMEMultipart("related")
            alt = MIMEMultipart("alternative")
            alt.attach(MIMEText(text_body, "plain"))
            alt.attach(MIMEText(html_body, "html"))
            msg.attach(alt)
            for cid, png_bytes in images:
                img = MIMEImage(png_bytes, _subtype="png")
                img.add_header("Content-ID", f"<{cid}>")
                img.add_header("Content-Disposition", "inline", filename=f"{cid}.png")
                msg.attach(img)
        else:
            msg = MIMEMultipart("alternative")
            msg.attach(MIMEText(text_body, "plain"))
            msg.attach(MIMEText(html_body, "html"))

        msg["Subject"] = subject
        msg["From"] = settings.SMTP_SENDER or settings.SMTP_USERNAME
        msg["To"] = ", ".join(recipients)

        try:
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
                if settings.SMTP_USE_TLS:
                    server.starttls()
                server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                server.sendmail(msg["From"], recipients, msg.as_string())

            logger.info(
                "email_sent_smtp",
                recipients=recipients,
                subject=subject,
                image_count=len(images) if images else 0,
            )
            return True
        except Exception:
            logger.exception(
                "email_send_failed",
                recipients=recipients,
                subject=subject,
            )
            raise
