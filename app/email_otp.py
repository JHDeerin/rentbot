"""
Helper to read one-time codes (OTPs) from a Gmail inbox via IMAP.

Used when a site (e.g. RentCafe) requires an email-delivered 2FA code on every
login. The user must generate a Gmail App Password (not their normal password)
and expose it via the GMAIL_APP_PASSWORD environment variable.
"""

from __future__ import annotations

import email
import email.utils
import imaplib
import os
import re
import time
from datetime import datetime, timedelta, timezone
from email.message import Message
from typing import Optional, Tuple

IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993


def _get_credentials() -> Tuple[str, str]:
    address = os.environ.get("GMAIL_ADDRESS")
    password = os.environ.get("GMAIL_APP_PASSWORD")
    if not address or not password:
        raise RuntimeError(
            "GMAIL_ADDRESS and GMAIL_APP_PASSWORD must be set to read OTP emails. "
            "Generate a Gmail App Password at https://myaccount.google.com/apppasswords."
        )
    return address, password


def _extract_text(msg: Message) -> str:
    """Return a single string with the message body (prefers text/plain)."""
    parts = []  # type: list
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype in ("text/plain", "text/html"):
                payload = part.get_payload(decode=True)
                if not payload:
                    continue
                charset = part.get_content_charset() or "utf-8"
                try:
                    parts.append(payload.decode(charset, errors="replace"))
                except LookupError:
                    parts.append(payload.decode("utf-8", errors="replace"))
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            try:
                parts.append(payload.decode(charset, errors="replace"))
            except LookupError:
                parts.append(payload.decode("utf-8", errors="replace"))

    subject = msg.get("Subject", "")
    return subject + "\n" + "\n".join(parts)


def fetch_otp(
    from_contains: str,
    after: datetime,
    otp_regex: str = r"\b(\d{4,8})\b",
    timeout_seconds: int = 120,
    poll_interval_seconds: int = 5,
    mailbox: str = "INBOX",
) -> str:
    """
    Poll Gmail for a matching OTP email and return the code.

    Args:
        from_contains: substring to match against the "From" header (case-insensitive).
        after: only consider emails received at or after this time (tz-aware preferred).
        otp_regex: regex whose first capture group is the code.
        timeout_seconds: give up after this long.
        poll_interval_seconds: delay between inbox polls.

    Raises:
        TimeoutError if no matching email arrives in time.
    """
    address, password = _get_credentials()
    pattern = re.compile(otp_regex)

    # IMAP SINCE is date-only (no time) and inclusive — use the date one day
    # before to be safe, then filter by timestamp ourselves.
    if after.tzinfo is None:
        after = after.replace(tzinfo=timezone.utc)
    since_date = (after - timedelta(days=1)).strftime("%d-%b-%Y")

    deadline = time.time() + timeout_seconds
    last_seen_uids = set()  # type: set
    while time.time() < deadline:
        try:
            with imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT) as mail:
                mail.login(address, password)
                mail.select(mailbox, readonly=True)
                search_q = f'(SINCE {since_date} FROM "{from_contains}")'
                status, data = mail.uid("search", None, search_q)
                if status != "OK":
                    raise RuntimeError(f"IMAP search failed: {status} {data!r}")
                uids = data[0].split() if data and data[0] else []

                # Walk newest → oldest so we find the freshest code first
                for uid in reversed(uids):
                    if uid in last_seen_uids:
                        continue
                    last_seen_uids.add(uid)
                    status, msg_data = mail.uid("fetch", uid, "(RFC822)")
                    if status != "OK" or not msg_data or not msg_data[0]:
                        continue
                    raw = msg_data[0][1]
                    if not isinstance(raw, (bytes, bytearray)):
                        continue
                    msg = email.message_from_bytes(raw)

                    # Filter on actual timestamp
                    received = _parse_date(msg.get("Date"))
                    if received is None or received < after:
                        continue

                    text = _extract_text(msg)
                    match = pattern.search(text)
                    if match:
                        return match.group(1)
        except imaplib.IMAP4.error as e:
            # Transient auth/network blips - retry on next poll
            print(f"IMAP error (will retry): {e}")

        time.sleep(poll_interval_seconds)

    raise TimeoutError(
        f"No OTP email from '{from_contains}' received within {timeout_seconds}s"
    )


def _parse_date(date_header: Optional[str]) -> Optional[datetime]:
    if not date_header:
        return None
    try:
        dt = email.utils.parsedate_to_datetime(date_header)
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt
