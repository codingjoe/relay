import datetime

from .. import message


def test_human_duration__milliseconds():
    duration = datetime.timedelta(milliseconds=300)

    assert message.human_duration(duration) == "300 milliseconds"


def test_human_duration__seconds():
    assert message.human_duration(datetime.timedelta(seconds=5)) == "5 seconds"


def test_human_duration__minutes():
    assert message.human_duration(datetime.timedelta(seconds=125)) == "2 minutes"


def test_human_duration__whole_minutes():
    assert message.human_duration(datetime.timedelta(minutes=1)) == "a minute"


def test_human_duration__hours():
    assert message.human_duration(datetime.timedelta(hours=3)) == "3 hours"
