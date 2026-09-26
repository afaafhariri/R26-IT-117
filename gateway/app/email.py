"""Outgoing email: the messages the auth flows send, and how they're delivered."""

import asyncio
import logging
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol

import httpx

from app.config import Settings

logger = logging.getLogger("gateway.email")

PRODUCT = "Construction Planner"


@dataclass(frozen=True)
class Email:
    to: str
    subject: str
    text: str


class EmailSender(Protocol):
    async def send(self, email: Email) -> None: ...


class ConsoleSender:
    """Writes each email to the log. The links in them are live credentials,
    so this is for local development only."""

    async def send(self, email: Email) -> None:
        logger.warning("Email to %s: %s\n\n%s", email.to, email.subject, email.text)


class SmtpSender:
    """Plain SMTP with no login or TLS, which is what Mailpit expects locally."""

    def __init__(self, settings: Settings):
        self.sender = settings.email_from
        self.host = settings.smtp_host
        self.port = settings.smtp_port

    async def send(self, email: Email) -> None:
        await asyncio.to_thread(self._send, email)

    def _send(self, email: Email) -> None:
        message = EmailMessage()
        message["From"] = self.sender
        message["To"] = email.to
        message["Subject"] = email.subject
        message.set_content(email.text)
        with smtplib.SMTP(self.host, self.port, timeout=10) as smtp:
            smtp.send_message(message)


class ResendSender:
    URL = "https://api.resend.com/emails"

    def __init__(self, settings: Settings, client: httpx.AsyncClient):
        self.sender = settings.email_from
        self.api_key = settings.resend_api_key
        self.client = client

    async def send(self, email: Email) -> None:
        response = await self.client.post(
            self.URL,
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "from": self.sender,
                "to": [email.to],
                "subject": email.subject,
                "text": email.text,
            },
            timeout=10,
        )
        response.raise_for_status()


def make_sender(settings: Settings, client: httpx.AsyncClient) -> EmailSender:
    if settings.email_backend == "resend":
        if not settings.resend_api_key:
            raise RuntimeError("EMAIL_BACKEND=resend needs RESEND_API_KEY.")
        return ResendSender(settings, client)
    if settings.email_backend == "smtp":
        return SmtpSender(settings)
    if settings.email_backend == "console":
        return ConsoleSender()
    raise RuntimeError(f"Unknown EMAIL_BACKEND {settings.email_backend!r}.")


async def deliver(sender: EmailSender, email: Email) -> None:
    """Runs after the response has gone out, so a failure is logged rather
    than raised. The response must not depend on it anyway: it would reveal
    whether the address has an account."""
    try:
        await sender.send(email)
    except Exception:
        logger.exception("Failed to send the '%s' email", email.subject)


# ── Messages ──────────────────────────────────────────────────────────────────


def verify_email_message(to: str, link: str) -> Email:
    return Email(
        to=to,
        subject=f"Confirm your email for {PRODUCT}",
        text=(
            f"Open this link to confirm your email address and finish setting up "
            f"your {PRODUCT} account. You'll be asked for the password you chose.\n\n"
            f"{link}\n\n"
            f"The link works once and expires in 24 hours.\n\n"
            f"If you didn't sign up, ignore this email and no account will be activated."
        ),
    )


def account_exists_message(to: str, login_link: str, reset_link: str) -> Email:
    return Email(
        to=to,
        subject=f"You already have a {PRODUCT} account",
        text=(
            f"Someone, hopefully you, tried to sign up to {PRODUCT} with this "
            f"email address. There is already an account for it.\n\n"
            f"Log in: {login_link}\n"
            f"Forgot your password? Reset it: {reset_link}\n\n"
            f"If this wasn't you, you can ignore this email. Nothing has changed."
        ),
    )


def reset_password_message(to: str, link: str) -> Email:
    return Email(
        to=to,
        subject=f"Reset your {PRODUCT} password",
        text=(
            f"Open this link to choose a new password:\n\n"
            f"{link}\n\n"
            f"The link works once and expires in 30 minutes.\n\n"
            f"If you didn't ask for this, ignore this email. Your password stays the same."
        ),
    )


def password_changed_message(to: str, reset_link: str) -> Email:
    return Email(
        to=to,
        subject=f"Your {PRODUCT} password was changed",
        text=(
            f"The password for your {PRODUCT} account was just changed, and every "
            f"device that was signed in has been signed out.\n\n"
            f"If you didn't do this, reset your password now: {reset_link}"
        ),
    )
