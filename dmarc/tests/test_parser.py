import gzip
from email.message import EmailMessage

from dmarc.parser import parse_arf, parse_dmarc_xml


def make_report_email(xml_bytes, filename="report.xml.gz"):
    msg = EmailMessage()
    msg["Subject"] = "DMARC Report"
    msg["From"] = "reporter@example.com"
    msg["To"] = "dmarc@example.com"
    msg.set_content("DMARC aggregate report")
    compressed = gzip.compress(xml_bytes)
    msg.add_attachment(
        compressed, maintype="application", subtype="gzip", filename=filename
    )
    return msg.as_bytes()


SAMPLE_XML = b"""<?xml version="1.0"?>
<feedback>
  <report_metadata>
    <org_name>google.com</org_name>
    <email>noreply-dmarc-support@google.com</email>
    <report_id>1234567890</report_id>
    <date_range>
      <begin>1704067200</begin>
      <end>1704153600</end>
    </date_range>
  </report_metadata>
  <policy_published>
    <domain>example.com</domain>
    <adkim>r</adkim>
    <aspf>r</aspf>
    <p>none</p>
    <sp>none</sp>
    <pct>100</pct>
  </policy_published>
  <record>
    <row>
      <source_ip>192.168.1.1</source_ip>
      <count>5</count>
      <policy_evaluated>
        <disposition>none</disposition>
        <dkim>pass</dkim>
        <spf>pass</spf>
      </policy_evaluated>
    </row>
    <identifiers>
      <header_from>example.com</header_from>
      <envelope_from>example.com</envelope_from>
    </identifiers>
    <auth_results>
      <dkim>
        <domain>example.com</domain>
        <result>pass</result>
      </dkim>
      <spf>
        <domain>example.com</domain>
        <result>pass</result>
      </spf>
    </auth_results>
  </record>
</feedback>"""


class TestParseDmarcXml:
    def test_parse_dmarc_xml__extracts_metadata(self):
        result = parse_dmarc_xml(SAMPLE_XML)
        meta = result["metadata"]
        assert meta["reporting_org"] == "google.com"
        assert meta["report_id"] == "1234567890"
        assert meta["begin_at"] is not None
        assert meta["end_at"] is not None

    def test_parse_dmarc_xml__extracts_records(self):
        result = parse_dmarc_xml(SAMPLE_XML)
        records = result["records"]
        assert len(records) == 1
        assert records[0]["source_ip_address"] == "192.168.1.1"
        assert records[0]["count"] == 5
        assert records[0]["disposition"] == "none"
        assert records[0]["dkim_alignment"] == "pass"
        assert records[0]["spf_alignment"] == "pass"
        assert records[0]["header_from"] == "example.com"


class TestParseArf:
    def test_parse_arf__raises_on_no_feedback_report(self):
        msg = EmailMessage()
        msg["Subject"] = "Not a report"
        msg.set_content("Just a regular email")
        try:
            parse_arf(msg.as_bytes())
            assert False, "Should have raised ValueError"
        except ValueError:
            pass

    def test_parse_arf__extracts_feedback_fields(self):
        msg = EmailMessage()
        msg["Subject"] = "RUF Report"
        msg["From"] = "reporter@example.com"
        msg.set_content("This is a report")
        msg.add_attachment(
            b"Feedback-Type: auth-failure\n"
            b"Source-IP: 10.0.0.1\n"
            b"Original-Mail-From: sender@evil.com\n"
            b"Original-Rcpt-To: victim@example.com\n"
            b"Delivery-Result: policy\n",
            maintype="message",
            subtype="feedback-report",
        )
        msg.add_attachment(
            b"From: sender@evil.com\r\nTo: victim@example.com\r\n",
            maintype="text",
            subtype="rfc822-headers",
        )
        result = parse_arf(msg.as_bytes())
        assert result["source_ip_address"] == "10.0.0.1"
        assert result["original_mail_from"] == "sender@evil.com"
        assert result["delivery_result"] == "policy"
        assert "From: sender@evil.com" in result["original_headers"]
