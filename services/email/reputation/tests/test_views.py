import pytest

from services.email.reputation.models import FblReport


class TestFblReportListView:
    @pytest.mark.django_db
    def test_get__lists_fbl_reports(self, client):
        from django.contrib.auth import get_user_model

        from accounts.models import Membership, Organization

        User = get_user_model()
        user = User.objects.create(username="testuser", email="test@example.com")
        org = Organization.objects.create(slug="testorg")
        Membership.objects.create(org=org, user=user, role="write")
        FblReport.objects.create(
            org=org,
            mail_from="feedback@gmail.com",
            rcpt_to="fbl@acme.com",
            reporting_org="gmail",
            feedback_type="abuse",
            original_mail_from="sender@acme.com",
        )
        client.force_login(user)
        response = client.get(f"/org/{org.slug}/email/reputation/fbl/")
        assert response.status_code == 200
        assert b"sender@acme.com" in response.content


class TestReputationOverviewView:
    @pytest.mark.django_db
    def test_get__shows_overview(self, client):
        from django.contrib.auth import get_user_model

        from accounts.models import Membership, Organization

        User = get_user_model()
        user = User.objects.create(username="testuser2", email="test2@example.com")
        org = Organization.objects.create(slug="testorg2")
        Membership.objects.create(org=org, user=user, role="write")
        client.force_login(user)
        response = client.get(f"/org/{org.slug}/email/reputation/")
        assert response.status_code == 200
