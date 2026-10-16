"""Resolve the relay user an MCP access token was issued for."""

from asgiref.sync import sync_to_async
from django.contrib.auth.models import User
from fastmcp.exceptions import AuthorizationError
from fastmcp.server.auth import AccessToken
from fastmcp.server.dependencies import CurrentAccessToken


class MalformedSubjectError(AuthorizationError):
    """Signal a claim that carries no numeric user id."""

    def __init__(self):
        super().__init__("The access token carries no usable subject.")


class UnknownUserError(AuthorizationError):
    """Signal a lookup for an account that no longer exists."""

    def __init__(self):
        super().__init__("The access token belongs to a user that no longer exists.")


class InactiveUserError(AuthorizationError):
    """Signal a lookup for a deactivated account."""

    def __init__(self):
        super().__init__("The account is inactive.")


async def authenticated_user(
    access_token: AccessToken = CurrentAccessToken(),  # noqa: B008 -- dependency
) -> User:
    """Return the active account an access token was issued for."""
    try:
        user_id = int(access_token.claims["sub"])
    except (KeyError, TypeError, ValueError) as error:
        raise MalformedSubjectError from error
    try:
        user = await sync_to_async(User.objects.get)(id=user_id)
    except User.DoesNotExist as error:
        raise UnknownUserError from error
    if not user.is_active:
        raise InactiveUserError
    return user
