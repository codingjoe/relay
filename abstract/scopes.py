"""Provide the registry every app declares its OAuth scopes in."""

from django.db import models

# Scopes every MCP client must hold, and the only ones granted implicitly.
MCP_REQUIRED_SCOPES = ("openid",)


class Scope(models.TextChoices):
    """
    Base class for OAuth scope enums. Members are `value, label` pairs.

    ```python
    class OrgScope(Scope):
        read = "org:read", _("Read organization data.")
    ```
    """


class DuplicateScopesError(ValueError):
    """Signal values that two enums both declare."""

    def __init__(self, duplicates: set[str]) -> None:
        super().__init__(f"Scopes already registered: {', '.join(sorted(duplicates))}.")


class ScopeRegistry:
    """Collect what relay advertises to OAuth clients."""

    def __init__(self) -> None:
        self.scopes: dict[str, str] = {}

    def register(self, scope_class: type[Scope]) -> type[Scope]:
        """Add one enum's members and return the enum for decorator use."""
        if duplicates := set(self.scopes) & {member.value for member in scope_class}:
            raise DuplicateScopesError(duplicates)
        self.scopes.update((member.value, member.label) for member in scope_class)
        return scope_class

    def supported(self) -> tuple[str, ...]:
        """Return every value relay may advertise."""
        return (*MCP_REQUIRED_SCOPES, *self.scopes)

    def display(self) -> dict[str, str]:
        """Return each value with the label shown to users."""
        return dict(self.scopes)


scopes = ScopeRegistry()
