from abstract.mailauth import Disposition, DmarcEvaluation, DmarcPolicy


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
