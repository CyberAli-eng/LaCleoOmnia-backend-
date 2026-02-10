"""
Optional email sending for password reset. Uses SMTP when configured.
"""
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)


def send_password_reset_email(to_email: str, reset_link: str, user_name: Optional[str] = None) -> bool:
    """
    Send password reset email. Returns True if sent, False if skipped or failed.
    Requires SMTP_HOST and SMTP_USER (and SMTP_PASSWORD if auth needed).
    """
    if not (getattr(settings, "SMTP_HOST", None) or "").strip():
        return False
    host = (settings.SMTP_HOST or "").strip()
    port = getattr(settings, "SMTP_PORT", 587) or 587
    user = (getattr(settings, "SMTP_USER", None) or "").strip()
    password = (getattr(settings, "SMTP_PASSWORD", None) or "").strip()
    use_tls = getattr(settings, "SMTP_USE_TLS", True)
    from_addr = (getattr(settings, "EMAIL_FROM", None) or "noreply@lacleoomnia.com").strip()

    subject = "Reset your password"
    greeting = f"Hi {user_name or 'there'}," if user_name else "Hi,"
    body = f"""{greeting}

You requested a password reset. Click the link below to set a new password (valid for 24 hours):

{reset_link}

If you didn't request this, you can ignore this email.

— LaCleo Omnia
"""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_email
    msg.attach(MIMEText(body, "plain"))

    try:
        if use_tls:
            with smtplib.SMTP(host, port) as server:
                server.starttls()
                if user and password:
                    server.login(user, password)
                server.sendmail(from_addr, [to_email], msg.as_string())
        else:
            with smtplib.SMTP(host, port) as server:
                if user and password:
                    server.login(user, password)
                server.sendmail(from_addr, [to_email], msg.as_string())
        logger.info("Password reset email sent to %s", to_email)
        return True
    except Exception as e:
        logger.warning("Failed to send password reset email to %s: %s", to_email, e)
        return False
