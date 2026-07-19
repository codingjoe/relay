from django.contrib import admin

from abstract.admin import TimeStampedAdminMixin


class TestTimeStampedAdminMixin:
    def test_merges_readonly_fields(self):
        class MyAdmin(TimeStampedAdminMixin, admin.ModelAdmin):
            readonly_fields = ["my_field"]

        assert "modified_at" in MyAdmin.readonly_fields
        assert "created_at" in MyAdmin.readonly_fields
        assert "my_field" in MyAdmin.readonly_fields

    def test_merges_list_filter(self):
        class MyAdmin(TimeStampedAdminMixin, admin.ModelAdmin):
            list_filter = ["my_filter"]

        assert "modified_at" in MyAdmin.list_filter
        assert "created_at" in MyAdmin.list_filter
        assert "my_filter" in MyAdmin.list_filter

    def test_no_duplicate_fields(self):
        class MyAdmin(TimeStampedAdminMixin, admin.ModelAdmin):
            readonly_fields = ["modified_at", "my_field"]

        assert MyAdmin.readonly_fields.count("modified_at") == 1
        assert MyAdmin.readonly_fields.count("created_at") == 1

    def test_no_subclass_fields_still_gets_defaults(self):
        class MyAdmin(TimeStampedAdminMixin, admin.ModelAdmin): ...

        assert "modified_at" in MyAdmin.readonly_fields
        assert "created_at" in MyAdmin.readonly_fields
