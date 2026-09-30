from __future__ import annotations

import os
import smtplib
import urllib.parse
from dataclasses import dataclass
from email.message import EmailMessage

import requests


@dataclass(frozen=True)
class AlertMessage:
    subject: str
    body: str


class EmailNotifier:
    def enabled(self) -> bool:
        return all(
            os.getenv(k)
            for k in ["SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "ALERT_EMAIL_TO"]
        )

    def send(self, msg: AlertMessage) -> None:
        if not self.enabled():
            return

        email = EmailMessage()
        email["From"] = os.environ["SMTP_USER"]
        email["To"] = os.environ["ALERT_EMAIL_TO"]
        email["Subject"] = msg.subject
        email.set_content(msg.body)

        with smtplib.SMTP(os.environ["SMTP_HOST"], int(os.environ["SMTP_PORT"])) as smtp:
            smtp.starttls()
            smtp.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
            smtp.send_message(email)


class TelegramBotNotifier:
    def enabled(self) -> bool:
        return bool(os.getenv("TELEGRAM_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"))

    def send(self, msg: AlertMessage) -> None:
        if not self.enabled():
            return
        text = f"{msg.subject}\n\n{msg.body}"
        token = os.environ["TELEGRAM_TOKEN"]
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = {
            "chat_id": os.environ["TELEGRAM_CHAT_ID"],
            "text": text,
        }
        response = requests.post(url, data=data, timeout=30)
        response.raise_for_status()


class TwilioWhatsAppNotifier:
    def enabled(self) -> bool:
        return all(
            os.getenv(k)
            for k in ["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM", "TWILIO_TO"]
        )

    def send(self, msg: AlertMessage) -> None:
        if not self.enabled():
            return
        account_sid = os.environ["TWILIO_ACCOUNT_SID"]
        auth_token = os.environ["TWILIO_AUTH_TOKEN"]
        url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
        data = {
            "From": os.environ["TWILIO_FROM"],
            "To": os.environ["TWILIO_TO"],
            "Body": f"{msg.subject}\n\n{msg.body}",
        }
        response = requests.post(url, data=data, auth=(account_sid, auth_token), timeout=30)
        response.raise_for_status()


class MultiNotifier:
    def __init__(self) -> None:
        self.notifiers = [EmailNotifier(), TelegramBotNotifier(), TwilioWhatsAppNotifier()]

    def send(self, msg: AlertMessage) -> None:
        errors: list[str] = []
        sent_any = False
        for notifier in self.notifiers:
            if not notifier.enabled():
                continue
            try:
                notifier.send(msg)
                sent_any = True
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{notifier.__class__.__name__}: {exc}")
        if not sent_any and errors:
            raise RuntimeError("; ".join(errors))
        if errors:
            print("Alguns alertas falharam:", "; ".join(errors))
