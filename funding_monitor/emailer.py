from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from typing import Any


def build_digest(matches: list[dict[str, Any]], recipient: str) -> EmailMessage:
    sender = os.getenv("EMAIL_FROM") or os.getenv("SMTP_USERNAME") or os.getenv("GMAIL_USER", "")
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = recipient
    msg["Subject"] = f"Funding monitor: {len(matches)} new matched opportunities"
    if not matches:
        msg.set_content("No new matched funding opportunities were found in this run.")
        return msg
    sections: list[str] = []
    for item in matches:
        opp = item["opportunity"]
        guideline = item["guideline"]
        screening = item["screening"]
        sections.append(
            "\n".join(
                [
                    f"## {opp['title']}",
                    f"Agency: {opp.get('agency') or 'Check notice'}",
                    f"Due: {opp.get('due_date') or 'Check notice'}",
                    f"Amount: {opp.get('amount') or 'Check notice'}",
                    f"URL: {opp.get('url')}",
                    f"Fit score: {screening.get('fit_score')}",
                    f"Rationale: {screening.get('rationale')}",
                    "",
                    guideline.get("body", ""),
                ]
            )
        )
    msg.set_content("\n\n" + ("\n\n" + "=" * 72 + "\n\n").join(sections))
    return msg


def send_digest(matches: list[dict[str, Any]], recipient: str) -> None:
    host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    port = int(os.getenv("SMTP_PORT", "465"))
    username = os.getenv("SMTP_USERNAME") or os.getenv("GMAIL_USER", "")
    password = os.getenv("SMTP_PASSWORD") or os.getenv("GMAIL_APP_PASSWORD", "")
    if not username or not password:
        raise RuntimeError("SMTP_USERNAME and SMTP_PASSWORD are required to send email")
    msg = build_digest(matches, recipient)
    with smtplib.SMTP_SSL(host, port, timeout=30) as smtp:
        smtp.login(username, password)
        smtp.send_message(msg)
