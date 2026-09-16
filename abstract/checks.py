from django.apps import apps
from django.core.checks import Warning, register
from django.db.models import CharField, FileField, UniqueConstraint, UUIDField


@register()
def check_uuid_pk_for_message_related(app_configs, **kwargs):
    """Warn if a model with a FK to a UUID-PK model does not use a UUID PK."""
    errors = []
    for model in apps.get_models():
        pk = model._meta.pk
        if not isinstance(pk, UUIDField):
            errors.extend(
                Warning(
                    f"{model._meta.label} has a FK to "
                    f"{related._meta.label} (UUID PK) but uses "
                    f"{type(pk).__name__} as primary key. "
                    "Use UUIDField for message-related models.",
                    obj=model,
                    id="abstract.W001",
                )
                for field in model._meta.get_fields()
                if (
                    (field.is_relation and field.many_to_one)
                    and (related := field.related_model)
                    and isinstance(related._meta.pk, UUIDField)
                )
            )
    return errors


@register()
def check_charfield_with_choices(app_configs, **kwargs):
    """Warn when a CharField has choices. The convention is to use a TextField with choices."""
    errors = []
    for model in apps.get_models():
        errors.extend(
            Warning(
                f"{model._meta.label}.{field.name} uses CharField with "
                "choices. Use a TextField with choices instead. "
                "CharField must only be used when max_length "
                "validation is needed.",
                obj=model,
                id="abstract.W002",
            )
            for field in model._meta.get_fields()
            if type(field) is CharField and field.choices
        )
    return errors


def is_file_field_unique(model, field) -> bool:
    """Return whether the database refuses two rows with the same file."""
    return field.unique or any(
        isinstance(constraint, UniqueConstraint) and field.name in constraint.fields
        for constraint in model._meta.constraints
    )


@register()
def check_file_field_is_unique(app_configs, **kwargs):
    """Warn when a file field is not kept unique by the database."""
    errors = []
    for model in apps.get_models():
        errors.extend(
            Warning(
                f"{field.name} is not unique.",
                hint=(
                    "Pass unique=True or add a UniqueConstraint covering the "
                    "field. A field that may be empty needs a condition that "
                    "skips empty values."
                ),
                obj=model,
                id="abstract.W003",
            )
            for field in model._meta.local_fields
            if isinstance(field, FileField) and not is_file_field_unique(model, field)
        )
    return errors
