#!/usr/bin/env python3
"""Send a fixed test email to an SMTP server.

Usage:
    python send_test_mail.py smtp://user:pass@host:port/from@x.com/to@y.com

Supports smtps:// for implicit TLS (port 465) and smtp:// for STARTTLS (port 587).
"""

import asyncio
import sys
from email.message import EmailMessage
from urllib.parse import urlparse

import aiosmtplib


async def send(smtp_uri: str) -> None:
    uri = urlparse(smtp_uri)
    if uri.scheme not in ("smtp", "smtps"):
        raise ValueError(f"Unsupported scheme: {uri.scheme}. Use smtp:// or smtps://")

    use_tls = uri.scheme == "smtps"
    port = uri.port or (465 if use_tls else 587)
    username = uri.username
    password = uri.password
    path = uri.path.strip("/")
    parts = path.split("/", 1)
    sender = parts[0]
    recipient = parts[1] if len(parts) > 1 else sender

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = recipient
    msg["Subject"] = "Relay test email"
    msg.set_content("This is a test email from relay.\n")

    response = await aiosmtplib.send(
        msg,
        hostname=uri.hostname,
        port=port,
        username=username,
        password=password,
        start_tls=not use_tls,
        use_tls=use_tls,
    )

    print(f"Sent to {recipient} via {uri.hostname}:{port} -> {response}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    asyncio.run(send(sys.argv[1]))
