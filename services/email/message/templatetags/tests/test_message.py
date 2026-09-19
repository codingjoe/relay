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
