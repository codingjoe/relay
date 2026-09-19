from .. import domains


def test_apex_suffix__relative_name():
    assert (
        domains.apex_suffix("mail.relay.acme.com", domains.Domain(name="acme.com"))
        == ".acme.com"
    )


def test_apex_suffix__at_the_apex():
    assert domains.apex_suffix("acme.com", domains.Domain(name="acme.com")) == ""


def test_apex_suffix__unrelated_name():
    assert domains.apex_suffix("example.net", domains.Domain(name="acme.com")) == ""
