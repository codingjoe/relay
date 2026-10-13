import pytest
from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount, SocialLogin
from django.contrib.auth.models import User
from django.contrib.sessions.backends.db import SessionStore
from django.test import RequestFactory

from accounts.adapters import RelaySocialAccountAdapter
from accounts.models import Membership, Organization


@pytest.mark.django_db
class TestSaveUser:
    def test_save_user__new_user(self):
        request = RequestFactory().post("/social/github/login/callback/")
        request.session = SessionStore()
        sociallogin = SocialLogin(
            user=User(username="newbie", email="n@example.com"),
            account=SocialAccount(provider="github", uid="4242"),
            email_addresses=[
                EmailAddress(email="n@example.com", verified=True, primary=True)
            ],
        )
        RelaySocialAccountAdapter().save_user(request, sociallogin)
        org = Organization.objects.get(slug="newbie")
        assert Membership.objects.filter(
            org=org, user=sociallogin.user, role=Membership.Role.ADMIN
        ).exists()
