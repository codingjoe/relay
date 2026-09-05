import asyncio
import datetime
import math
import time
from argparse import ArgumentTypeError
from collections import Counter
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import make_msgid
from urllib.parse import urlparse

import aiosmtplib
import environ
from django.core.exceptions import ImproperlyConfigured
from django.core.management.base import BaseCommand, CommandError

IMPLICIT_TLS_PORT = 465
STARTTLS_PORT = 587
PERCENTILE_STEPS = (50, 66, 75, 80, 90, 95, 98, 99, 100)


@dataclass
class SmtpUri:
    """Submission endpoint and addresses parsed from an SMTP URI."""

    hostname: str
    port: int
    username: str | None
    password: str | None
    sender: str
    recipient: str
    use_tls: bool


@dataclass
class SendResult:
    """Outcome of one benchmark email."""

    duration: datetime.timedelta
    status_code: int | None
    error: str


class UnsupportedSchemeError(ValueError):
    """The SMTP URI scheme is neither smtp nor smtps."""

    def __init__(self, scheme):
        super().__init__(f"Unsupported scheme: {scheme}. Use smtp:// or smtps://")


class MalformedSmtpUriError(ValueError):
    """The SMTP URI could not be parsed."""

    def __init__(self, reason):
        super().__init__(f"Invalid SMTP URI: {reason}")


class MissingHostnameError(ValueError):
    """The SMTP URI has no hostname."""

    def __init__(self):
        super().__init__("The URI must include a hostname.")


class MissingSenderError(ValueError):
    """The SMTP URI has no sender in its path."""

    def __init__(self):
        super().__init__(
            "The URI must include a sender in its path, for example "
            "smtps://user:pass@msa.example.com/alice@example.com/bob@example.com"
        )


class PositiveIntRequiredError(ArgumentTypeError):
    """A command option received a value smaller than one."""

    def __init__(self, value):
        super().__init__(f"The value must be at least 1, not {value}.")


def positive_int(value):
    """Parse a strictly positive integer, as an argparse option type."""
    number = int(value)
    if number < 1:
        raise PositiveIntRequiredError(value)
    return number


def parse_smtp_uri(smtp_uri: str) -> SmtpUri:
    """
    Parse an SMTP URI into its endpoint, sender, and recipient.

    The URI path carries the sender and recipient, separated by a slash, for
    example `smtps://user:pass@msa.example.com/alice@example.com/bob@example.com`.
    `smtps://` uses implicit TLS, `smtp://` uses STARTTLS. The recipient
    defaults to the sender when the URI omits it.
    """
    match urlparse(smtp_uri).scheme:
        case "smtps":
            use_tls, default_port = True, IMPLICIT_TLS_PORT
        case "smtp":
            use_tls, default_port = False, STARTTLS_PORT
        case unsupported_scheme:
            raise UnsupportedSchemeError(unsupported_scheme)
    try:
        config = environ.Env.email_url_config(smtp_uri)
    except (ImproperlyConfigured, ValueError) as error:
        raise MalformedSmtpUriError(error) from error

    path = config["EMAIL_FILE_PATH"].strip("/")
    sender, _, recipient = path.partition("/")
    recipient = recipient or sender
    if not config["EMAIL_HOST"]:
        raise MissingHostnameError()
    if not sender:
        raise MissingSenderError()
    return SmtpUri(
        hostname=config["EMAIL_HOST"],
        port=config["EMAIL_PORT"] or default_port,
        username=config["EMAIL_HOST_USER"],
        password=config["EMAIL_HOST_PASSWORD"],
        sender=sender,
        recipient=recipient,
        use_tls=use_tls,
    )


async def send_email(uri: SmtpUri) -> SendResult:
    """Send one benchmark email and return its send result."""
    message = EmailMessage()
    message["From"] = uri.sender
    message["To"] = uri.recipient
    message["Message-ID"] = make_msgid()
    message["Subject"] = "Relay benchmark email"
    message.set_content("This is a benchmark email from relay.\n")

    started_at = time.monotonic()
    status_code, error = 250, ""
    try:
        await aiosmtplib.send(
            message,
            hostname=uri.hostname,
            port=uri.port,
            username=uri.username,
            password=uri.password,
            start_tls=not uri.use_tls,
            use_tls=uri.use_tls,
        )
    except aiosmtplib.SMTPResponseException as smtp_error:
        status_code, error = smtp_error.code, type(smtp_error).__name__
    except (aiosmtplib.SMTPException, OSError) as send_error:
        status_code, error = None, type(send_error).__name__
    return SendResult(
        datetime.timedelta(seconds=time.monotonic() - started_at),
        status_code,
        error,
    )


async def benchmark_emails(
    uri: SmtpUri, count: int, concurrency: int, send_results: list, report_progress
):
    """
    Send count emails with the given concurrency, appending each send result.

    `report_progress` runs after every email with the number of completed
    emails, which lets the caller print progress lines.
    """
    unsent_emails = asyncio.Queue()
    for _ in range(count):
        unsent_emails.put_nowait(None)

    async def send_worker():
        while True:
            try:
                unsent_emails.get_nowait()
            except asyncio.QueueEmpty:
                break
            send_results.append(await send_email(uri))
            report_progress(len(send_results))

    await asyncio.gather(*(send_worker() for _ in range(concurrency)))


def percentile(ascending_values: list, percent: int) -> float:
    """Return the value at the given percentile of an ascending sequence."""
    index = math.ceil(percent / 100 * len(ascending_values)) - 1
    return ascending_values[max(index, 0)]


class Command(BaseCommand):
    help = "Benchmark an SMTP submission endpoint by sending emails, like ab or hey"

    def add_arguments(self, parser):
        parser.add_argument(
            "smtp_uri",
            help=(
                "SMTP URI, for example "
                "smtps://user:pass@msa.example.com:465/"
                "alice@example.com/bob@example.com"
            ),
        )
        parser.add_argument(
            "-n",
            "--count",
            type=positive_int,
            default=100,
            help="Number of emails to send (default: 100)",
        )
        parser.add_argument(
            "-c",
            "--concurrency",
            type=positive_int,
            default=10,
            help="Number of concurrent senders (default: 10)",
        )

    def handle(self, *args, smtp_uri, count, concurrency, **options):
        try:
            uri = parse_smtp_uri(smtp_uri)
        except ValueError as error:
            raise CommandError(str(error)) from error
        progress_interval = max(count // 10, 1)

        def report_progress(completed):
            if completed % progress_interval == 0 or completed == count:
                self.stdout.write(f"Completed {completed} of {count} emails")

        self.stdout.write(
            f"Benchmarking {uri.hostname}:{uri.port} with {count} emails "
            f"at concurrency {concurrency}"
        )
        self.stdout.write("")
        send_results = []
        started_at = time.monotonic()
        try:
            asyncio.run(
                benchmark_emails(uri, count, concurrency, send_results, report_progress)
            )
        except KeyboardInterrupt:
            self.stdout.write("Benchmark interrupted. Printing partial results.")
        total_duration = datetime.timedelta(seconds=time.monotonic() - started_at)
        self.stdout.write("")
        self.print_summary(uri, send_results, concurrency, total_duration)

    def print_summary(
        self, uri: SmtpUri, send_results: list, concurrency: int, total_duration
    ):
        """Print ab-style statistics for the benchmark send results."""
        if not send_results:
            self.stdout.write(self.style.ERROR("No emails were sent."))
        else:
            complete_count = len(send_results)
            failed_count = sum(bool(result.error) for result in send_results)
            total_secs = total_duration.total_seconds()
            durations_ms = sorted(
                result.duration.total_seconds() * 1000 for result in send_results
            )
            tls_mode = "implicit TLS" if uri.use_tls else "STARTTLS"
            summary_rows = [
                ("Sender:", uri.sender),
                ("Recipient:", uri.recipient),
                ("Endpoint:", f"{uri.hostname}:{uri.port} ({tls_mode})"),
                ("Concurrency Level:", str(concurrency)),
                ("Time taken for tests:", f"{total_secs:.3f} secs"),
                ("Complete emails:", str(complete_count)),
                ("Failed emails:", str(failed_count)),
                (
                    "Emails per second:",
                    f"{complete_count / total_secs:.2f} [#/sec] (mean)",
                ),
                (
                    "Time per email:",
                    f"{sum(durations_ms) / complete_count:.2f} [ms] (mean)",
                ),
                (
                    "Time per email:",
                    (
                        f"{total_secs * 1000 / complete_count:.2f} [ms] "
                        "(mean, across all concurrent senders)"
                    ),
                ),
                ("Fastest email:", f"{durations_ms[0]:.2f} [ms]"),
                ("Slowest email:", f"{durations_ms[-1]:.2f} [ms]"),
            ]
            label_width = max(len(label) for label, _ in summary_rows) + 2
            for label, value in summary_rows:
                self.stdout.write(f"{label:<{label_width}}{value}")

            self.stdout.write("")
            self.stdout.write(
                "Percentage of the emails served within a certain time (ms):"
            )
            for percent in PERCENTILE_STEPS:
                slowest_suffix = " (slowest)" if percent == 100 else ""
                self.stdout.write(
                    f"  {percent:>3}%  "
                    f"{percentile(durations_ms, percent):8.1f}{slowest_suffix}"
                )

            status_codes = Counter(
                result.status_code
                for result in send_results
                if result.status_code is not None
            )
            if status_codes:
                self.stdout.write("")
                self.stdout.write("SMTP status codes:")
                for status_code, status_count in sorted(status_codes.items()):
                    self.stdout.write(f"  {status_code}    {status_count} emails")

            errors = Counter(result.error for result in send_results if result.error)
            if errors:
                self.stdout.write("")
                self.stdout.write("Errors:")
                for error_name, error_count in errors.most_common():
                    self.stdout.write(f"  {error_name}    {error_count} emails")

            self.stdout.write("")
            if failed_count:
                self.stdout.write(
                    self.style.ERROR(
                        f"{failed_count} of {complete_count} emails failed."
                    )
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS(f"All {complete_count} emails were sent.")
                )
