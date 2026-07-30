import gzip
import io
import zipfile
from email.message import EmailMessage

from abstract.email_utils import iter_attachments


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
