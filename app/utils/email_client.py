"""
Async email notification client using Gmail SMTP.
Used to alert the team about new leads and unanswered queries.
"""

import smtplib
import asyncio
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from app.config import settings
from app.utils.logger import logger


def _send_email_sync(subject: str, body: str) -> None:
    """Synchronous email send, run in a thread pool to avoid blocking the event loop."""
    msg = MIMEMultipart()
    msg["From"] = settings.smtp_user
    msg["To"] = settings.notify_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
        server.starttls()
        server.login(settings.smtp_user, settings.smtp_password)
        server.sendmail(settings.smtp_user, settings.notify_email, msg.as_string())


async def send_team_notification(subject: str, body: str) -> None:
    """
    Send a notification email to the team. Failures are logged but never
    raised — a notification failure should never break the main chat flow.
    """
    if not settings.smtp_user or not settings.notify_email:
        logger.warning(
            "Email notification skipped — SMTP_USER or NOTIFY_EMAIL not configured."
        )
        return

    try:
        await asyncio.to_thread(_send_email_sync, subject, body)
        logger.info(f"Team notification email sent: {subject}")
    except Exception as e:
        logger.error(f"Failed to send team notification email: {e}")
