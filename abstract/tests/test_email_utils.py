import base64
import gzip
import io
import zipfile
from email import message_from_string
from email.message import EmailMessage, Message
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart

from abstract.email_utils import extract_part_text, iter_attachments


def make_email_with_attachment(filename, data, content_type="application/gzip"):
    msg = EmailMessage()
    msg["Subject"] = "Test"
    msg["From"] = "test@example.com"
    msg["To"] = "dmarc@example.com"
    msg.set_content("Report body")
    msg.add_attachment(
        data,
        maintype=content_type.split("/")[0],
        subtype=content_type.split("/")[1],
        filename=filename,
    )
    return msg.as_bytes()


class TestIterAttachments:
    def test_iter_attachments__yields_plain_attachment(self):
        raw = make_email_with_attachment("report.xml", b"<feedback/>", "text/xml")
        results = list(iter_attachments(raw))
        assert len(results) == 1
        assert results[0] == b"<feedback/>"

    def test_iter_attachments__yields_gzip_attachment(self):
        compressed = gzip.compress(b"<feedback/>")
        raw = make_email_with_attachment("report.xml.gz", compressed)
        results = list(iter_attachments(raw))
        assert len(results) == 1
        assert results[0] == b"<feedback/>"

    def test_iter_attachments__yields_zip_attachment(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("report.xml", b"<feedback/>")
        raw = make_email_with_attachment(
            "report.zip", buf.getvalue(), "application/zip"
        )
        results = list(iter_attachments(raw))
        assert len(results) == 1
        assert results[0] == b"<feedback/>"

    def test_iter_attachments__returns_empty_for_no_attachment(self):
        msg = EmailMessage()
        msg["Subject"] = "Test"
        msg.set_content("No attachment")
        results = list(iter_attachments(msg.as_bytes()))
        assert results == []

    def test_iter_attachments__yields_multiple_attachments(self):
        msg = EmailMessage()
        msg["Subject"] = "Test"
        msg.set_content("body")
        msg.add_attachment(b"data1", maintype="text", subtype="plain", filename="a.txt")
        msg.add_attachment(b"data2", maintype="text", subtype="plain", filename="b.txt")
        results = list(iter_attachments(msg.as_bytes()))
        assert len(results) == 2

    def test_iter_attachments__skips_multipart_attachment_parts(self):
        """An attachment-disposed multipart container yields no payload."""

        outer = MIMEMultipart()
        nested = MIMEMultipart()
        nested.add_header("Content-Disposition", "attachment", filename="nested.eml")
        outer.attach(nested)
        attachment = MIMEApplication(b"payload", _subtype="json")
        attachment.add_header("Content-Disposition", "attachment", filename="a.json")
        outer.attach(attachment)
        assert list(iter_attachments(outer.as_bytes())) == [b"payload"]


def make_multipart_with_sub_part(sub_part):
    """Wrap a raw sub-part (headers + body) in a multipart/mixed envelope."""
    return (
        "Content-Type: multipart/mixed; boundary=OUTER\r\n\r\n"
        "--OUTER\r\n"
        f"{sub_part}\r\n"
        "--OUTER--\r\n"
    )


class TestExtractPartText:
    def test_extract_part_text__decodes_plain_sub_part(self):

        raw = make_multipart_with_sub_part(
            "Content-Type: text/plain\r\n\r\nhello world"
        )
        assert extract_part_text(message_from_string(raw)) == "hello world"

    def test_extract_part_text__decodes_base64_sub_part(self):

        encoded = base64.b64encode(b"encoded body").decode()
        raw = make_multipart_with_sub_part(
            "Content-Type: text/plain\r\n"
            "Content-Transfer-Encoding: base64\r\n\r\n"
            f"{encoded}"
        )
        assert extract_part_text(message_from_string(raw)) == "encoded body"

    def test_extract_part_text__skips_nested_multipart_sub_part(self):

        raw = make_multipart_with_sub_part(
            "Content-Type: multipart/alternative; boundary=INNER\r\n\r\n"
            "--INNER\r\n"
            "Content-Type: text/plain\r\n\r\n"
            "inner text\r\n"
            "--INNER--"
        )
        assert extract_part_text(message_from_string(raw)) == ""

    def test_extract_part_text__decodes_non_multipart_base64(self):

        encoded = base64.b64encode(b"direct body").decode()
        raw = (
            "Content-Type: text/plain\r\n"
            "Content-Transfer-Encoding: base64\r\n\r\n"
            f"{encoded}"
        )
        assert extract_part_text(message_from_string(raw)) == "direct body"

    def test_extract_part_text__returns_empty_string_without_payload(self):

        assert extract_part_text(Message()) == ""

    def test_extract_part_text__decodes_base64_body_without_cte(self):
        """A sub-part may carry base64 text even when its CTE does not honor it."""

        encoded = base64.b64encode(b"undetected base64").decode()
        raw = make_multipart_with_sub_part(f"Content-Type: text/plain\r\n\r\n{encoded}")
        assert extract_part_text(message_from_string(raw)) == "undetected base64"

    def test_extract_part_text__keeps_payload_when_base64_round_trip_fails(self):
        """A 7-bit body that decodes but does not round-trip is used as-is."""

        raw = make_multipart_with_sub_part("Content-Type: text/plain\r\n\r\naGVs bG8=")
        assert extract_part_text(message_from_string(raw)) == "aGVs bG8="
