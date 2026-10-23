from unittest.mock import patch

from abstract.checks import check_models_with_str_define_repr


class FakeMeta:
    app_config = object()
    label = "fake.Model"


class ModelWithStr:
    _meta = FakeMeta()

    def __str__(self):
        return "model"


class ModelWithRepresentation(ModelWithStr):
    def __repr__(self):
        return "<ModelWithRepresentation>"


def test_check_models_with_str_define_repr__warns_without_repr():
    with (
        patch("abstract.checks.apps.get_models", return_value=[ModelWithStr]),
        patch("abstract.checks.is_first_party", return_value=True),
    ):
        warnings = check_models_with_str_define_repr(None)

    assert [warning.id for warning in warnings] == ["abstract.W005"]
    assert warnings[0].msg == "fake.Model defines __str__ without __repr__."


def test_check_models_with_str_define_repr__passes_with_repr():
    with (
        patch(
            "abstract.checks.apps.get_models", return_value=[ModelWithRepresentation]
        ),
        patch("abstract.checks.is_first_party", return_value=True),
    ):
        assert check_models_with_str_define_repr(None) == []
