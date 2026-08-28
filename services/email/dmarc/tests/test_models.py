import gzip
from email.message import EmailMessage

import pytest

from domains.models import Domain
from services.email.dmarc.models import DmarcRecord, DmarcReport

SAMPLE_XML = b"""<?xml version="1.0"?>
<feedback>
  <report_metadata>
    <org_name>google.com</org_name>
    <email>noreply@google.com</email>
    <report_id>12345</report_id>
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
      <count>3</count>
      <policy_evaluated>
        <disposition>none</disposition>
        <dkim>pass</dkim>
        <spf>fail</spf>
      </policy_evaluated>
    </row>
    <identifiers>
      <header_from>example.com</header_from>
    </identifiers>
    <auth_results>
      <dkim><domain>example.com</domain><result>pass</result></dkim>
      <spf><domain>example.com</domain><result>fail</result></spf>
    </auth_results>
  </record>
</feedback>"""


def make_dmarc_email(xml_bytes):
    msg = EmailMessage()
    msg["Subject"] = "DMARC Report"
    msg["From"] = "reporter@example.com"
    msg["To"] = "dmarc@example.com"
    msg.set_content("Report body")
    compressed = gzip.compress(xml_bytes)
    msg.add_attachment(
        compressed, maintype="application", subtype="gzip", filename="report.xml.gz"
    )
    return msg.as_bytes()


class TestDmarcReportParseFromEmail:
    def test_parse_from_email__returns_report_and_records(self):
        raw = make_dmarc_email(SAMPLE_XML)
        report, records = DmarcReport.parse_from_email(raw)
        assert report.reporting_org == "google.com"
        assert report.report_id == "12345"
        assert len(records) == 1
        assert records[0].source_ip_address == "192.168.1.1"
        assert records[0].count == 3

    def test_parse_from_email__raises_on_no_attachment(self):
        msg = EmailMessage()
        msg["Subject"] = "No attachment"
        msg.set_content("body")
        try:
            DmarcReport.parse_from_email(msg.as_bytes())
            assert False, "Should have raised ValueError"
        except ValueError:
            pass


@pytest.mark.django_db
class TestDmarcReportStr:
    def test_str__shows_reporting_org_and_domain(self, org):

        domain = Domain.objects.create(name="example.com", org=org)
        report = DmarcReport(
            org=org,
            domain=domain,
            reporting_org="google.com",
            report_id="12345",
        )
        assert "google.com" in str(report)
        assert "12345" in str(report)


class TestDmarcRecordStr:
    def test_str__shows_ip_count_disposition(self):

        record = DmarcRecord(
            source_ip_address="192.168.1.1",
            count=5,
            disposition="none",
        )
        result = str(record)
        assert "192.168.1.1" in result
        assert "5" in result
        assert "none" in result
