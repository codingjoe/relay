class TimeStampedAdminMixin:
    readonly_fields = ["modified_at", "created_at"]
    list_filter = ["modified_at", "created_at"]

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        for attr in ("readonly_fields", "list_filter"):
            cls_attr = getattr(cls, attr, [])
            mixin_attr = TimeStampedAdminMixin.__dict__.get(attr, [])
            merged = [*mixin_attr, *(f for f in cls_attr if f not in mixin_attr)]
            setattr(cls, attr, merged)
