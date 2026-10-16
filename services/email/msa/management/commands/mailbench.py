import asyncio
import contextlib
import math
import time
from argparse import ArgumentTypeError
from collections import Counter
from email.message import EmailMessage
from email.utils import make_msgid
from urllib.parse import urlparse

import aiosmtplib
import environ
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

PERCENTILE_STEPS = (50, 75, 95)


def positive_int(value: str) -> int:
    """Parse a whole number of at least 1 for an argparse option type."""
    number = int(value)
    if number < 1:
        raise ArgumentTypeError(  # noqa: TRY003
            f"The value must be at least 1, not {value}."
        )
    return number


def parse_smtp_url(smtp_url: str) -> dict:
    """Return the email configuration of an SMTP submission URL."""
    match urlparse(smtp_url).scheme:
        case "smtps":
            use_tls, default_port = True, 465
        case "smtp":
            use_tls, default_port = False, 587
        case unsupported_scheme:
            raise ValueError(  # noqa: TRY003
                f"Unsupported scheme: {unsupported_scheme}. Use smtp:// or smtps://"
            )
    config = environ.Env.email_url_config(smtp_url)
    if not config["EMAIL_HOST"]:
        raise ValueError("The URL must include a hostname.")  # noqa: TRY003
    return config | {
        "EMAIL_PORT": config["EMAIL_PORT"] or default_port,
        "EMAIL_USE_TLS": use_tls,
    }


def build_email(sender: str, recipients: list[str]) -> EmailMessage:
    """Assemble one message with a unique Message-ID and a fixed subject and body."""
    message = EmailMessage()
    message["From"] = sender
    message["To"] = ", ".join(recipients)
    message["Message-ID"] = make_msgid(domain="relay.example.com")
    message["Subject"] = "Relay benchmark email"
    message.set_content("This is a benchmark email from relay.\n")
    return message


async def open_connection(config: dict) -> aiosmtplib.SMTP:
    """Dial the endpoint, negotiate TLS, and log in if credentials are given."""
    smtp = aiosmtplib.SMTP(
        hostname=config["EMAIL_HOST"],
        port=config["EMAIL_PORT"],
        username=config["EMAIL_HOST_USER"],
        password=config["EMAIL_HOST_PASSWORD"],
        local_hostname=settings.RELAY_SMTP_PUBLIC_HOSTNAME,
        start_tls=not config["EMAIL_USE_TLS"],
        use_tls=config["EMAIL_USE_TLS"],
    )
    await smtp.connect()
    return smtp


async def benchmark_emails(
    config: dict,
    sender: str,
    recipients: list[str],
    count: int,
    concurrency: int,
    emails_per_connection: int,
    send_results: list,
) -> None:
    """
    Send the requested messages across the given number of parallel connections.

    Append each send result to `send_results` as it completes.
    """

    async def send_slice(indices: range) -> None:
        smtp = None
        emails_on_connection = 0
        for _ in indices:
            started_at = time.monotonic()
            error = ""
            opened_connection = False
            try:
                if smtp is not None and emails_on_connection >= emails_per_connection:
                    with contextlib.suppress(aiosmtplib.SMTPException, OSError):
                        await smtp.quit()
                    smtp = None
                if smtp is None:
                    smtp = await open_connection(config)
                    emails_on_connection = 0
                    opened_connection = True
                await smtp.send_message(build_email(sender, recipients))
            except (
                aiosmtplib.SMTPResponseException,
                aiosmtplib.SMTPRecipientsRefused,
            ) as smtp_error:
                error = f"{type(smtp_error).__name__}: {smtp_error}"
            except (aiosmtplib.SMTPException, OSError) as send_error:
                error = f"{type(send_error).__name__}: {send_error}"
                smtp = None
                emails_on_connection = 0
            emails_on_connection += 1
            send_results.append(
                ((time.monotonic() - started_at) * 1000, error, opened_connection)
            )
        if smtp is not None:
            with contextlib.suppress(aiosmtplib.SMTPException, OSError):
                await smtp.quit()

    await asyncio.gather(
        *(
            send_slice(range(worker, count, concurrency))
            for worker in range(concurrency)
        )
    )


class Command(BaseCommand):
    help = (
        "Benchmark an SMTP submission endpoint, like ab or hey. "
        "The endpoint comes from the SMTP_URL environment variable."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "recipients",
            nargs="+",
            help="Recipients of the benchmark email.",
        )
        parser.add_argument(
            "--from",
            dest="sender",
            required=True,
            help="Sender address of the benchmark email.",
        )
        parser.add_argument(
            "-n",
            "--count",
            type=positive_int,
            default=100,
            help="Total number of emails to send (default: 100).",
        )
        parser.add_argument(
            "-c",
            "--concurrency",
            type=positive_int,
            default=10,
            help=(
                "Number of connections used at the same time (default: 10, at most -n)."
            ),
        )
        parser.add_argument(
            "-e",
            "--emails-per-connection",
            type=positive_int,
            default=1,
            help=(
                "Number of emails attempted over one connection before it is "
                "closed and a new one is opened (default: 1)."
            ),
        )

    def handle(
        self,
        *args,
        sender,
        recipients,
        count,
        concurrency,
        emails_per_connection,
        **options,
    ):
        smtp_url = environ.Env().str("SMTP_URL", default="")
        if not smtp_url:
            raise CommandError(  # noqa: TRY003
                "Set the SMTP_URL environment variable to the submission endpoint, "
                "for example smtps://user:password@msa.example.com:465. Use smtps:// "
                "for implicit TLS (default port 465) or smtp:// for STARTTLS "
                "(default port 587). Percent-encode special characters in the "
                "credentials."
            )
        concurrency = min(concurrency, count)
        try:
            config = parse_smtp_url(smtp_url)
        except ValueError as error:
            raise CommandError(str(error)) from error
        self.stdout.write(
            f"Benchmarking {config['EMAIL_HOST']}:{config['EMAIL_PORT']} with "
            f"{count} emails at {concurrency} concurrent connections"
        )
        self.stdout.write("")
        send_results = []
        started_at = time.monotonic()
        try:
            asyncio.run(
                benchmark_emails(
                    config,
                    sender,
                    recipients,
                    count,
                    concurrency,
                    emails_per_connection,
                    send_results,
                )
            )
        except KeyboardInterrupt as interrupt:
            if not send_results:
                raise CommandError("No emails were sent.") from interrupt  # noqa: TRY003
            self.stdout.write("Benchmark interrupted. Printing partial results.")
        total_secs = time.monotonic() - started_at
        self.stdout.write("")
        complete_count = len(send_results)
        failed_count = sum(bool(error) for _, error, _ in send_results)
        durations_ms = sorted(duration_ms for duration_ms, _, _ in send_results)
        connections_opened = sum(opened for _, _, opened in send_results)
        tls_mode = "implicit TLS" if config["EMAIL_USE_TLS"] else "STARTTLS"
        summary_rows = [
            ("Sender:", sender),
            ("Recipients:", ", ".join(recipients)),
            (
                "Endpoint:",
                f"{config['EMAIL_HOST']}:{config['EMAIL_PORT']} ({tls_mode})",
            ),
            ("Concurrent connections:", str(concurrency)),
            ("Emails per connection:", str(emails_per_connection)),
            ("Time taken for tests:", f"{total_secs:.3f} secs"),
            ("Emails attempted:", str(complete_count)),
            ("Emails sent:", str(complete_count - failed_count)),
            ("Emails failed:", str(failed_count)),
            ("Connections opened:", str(connections_opened)),
            (
                "Emails per second:",
                f"{complete_count / total_secs:.2f} [#/sec] (mean)",
            ),
            (
                "Time per email:",
                f"{sum(durations_ms) / complete_count:.2f} [ms] (mean)",
            ),
            ("Fastest email:", f"{durations_ms[0]:.2f} [ms]"),
            ("Slowest email:", f"{durations_ms[-1]:.2f} [ms]"),
        ]
        label_width = max(len(label) for label, _ in summary_rows) + 2
        for label, value in summary_rows:
            self.stdout.write(f"{label:<{label_width}}{value}")

        self.stdout.write("")
        self.stdout.write("Percentage of the emails served within a certain time (ms):")
        for percent in PERCENTILE_STEPS:
            index = math.ceil(percent / 100 * complete_count) - 1
            self.stdout.write(f"  {percent:>3}%  {durations_ms[index]:8.1f}")

        errors = Counter(error for _, error, _ in send_results if error)
        if errors:
            self.stdout.write("")
            self.stdout.write("Errors:")
            for error_name, error_count in errors.most_common():
                self.stdout.write(f"  {error_name}    {error_count} emails")

        self.stdout.write("")
        if failed_count:
            self.stdout.write(
                self.style.ERROR(f"{failed_count} of {complete_count} emails failed.")
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f"All {complete_count} emails were sent.")
            )
