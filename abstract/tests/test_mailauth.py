import dkim
import dns.exception
import dns.resolver
import pytest

from abstract.mailauth import AuthResult, Disposition, DmarcEvaluation, DmarcPolicy


class TestDmarcPolicyDisposition:
    def test_disposition__returns_none_when_dkim_aligned(self):
        policy = DmarcPolicy(p="reject")
        assert (
            policy.disposition(dkim_aligned=True, spf_aligned=False) == Disposition.NONE
        )

    def test_disposition__returns_none_when_spf_aligned(self):
        policy = DmarcPolicy(p="reject")
        assert (
            policy.disposition(dkim_aligned=False, spf_aligned=True) == Disposition.NONE
        )

    def test_disposition__returns_none_when_both_aligned(self):
        policy = DmarcPolicy(p="reject")
        assert (
            policy.disposition(dkim_aligned=True, spf_aligned=True) == Disposition.NONE
        )

    def test_disposition__returns_quarantine_when_neither_aligned(self):
        policy = DmarcPolicy(p="quarantine")
        assert (
            policy.disposition(dkim_aligned=False, spf_aligned=False)
            == Disposition.QUARANTINE
        )

    def test_disposition__returns_reject_when_neither_aligned(self):
        policy = DmarcPolicy(p="reject")
        assert (
            policy.disposition(dkim_aligned=False, spf_aligned=False)
            == Disposition.REJECT
        )

    def test_disposition__returns_none_for_unknown_policy(self):
        policy = DmarcPolicy(p="invalid_value")
        assert (
            policy.disposition(dkim_aligned=False, spf_aligned=False)
            == Disposition.NONE
        )

    def test_disposition__returns_none_for_default_policy(self):
        policy = DmarcPolicy()
        assert (
            policy.disposition(dkim_aligned=False, spf_aligned=False)
            == Disposition.NONE
        )


class TestDmarcPolicyAddresses:
    def test_rua_address__extracts_mailto(self):
        policy = DmarcPolicy(rua="mailto:dmarc@example.com,mailto:other@example.com")
        assert policy.rua_address == "dmarc@example.com"

    def test_ruf_address__extracts_mailto(self):
        policy = DmarcPolicy(ruf="mailto:ruf@example.com")
        assert policy.ruf_address == "ruf@example.com"

    def test_rua_address__returns_empty_when_no_rua(self):
        policy = DmarcPolicy()
        assert policy.rua_address == ""

    def test_rua_address__returns_empty_when_not_mailto(self):
        policy = DmarcPolicy(rua="https://example.com/dmarc")
        assert policy.rua_address == ""


class TestDmarcPolicyLookup:
    def test_lookup__is_published_for_served_dmarc_record(self, dns_resolver):
        dns_resolver.add("_dmarc.example.org", "TXT", '"v=DMARC1; p=reject"')

        policy = DmarcPolicy.lookup("example.org")

        assert policy.is_published is True

    def test_lookup__is_not_published_when_nxdomain(self, dns_resolver):
        policy = DmarcPolicy.lookup("example.org")

        assert policy.is_published is False
        assert policy.temperror is False

    def test_lookup__is_not_published_when_no_answer(self, dns_resolver):
        dns_resolver.add("_dmarc.example.org", "TXT")

        policy = DmarcPolicy.lookup("example.org")

        assert policy.is_published is False
        assert policy.temperror is False

    def test_lookup__temperror_when_dns_times_out(self, dns_resolver):
        dns_resolver.fail("_dmarc.example.org", "TXT", dns.exception.Timeout())

        policy = DmarcPolicy.lookup("example.org")

        assert policy.is_published is False
        assert policy.temperror is True

    def test_lookup__temperror_when_no_nameservers(self, dns_resolver):
        dns_resolver.fail("_dmarc.example.org", "TXT", dns.resolver.NoNameservers())

        policy = DmarcPolicy.lookup("example.org")

        assert policy.is_published is False
        assert policy.temperror is True

    def test_lookup__parses_pct_field(self, dns_resolver):
        dns_resolver.add("_dmarc.example.org", "TXT", '"v=DMARC1; p=reject; pct=25;"')

        policy = DmarcPolicy.lookup("example.org")

        assert policy.pct == 25
        assert policy.is_published is True

    def test_lookup__keeps_default_pct_for_malformed_value(self, dns_resolver):
        dns_resolver.add("_dmarc.example.org", "TXT", '"v=DMARC1; p=none; pct=abc"')

        policy = DmarcPolicy.lookup("example.org")

        assert policy.pct == 100
        assert policy.is_published is True

    def test_lookup__is_not_published_when_no_dmarc_record(self, dns_resolver):
        dns_resolver.add("_dmarc.example.org", "TXT", '"v=spf1 -all"')

        policy = DmarcPolicy.lookup("example.org")

        assert policy == DmarcPolicy()


class TestDmarcEvaluationExtractDomain:
    def test_extract_domain__returns_domain_from_email(self):
        assert DmarcEvaluation.extract_domain("user@example.com") == "example.com"

    def test_extract_domain__returns_domain_from_header(self):
        assert (
            DmarcEvaluation.extract_domain("User <user@example.com>") == "example.com"
        )

    def test_extract_domain__returns_lowercased(self):
        assert DmarcEvaluation.extract_domain("user@EXAMPLE.COM") == "example.com"

    def test_extract_domain__returns_input_when_no_match(self):
        assert DmarcEvaluation.extract_domain("example.com") == "example.com"


class TestDmarcEvaluationCheckAlignment:
    def test_check_alignment__pass_relaxed_same_domain(self):
        assert (
            DmarcEvaluation.check_alignment("example.com", "example.com", "r") is True
        )

    def test_check_alignment__pass_relaxed_subdomain(self):
        assert (
            DmarcEvaluation.check_alignment("mail.example.com", "example.com", "r")
            is True
        )

    def test_check_alignment__fail_relaxed_different_domain(self):
        assert DmarcEvaluation.check_alignment("evil.com", "example.com", "r") is False

    def test_check_alignment__pass_strict_exact_match(self):
        assert (
            DmarcEvaluation.check_alignment("example.com", "example.com", "s") is True
        )

    def test_check_alignment__fail_strict_subdomain(self):
        assert (
            DmarcEvaluation.check_alignment("mail.example.com", "example.com", "s")
            is False
        )

    def test_check_alignment__fail_when_empty_auth_domain(self):
        assert DmarcEvaluation.check_alignment("", "example.com", "r") is False

    def test_check_alignment__fail_when_empty_header_domain(self):
        assert DmarcEvaluation.check_alignment("example.com", "", "r") is False


class TestDmarcEvaluationCheckSpf:
    def test_check_spf__temperror_when_dns_times_out(self, dns_resolver):
        dns_resolver.fail("example.org", "TXT", dns.exception.Timeout())

        assert DmarcEvaluation.check_spf("192.0.2.1", "example.org") == (
            AuthResult.TEMPERROR,
            "example.org",
        )

    def test_check_spf__temperror_when_no_nameservers(self, dns_resolver):
        dns_resolver.fail("example.org", "TXT", dns.resolver.NoNameservers())

        assert DmarcEvaluation.check_spf("192.0.2.1", "example.org") == (
            AuthResult.TEMPERROR,
            "example.org",
        )


class TestDmarcEvaluationVerifyDkim:
    def test_verify_dkim__permerror_when_message_starts_with_continuation(self):
        raw = b" continuation\r\n\r\nbody\r\n"

        with pytest.raises(IndexError):
            dkim.verify(raw)

        assert DmarcEvaluation.verify_dkim(raw) == (AuthResult.PERMERROR, "")


RAW_EMAIL = (
    b"From: external@example.org\r\n"
    b"To: user@example.com\r\n"
    b"Subject: Test\r\n"
    b"\r\n"
    b"Something happened\r\n"
)


class TestDmarcEvaluationFromBytes:
    def test_from_bytes__dmarc_policy_is_published_for_served_policy(
        self, dns_resolver
    ):
        dns_resolver.add("_dmarc.example.org", "TXT", '"v=DMARC1; p=none"')

        evaluation = DmarcEvaluation.from_bytes(RAW_EMAIL, "external@example.org")

        assert evaluation.dmarc_policy_is_published is True

    def test_from_bytes__dmarc_policy_not_published_without_policy(self, dns_resolver):
        evaluation = DmarcEvaluation.from_bytes(RAW_EMAIL, "external@example.org")

        assert evaluation.dmarc_policy_is_published is False
        assert evaluation.dmarc_policy_temperror is False

    def test_from_bytes__dmarc_policy_temperror_when_lookup_times_out(
        self, dns_resolver
    ):
        dns_resolver.fail("_dmarc.example.org", "TXT", dns.exception.Timeout())

        evaluation = DmarcEvaluation.from_bytes(RAW_EMAIL, "external@example.org")

        assert evaluation.dmarc_policy_temperror is True

    def test_from_bytes__spf_temperror_when_spf_lookup_times_out(self, dns_resolver):
        dns_resolver.add("_dmarc.example.org", "TXT", '"v=DMARC1; p=none"')
        raw = (
            b"From: external@example.org\r\n"
            b"Received: from mx.example.net (mx.example.net [192.0.2.1])\r\n"
            b"\r\n"
            b"Something happened\r\n"
        )
        dns_resolver.fail("example.org", "TXT", dns.exception.Timeout())

        evaluation = DmarcEvaluation.from_bytes(raw, "external@example.org")

        assert evaluation.spf_result == AuthResult.TEMPERROR
