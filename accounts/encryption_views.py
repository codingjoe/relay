from datetime import timedelta

from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views import generic
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from kms.models import OrgEncryptionKey, RecoveryEvent
from kms.tasks import notify_recovery_triggered

from .models import Membership, MembershipEncryptionKey, UserEncryptionKey
from .views import (
    OrganizationScopedView,
    create_encryption_keys,
    validate_encryption_keys,
)


class AdminOnlyView(OrganizationScopedView, APIView):
    """Restrict access to org admins."""

    def dispatch(self, request, *args, **kwargs):
        try:
            self.org.memberships.get(user=request.user, role=Membership.Role.ADMIN)
        except Membership.DoesNotExist:
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class EncryptionStatusView(OrganizationScopedView, APIView):
    """Return whether the org has encryption configured and the user's key status."""

    def get(self, request, *args, **kwargs):
        try:
            org_key = self.org.encryption_keys.get(is_active=True)
        except OrgEncryptionKey.DoesNotExist:
            org_public_key = None
            org_key_id = None
            recovery_sealed_org_private_key = None
        else:
            org_public_key = org_key.public_key
            org_key_id = org_key.key_id
            recovery_sealed_org_private_key = (
                org_key.recovery_sealed_org_private_key or None
            )
        try:
            user_key = request.user.encryption_keys.latest("created_at")
        except UserEncryptionKey.DoesNotExist:
            user_key_id = None
        else:
            user_key_id = user_key.key_id
        membership = self.org.memberships.get(user=request.user)
        sealed_org_private_key = None
        if hasattr(membership, "encryption_key"):
            sealed_org_private_key = membership.encryption_key.sealed_org_private_key
        recent_recovery = (
            RecoveryEvent.objects.filter(
                org_encryption_key__org=self.org,
                created_at__gte=timezone.now() - timedelta(hours=24),
            )
            .select_related("triggered_by")
            .first()  # noqa: relint - latest of 0+ events
        )
        recovery_triggered_at = None
        recovery_triggered_by = None
        if recent_recovery:
            recovery_triggered_at = recent_recovery.created_at.isoformat()
            recovery_triggered_by = str(recent_recovery.triggered_by)
        return Response(
            {
                "org_has_encryption": org_key_id is not None,
                "org_public_key": org_public_key,
                "org_key_id": org_key_id,
                "user_has_key": user_key_id is not None,
                "user_key_id": user_key_id,
                "has_sealed_org_key": hasattr(membership, "encryption_key"),
                "sealed_org_private_key": sealed_org_private_key,
                "recovery_sealed_org_private_key": recovery_sealed_org_private_key,
                "recovery_triggered_at": recovery_triggered_at,
                "recovery_triggered_by": recovery_triggered_by,
            }
        )


class EncryptionSetupView(AdminOnlyView):
    """Create the org encryption key, the admin's user key, and the sealed membership key."""

    def post(self, request, *args, **kwargs):
        if self.org.encryption_keys.filter(is_active=True).exists():
            return Response(
                {"error": "Encryption is already configured for this organization."},
                status=status.HTTP_409_CONFLICT,
            )
        try:
            keys = {
                "org_public_key": request.data["org_public_key"],
                "user_public_key": request.data["user_public_key"],
                "encrypted_master_key": request.data["encrypted_master_key"],
                "encrypted_private_key": request.data["encrypted_private_key"],
                "sealed_org_private_key": request.data["sealed_org_private_key"],
                "recovery_sealed_org_private_key": request.data[
                    "recovery_sealed_org_private_key"
                ],
                "org_key_id": request.data.get("org_key_id", ""),
                "user_key_id": request.data.get("user_key_id", ""),
            }
        except KeyError as missing:
            return Response(
                {"error": f"Missing required field: {missing.args[0]}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            validate_encryption_keys(keys)
        except ValueError as err:
            return Response({"error": str(err)}, status=status.HTTP_400_BAD_REQUEST)
        try:
            with transaction.atomic():
                org_key, user_key = create_encryption_keys(
                    org=self.org,
                    user=request.user,
                    membership=self.org.memberships.get(user=request.user),
                    keys=keys,
                )
        except IntegrityError:
            # A concurrent request configured the same active org encryption key.
            return Response(
                {"error": "Encryption is already configured for this organization."},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(
            {
                "org_key_id": org_key.key_id,
                "user_key_id": user_key.key_id,
            },
            status=status.HTTP_201_CREATED,
        )


class UserEncryptionKeyView(OrganizationScopedView, APIView):
    """Get, create, or rotate the current user's personal encryption key."""

    def get(self, request, *args, **kwargs):
        user_key = get_object_or_404(UserEncryptionKey, user=request.user)
        return Response(
            {
                "public_key": user_key.public_key,
                "key_id": user_key.key_id,
                "encrypted_master_key": user_key.encrypted_master_key,
                "encrypted_private_key": user_key.encrypted_private_key,
            }
        )

    def post(self, request, *args, **kwargs):
        try:
            public_key, encrypted_master_key, encrypted_private_key = (
                request.data["public_key"],
                request.data["encrypted_master_key"],
                request.data["encrypted_private_key"],
            )
        except KeyError as missing:
            return Response(
                {"error": f"Missing required field: {missing.args[0]}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        key_id = request.data.get("key_id", "")
        try:
            validate_encryption_keys(
                {
                    "public_key": public_key,
                    "key_id": key_id,
                    "encrypted_master_key": encrypted_master_key,
                    "encrypted_private_key": encrypted_private_key,
                }
            )
        except ValueError as err:
            return Response({"error": str(err)}, status=status.HTTP_400_BAD_REQUEST)
        user_key = UserEncryptionKey(
            user=request.user,
            public_key=public_key,
            key_id=key_id,
            encrypted_master_key=encrypted_master_key,
            encrypted_private_key=encrypted_private_key,
        )
        try:
            user_key.save(force_insert=True)
        except IntegrityError:
            return Response(
                {"error": _("A key with this key_id already exists.")},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(
            {"key_id": user_key.key_id},
            status=status.HTTP_201_CREATED,
        )

    def put(self, request, *args, **kwargs):
        try:
            public_key, encrypted_master_key, encrypted_private_key = (
                request.data["public_key"],
                request.data["encrypted_master_key"],
                request.data["encrypted_private_key"],
            )
        except KeyError as missing:
            return Response(
                {"error": f"Missing required field: {missing.args[0]}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        key_id = request.data.get("key_id", "")
        try:
            validate_encryption_keys(
                {
                    "public_key": public_key,
                    "key_id": key_id,
                    "encrypted_master_key": encrypted_master_key,
                    "encrypted_private_key": encrypted_private_key,
                }
            )
        except ValueError as err:
            return Response({"error": str(err)}, status=status.HTTP_400_BAD_REQUEST)
        user_key = get_object_or_404(UserEncryptionKey, user=request.user)
        user_key.public_key = public_key
        user_key.key_id = key_id
        user_key.encrypted_master_key = encrypted_master_key
        user_key.encrypted_private_key = encrypted_private_key
        user_key.save(
            update_fields=[
                "public_key",
                "key_id",
                "encrypted_master_key",
                "encrypted_private_key",
                "modified_at",
            ]
        )
        return Response({"key_id": user_key.key_id})


class MembershipEncryptionKeyListView(AdminOnlyView):
    """List all membership encryption keys for the org, or seal the org key for a member."""

    def get(self, request, *args, **kwargs):
        membership_keys = (
            MembershipEncryptionKey.objects.filter(membership__org=self.org)
            .select_related("membership__user")
            .prefetch_related(
                Prefetch(
                    "membership__user__encryption_keys",
                    queryset=UserEncryptionKey.objects.order_by("-created_at"),
                    to_attr="user_encryption_keys",
                )
            )
        )
        return Response(
            [
                {
                    "membership_id": mk.membership_id,
                    "user_key_id": (
                        mk.membership.user.user_encryption_keys[0].key_id
                        if mk.membership.user.user_encryption_keys
                        else None
                    ),
                    "has_sealed_org_key": True,
                }
                for mk in membership_keys
            ]
        )

    def post(self, request, *args, **kwargs):
        try:
            membership_id, sealed_org_private_key = (
                request.data["membership_id"],
                request.data["sealed_org_private_key"],
            )
        except KeyError as missing:
            return Response(
                {"error": f"Missing required field: {missing.args[0]}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        membership = get_object_or_404(Membership, pk=membership_id, org=self.org)
        org_key = get_object_or_404(OrgEncryptionKey, org=self.org, is_active=True)
        try:
            membership_key = MembershipEncryptionKey.objects.get(membership=membership)
        except MembershipEncryptionKey.DoesNotExist:
            membership_key = MembershipEncryptionKey(
                membership=membership,
                org_encryption_key=org_key,
                sealed_org_private_key=sealed_org_private_key,
            )
            membership_key.save(force_insert=True)
        else:
            membership_key.org_encryption_key = org_key
            membership_key.sealed_org_private_key = sealed_org_private_key
            membership_key.save(
                update_fields=[
                    "org_encryption_key",
                    "sealed_org_private_key",
                    "modified_at",
                ]
            )
        return Response(
            {"membership_id": membership.pk},
            status=status.HTTP_201_CREATED,
        )


class MembershipEncryptionKeyDeleteView(AdminOnlyView):
    """Revoke a member's sealed org private key."""

    def delete(self, request, membership_pk, *args, **kwargs):
        membership = get_object_or_404(Membership, pk=membership_pk, org=self.org)
        get_object_or_404(MembershipEncryptionKey, membership=membership).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class EncryptionSetupPageView(OrganizationScopedView, generic.TemplateView):
    """Render the encryption setup wizard HTML page."""

    template_name = "encryption/setup.html"
    title = _("Encryption setup")
    parent = "accounts:org-home"


class RecoveryTriggerView(OrganizationScopedView, APIView):
    """Log a break-glass recovery event and notify all org members.

    Called by the browser after successfully decrypting the org private key
    from the BIP39 mnemonic. The mnemonic itself is the authorization. Any
    org member who knows the 12 words can trigger recovery, but the event
    is permanently logged and all members are notified.
    """

    def post(self, request, *args, **kwargs):
        org_key = get_object_or_404(OrgEncryptionKey, org=self.org, is_active=True)
        if not org_key.recovery_sealed_org_private_key:
            return Response(
                {"error": "This organization has no recovery key configured."},
                status=status.HTTP_404_NOT_FOUND,
            )
        event = RecoveryEvent.objects.create(
            org_encryption_key=org_key,
            triggered_by=request.user,
        )
        transaction.on_commit(
            lambda: notify_recovery_triggered.enqueue(recovery_event_id=event.pk)
        )
        return Response(
            {
                "recovery_event_id": event.pk,
                "created_at": event.created_at.isoformat(),
            },
            status=status.HTTP_201_CREATED,
        )


class RecoveryPageView(OrganizationScopedView, generic.TemplateView):
    """Render the BIP39 recovery page."""

    template_name = "encryption/recover.html"
    title = _("Encryption recovery")
    parent = "accounts:org-home"
