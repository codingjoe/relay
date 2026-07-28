"""Django system checks for model field conventions."""

from django.apps import apps
from django.core.checks import Warning, register
from django.db.models import CharField, UUIDField


@register()
def check_uuid_pk_for_message_related(app_configs, **kwargs):
    """Warn if a model with a FK to a UUID-PK model doesn't use UUID PK.

    Models related to message models (IncomingMessage, OutgoingMessage, etc.)
    should use UUIDv7 as their primary key for consistency and to avoid
    potential overflow when the UUID is larger than bigint.
    """
    errors = []
    for model in apps.get_models():
        pk = model._meta.pk
        if not isinstance(pk, UUIDField):
            for field in model._meta.get_fields():
                if (
                    (field.is_relation and field.many_to_one)
                    and (related := field.related_model)
                    and isinstance(related._meta.pk, UUIDField)
                ):
                    errors.append(
                        Warning(
                            f"{model._meta.label} has a FK to "
                            f"{related._meta.label} (UUID PK) but uses "
                            f"{type(pk).__name__} as primary key. "
                            "Use UUIDField for message-related models.",
                            obj=model,
                            id="abstract.W001",
                        )
                    )
    return errors


@register()
def check_charfield_with_choices(app_configs, **kwargs):
    """Warn if a CharField has choices — should use TextField with choices.

    In PostgreSQL there is no performance advantage to varchar over text.
    Choice fields should use ``TextField(choices=...)`` — Django's choice
    validation works without ``max_length``.
    """
    errors = []
    for model in apps.get_models():
        for field in model._meta.get_fields():
            if type(field) is CharField and field.choices:
                errors.append(
                    Warning(
                        f"{model._meta.label}.{field.name} uses CharField with "
                        "choices — use TextField with choices instead. "
                        "CharField should only be used when max_length "
                        "validation is needed.",
                        obj=model,
                        id="abstract.W002",
                    )
                )
    return errors
