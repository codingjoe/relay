import pytest
from django.contrib import admin
from django.db import models
from django.urls import reverse


class TestAdminSite:
    @pytest.mark.django_db
    def test_get__index_renders(self, client, admin_user):
        client.force_login(admin_user)
        response = client.get(reverse("admin:index"))

        assert response.status_code == 200
        assert "/static/admin/" in response.content.decode()


class TestAdminAutocomplete:
    def test_related_form_fields_use_autocomplete(self):
        missing = []
        for model, model_admin in admin.site._registry.items():
            handled = (
                set(model_admin.get_autocomplete_fields(request=None))
                | set(model_admin.get_readonly_fields(request=None))
                | set(model_admin.raw_id_fields)
                | set(model_admin.filter_horizontal)
                | set(model_admin.filter_vertical)
            )
            related = [
                field
                for field in model._meta.get_fields()
                if field.editable
                and not field.auto_created
                and field.name not in handled
                and (
                    isinstance(field, models.ForeignKey)
                    or (
                        isinstance(field, models.ManyToManyField)
                        and field.remote_field.through._meta.auto_created
                    )
                )
            ]
            missing.extend(f"{model._meta.label}.{field.name}" for field in related)

        assert missing == []
