from django.apps import apps
from django.contrib import admin
from django.core.checks import Warning, register
from django.db.models import (
    CharField,
    FileField,
    ForeignKey,
    ManyToManyField,
    UniqueConstraint,
    UUIDField,
)


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
            if (
                isinstance(field, FileField)
                and not field.unique
                and not any(
                    field.name in constraint.fields
                    for constraint in model._meta.constraints
                    if isinstance(constraint, UniqueConstraint)
                )
                and not any(
                    field.name in fields for fields in model._meta.unique_together
                )
            )
        )
    return errors


@register()
def check_admin_related_fields_use_autocomplete(app_configs, **kwargs):
    """Warn when an admin renders a relation field as a plain select box."""
    warnings = []
    for model, model_admin in admin.site._registry.items():
        handled = (
            set(model_admin.get_autocomplete_fields(request=None))
            | set(model_admin.get_readonly_fields(request=None))
            | set(model_admin.raw_id_fields)
            | set(model_admin.filter_horizontal)
            | set(model_admin.filter_vertical)
        )
        warnings.extend(
            Warning(
                f"{model._meta.label}.{field.name} renders as a plain select box.",
                hint="Add the field to autocomplete_fields on the admin.",
                obj=model_admin.__class__,
                id="abstract.W004",
            )
            for field in model._meta.get_fields()
            if field.editable
            and not field.auto_created
            and field.name not in handled
            and (
                isinstance(field, ForeignKey)
                or (
                    isinstance(field, ManyToManyField)
                    and field.remote_field.through._meta.auto_created
                )
            )
        )
    return warnings
