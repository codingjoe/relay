from unittest.mock import patch

import pytest
from django.conf import settings

from domains.models import Domain
from services.email.dmarc.models import DmarcFailureReport, DmarcReport
from services.email.mta.handlers import process_incoming_message
from services.email.mta.models import IncomingMessage
from services.email.mta.tests.conftest import make_raw_email


class TestProcessIncomingMessageReports:
    @pytest.mark.django_db(transaction=True)
    @pytest.mark.parametrize(
        ("local_part", "report_model"),
        [
            (settings.RELAY_DMARC_REPORT_LOCAL_PART, DmarcReport),
            (settings.RELAY_DMARC_RUF_LOCAL_PART, DmarcFailureReport),
        ],
    )
    async def test_report_recipient__binds_report_to_domain(
        self,
        org,
        local_part,
        report_model,
    ):
        domain = Domain.objects.create(name="example.com", org=org)

        with (
            patch("services.email.dmarc.signals.parse_dmarc_report"),
            patch("services.email.dmarc.signals.parse_dmarc_failure_report"),
        ):
            result = await process_incoming_message(
                "external@example.org",
                f"{local_part}@example.com",
                make_raw_email(),
                {"ssl_object": None},
                domain,
                IncomingMessage.Status.RECEIVED,
                "",
            )

        report = await report_model.objects.aget(domain=domain)
        assert result == "250 OK"
        assert report.org == org
        assert report.raw_body.size > 0
        assert report.headers
