import datetime

from .. import message


def test_human_duration__milliseconds():
    assert message.human_duration(datetime.timedelta(milliseconds=40)) == "40 ms"


def test_human_duration__seconds():
    assert message.human_duration(datetime.timedelta(milliseconds=300)) == "0.3 s"


def test_human_duration__several_seconds():
    assert message.human_duration(datetime.timedelta(seconds=5)) == "5.0 s"


def test_human_duration__minutes():
    assert message.human_duration(datetime.timedelta(seconds=125)) == "2 min 5 s"


def test_human_duration__whole_minutes():
    assert message.human_duration(datetime.timedelta(minutes=1)) == "1 min"


def test_text_class__success():
    assert message.text_class("success") == "text-success"


def test_text_class__warning():
    assert message.text_class("warning") == "text-warning"


def test_text_class__destructive():
    assert message.text_class("destructive") == "text-destructive"


def test_text_class__other_variants_read_as_muted():
    assert message.text_class("outline") == "text-muted-foreground"


def test_surface_class__variants():
    assert message.surface_class("success") == "bg-success/10"
    assert message.surface_class("warning") == "bg-warning/10"
    assert message.surface_class("destructive") == "bg-destructive/10"


def test_surface_class__other_variants_stay_plain():
    assert message.surface_class("outline") == ""
