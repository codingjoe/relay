import base64
import io
from types import SimpleNamespace

import dkim
import dns.exception
import dns.resolver
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from abstract.mailauth import (
    Alignment,
    AuthResult,
    Disposition,
    DmarcEvaluation,
    DmarcPolicy,
)


class TestDmarcPolicyDisposition:
    def test_disposition__returns_none_when_dkim_authenticated(self):
        policy = DmarcPolicy(p="reject")
        assert (
            policy.disposition(dkim_authenticated=True, spf_authenticated=False)
            == Disposition.NONE
        )

    def test_disposition__returns_none_when_spf_authenticated(self):
        policy = DmarcPolicy(p="reject")
        assert (
            policy.disposition(dkim_authenticated=False, spf_authenticated=True)
            == Disposition.NONE
        )

    def test_disposition__returns_none_when_both_authenticated(self):
        policy = DmarcPolicy(p="reject")
        assert (
            policy.disposition(dkim_authenticated=True, spf_authenticated=True)
            == Disposition.NONE
        )

    def test_disposition__returns_quarantine_when_neither_authenticated(self):
        policy = DmarcPolicy(p="quarantine")
        assert (
            policy.disposition(dkim_authenticated=False, spf_authenticated=False)
            == Disposition.QUARANTINE
        )

    def test_disposition__returns_reject_when_neither_authenticated(self):
        policy = DmarcPolicy(p="reject")
        assert (
            policy.disposition(dkim_authenticated=False, spf_authenticated=False)
            == Disposition.REJECT
        )

    def test_disposition__returns_none_for_unknown_policy(self):
        policy = DmarcPolicy(p="invalid_value")
        assert (
            policy.disposition(dkim_authenticated=False, spf_authenticated=False)
            == Disposition.NONE
        )

    def test_disposition__returns_none_for_default_policy(self):
        policy = DmarcPolicy()
        assert (
            policy.disposition(dkim_authenticated=False, spf_authenticated=False)
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

SPOOFED_EMAIL = (
    b"Received: from mx.victim.com (mx.victim.com [192.0.2.1])\r\n"
    b" by mail.relay.example.com with ESMTP\r\n"
    b"From: ceo@victim.com\r\n"
    b"To: postmaster@example.com\r\n"
    b"Subject: Urgent\r\n"
    b"\r\n"
    b"Wire the money now\r\n"
)


def make_dkim_signature_header(dns_resolver, raw_bytes, domain_name):
    """Return a DKIM-Signature header line for raw bytes.

    The public key is published on the stub DNS resolver.
    """
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_key_b64 = base64.b64encode(
        private_key.public_key().public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    ).decode("ascii")
    record = f"v=DKIM1; k=rsa; t=s; h=sha256; p={public_key_b64};"
    chunks = [record[index : index + 255] for index in range(0, len(record), 255)]
    dns_resolver.add(
        f"sel1._domainkey.{domain_name}",
        "TXT",
        " ".join(f'"{chunk}"' for chunk in chunks),
    )
    return dkim.sign(raw_bytes, b"sel1", domain_name.encode(), private_pem)


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

    def test_from_bytes__rejects_spoofed_sender_with_aligned_envelope(
        self, dns_resolver
    ):
        dns_resolver.add("victim.com", "TXT", '"v=spf1 -all"')
        dns_resolver.add("_dmarc.victim.com", "TXT", '"v=DMARC1; p=reject"')

        evaluation = DmarcEvaluation.from_bytes(
            SPOOFED_EMAIL, "ceo@victim.com", "198.51.100.99"
        )

        assert evaluation.spf_result == AuthResult.FAIL
        assert evaluation.spf_alignment == Alignment.PASS
        assert evaluation.dmarc_authenticated is False
        assert evaluation.disposition == Disposition.REJECT

    def test_from_bytes__evaluates_spf_against_client_ip_not_received_header(
        self, dns_resolver
    ):
        dns_resolver.add("victim.com", "TXT", '"v=spf1 ip4:192.0.2.1 -all"')
        dns_resolver.add("_dmarc.victim.com", "TXT", '"v=DMARC1; p=reject"')

        evaluation = DmarcEvaluation.from_bytes(
            SPOOFED_EMAIL, "ceo@victim.com", "198.51.100.99"
        )

        assert evaluation.source_ip_address == "198.51.100.99"
        assert evaluation.spf_result == AuthResult.FAIL
        assert evaluation.disposition == Disposition.REJECT

    def test_from_bytes__falls_back_to_received_header_without_client_ip(
        self, dns_resolver
    ):
        dns_resolver.add("victim.com", "TXT", '"v=spf1 ip4:192.0.2.1 -all"')
        dns_resolver.add("_dmarc.victim.com", "TXT", '"v=DMARC1; p=reject"')

        evaluation = DmarcEvaluation.from_bytes(SPOOFED_EMAIL, "ceo@victim.com")

        assert evaluation.source_ip_address == "192.0.2.1"
        assert evaluation.spf_result == AuthResult.PASS

    def test_from_bytes__rejects_spf_pass_without_alignment(self, dns_resolver):
        dns_resolver.add("attacker.example", "TXT", '"v=spf1 ip4:198.51.100.99 -all"')
        dns_resolver.add("_dmarc.victim.example", "TXT", '"v=DMARC1; p=reject"')
        raw = (
            b"From: ceo@victim.example\r\n"
            b"To: postmaster@example.com\r\n"
            b"\r\n"
            b"Wire the money now\r\n"
        )

        evaluation = DmarcEvaluation.from_bytes(
            raw, "spoof@attacker.example", "198.51.100.99"
        )

        assert evaluation.spf_result == AuthResult.PASS
        assert evaluation.spf_alignment == Alignment.FAIL
        assert evaluation.dmarc_authenticated is False
        assert evaluation.disposition == Disposition.REJECT

    def test_from_bytes__rejects_ipv6_client_ip_without_received_fallback(
        self, dns_resolver
    ):
        dns_resolver.add("victim.com", "TXT", '"v=spf1 ip4:192.0.2.1 -all"')
        dns_resolver.add("_dmarc.victim.com", "TXT", '"v=DMARC1; p=reject"')

        evaluation = DmarcEvaluation.from_bytes(
            SPOOFED_EMAIL, "ceo@victim.com", "2001:db8::1"
        )

        assert evaluation.source_ip_address == "2001:db8::1"
        assert evaluation.spf_result == AuthResult.FAIL
        assert evaluation.disposition == Disposition.REJECT

    def test_from_bytes__accepts_dkim_authenticated_sender(self, dns_resolver):
        dns_resolver.add("example.org", "TXT", '"v=spf1 -all"')
        dns_resolver.add("_dmarc.example.org", "TXT", '"v=DMARC1; p=reject"')
        raw = (
            make_dkim_signature_header(dns_resolver, RAW_EMAIL, "example.org")
            + RAW_EMAIL
        )

        evaluation = DmarcEvaluation.from_bytes(
            raw, "external@example.org", "198.51.100.99"
        )

        assert evaluation.dkim_result == AuthResult.PASS
        assert evaluation.dkim_alignment == Alignment.PASS
        assert evaluation.dmarc_authenticated is True
        assert evaluation.disposition == Disposition.NONE


class TestDmarcEvaluationFromMessage:
    def test_from_message__extracts_source_ip_from_received_header(self, dns_resolver):
        dns_resolver.add("example.org", "TXT", '"v=spf1 ip4:192.0.2.1 -all"')
        dns_resolver.add("_dmarc.example.org", "TXT", '"v=DMARC1; p=none"')
        raw = (
            b"Received: from mx.example.org (mx.example.org [192.0.2.1])\r\n"
            b"From: external@example.org\r\n"
            b"\r\n"
            b"Something happened\r\n"
        )
        message = SimpleNamespace(
            mail_from="external@example.org", raw_body=io.BytesIO(raw)
        )

        evaluation = DmarcEvaluation.from_message(message)

        assert evaluation.source_ip_address == "192.0.2.1"
        assert evaluation.spf_result == AuthResult.PASS
