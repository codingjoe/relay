import gzip
from email.message import EmailMessage

import pytest
from django.core.files.base import ContentFile

from services.email.dmarc.models import DmarcReport

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
    <adkim>r</adkim><aspf>r</aspf><p>none</p><sp>none</sp><pct>100</pct>
  </policy_published>
  <record>
    <row>
      <source_ip>192.168.1.1</source_ip>
      <count>3</count>
      <policy_evaluated>
        <disposition>none</disposition><dkim>pass</dkim><spf>pass</spf>
      </policy_evaluated>
    </row>
    <identifiers><header_from>example.com</header_from></identifiers>
    <auth_results>
      <dkim><domain>example.com</domain><result>pass</result></dkim>
      <spf><domain>example.com</domain><result>pass</result></spf>
    </auth_results>
  </record>
</feedback>"""


def make_report_email(xml_bytes):
    msg = EmailMessage()
    msg["Subject"] = "DMARC Report"
    msg["From"] = "reporter@example.com"
    msg["To"] = "dmarc@example.com"
    msg.set_content("body")
    compressed = gzip.compress(xml_bytes)
    msg.add_attachment(
        compressed, maintype="application", subtype="gzip", filename="report.xml.gz"
    )
    return msg.as_bytes()


@pytest.fixture
def dmarc_report(org):
    from domains.models import Domain

    domain = Domain.objects.create(name="example.com", org=org)
    raw = make_report_email(SAMPLE_XML)
    report = DmarcReport(
        org=org,
        domain=domain,
        receiving_domain="example.com",
        mail_from="reporter@google.com",
        rcpt_to="dmarc@example.com",
        subject="DMARC Report",
        report_id="12345",
        reporting_org="google.com",
        reporting_email="noreply@google.com",
    )
    report.raw_body.save(f"{report.id}.eml", ContentFile(raw), save=False)
    report.save(force_insert=True)
    # Parse and store records
    parsed_report, records = DmarcReport.parse_from_email(raw)
    report.reporting_org = parsed_report.reporting_org
    report.report_id = parsed_report.report_id
    report.begin_at = parsed_report.begin_at
    report.end_at = parsed_report.end_at
    report.save(update_fields=["reporting_org", "report_id", "begin_at", "end_at"])
    from services.email.dmarc.models import DmarcRecord

    for record in records:
        record.report = report
    DmarcRecord.objects.bulk_create(records)
    return report


@pytest.mark.django_db
class TestDmarcReportDetailView:
    def test_get__shows_report_detail(self, client, org, dmarc_report):
        client.force_login(org.members.first())  # noqa: any member
        response = client.get(f"/org/{org.slug}/email/dmarc/{dmarc_report.pk}")
        assert response.status_code == 200
        assert "192.168.1.1" in response.content.decode()

    def test_get__filters_records_by_source_ip(self, client, org, dmarc_report):
        client.force_login(org.members.first())  # noqa: any member
        response = client.get(
            f"/org/{org.slug}/email/dmarc/{dmarc_report.pk}",
            {"source_ip": "192.168.1.1"},
        )
        assert response.status_code == 200
        assert "192.168.1.1" in response.content.decode()

    def test_get__source_ip_filter_excludes_non_matching(
        self, client, org, dmarc_report
    ):
        client.force_login(org.members.first())  # noqa: any member
        response = client.get(
            f"/org/{org.slug}/email/dmarc/{dmarc_report.pk}",
            {"source_ip": "10.0.0.1"},
        )
        assert response.status_code == 200
        assert "192.168.1.1" not in response.content.decode()
