"""Authenticate relay's GitHub users through django-allauth."""

from typing import Any

from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.socialaccount.models import SocialLogin
from django.contrib.auth.base_user import AbstractBaseUser
from django.db import transaction
from django.http import HttpRequest

from .models import Membership, Organization


class RelaySocialAccountAdapter(DefaultSocialAccountAdapter):
    """Give every new GitHub user a personal organization."""

    @transaction.atomic
    def save_user(
        self, request: HttpRequest, sociallogin: SocialLogin, form: Any | None = None
    ) -> AbstractBaseUser:
        """Create the account with its personal organization and admin membership."""
        user = super().save_user(request, sociallogin, form)
        Membership.objects.create(
            org=Organization.objects.create(slug=user.username),
            user=user,
            role=Membership.Role.ADMIN,
        )
        return user
