import pytest
from django.urls import reverse


def empty_state(response):
    return (
        response.content.decode()
        .split('<section class="empty">', 1)[1]
        .split("</section>", 1)[0]
    )


@pytest.mark.django_db
class TestMessageListView:
    def test_get__renders_dialog_with_header_trigger(self, admin_client, org):
        response = admin_client.get(f"/org/{org.slug}/email/messages/")

        assert response.status_code == 200
        content = response.content.decode()
        assert 'id="dlg-test-email"' in content
        assert (
            f'action="{reverse("msa:message-test", kwargs={"org_slug": org.slug})}"'
            in content
        )
        assert 'name="subject"' not in content
        assert (
            "getElementById('dlg-test-email').showModal()"
            in content.split('id="dlg-test-email"', 1)[0]
        )

    def test_get__empty_state_opens_dialog(self, admin_client, org):
        response = admin_client.get(f"/org/{org.slug}/email/messages/")

        assert response.status_code == 200
        assert "getElementById('dlg-test-email').showModal()" in empty_state(response)
