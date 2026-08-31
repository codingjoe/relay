import datetime
import email
import logging

import authres
import dkim
import pytest

from abstract.mailauth import Alignment, AuthResult, DmarcEvaluation
from accounts.models import Organization
from conftest import StubResolver
from domains.models import Domain
from domains.resolver import dkim_record
from kms import keys
from kms.models import SigningKey
from services.email.mta.arc import (
    ARC_INSTANCE_LIMIT,
    ChainResult,
    create_authentication_results,
    fetch_dkim_key_record,
    is_trusted_authentication_results,
    remove_untrusted_authentication_results,
    seal_message,
    verify_arc_chain,
)
from services.email.mta.tests.conftest import make_dmarc_evaluation, make_raw_email

AUTHSERV_ID = "mail.relay.example.com"


def register_dkim_key_record(
    resolver: StubResolver, selector: str, domain_name: str, key: SigningKey
) -> None:
    """Serve a signing key's DKIM public key record from the stub."""
    record = dkim_record(key)
    chunks = [record[index : index + 255] for index in range(0, len(record), 255)]
    resolver.add(
        f"{selector}._domainkey.{domain_name}",
        "TXT",
        " ".join(f'"{chunk}"' for chunk in chunks),
    )


def register_dkim_record(resolver: StubResolver, domain: Domain) -> None:
    """Serve the domain's RSA-2048 DKIM public key record from the stub."""
    selector, key = domain.dkim_ciphers[0]
    register_dkim_key_record(resolver, selector, domain.name, key)


def parse_arc_seals(raw_bytes: bytes) -> list[dict[str, str]]:
    """Return the tag dict of every ARC-Seal, topmost first."""
    return [
        dict(
            tag.split("=", 1)
            for tag in " ".join(seal.split()).split("; ")
            if "=" in tag
        )
        for seal in email.message_from_bytes(raw_bytes).get_all("ARC-Seal")
    ]


def parse_ar_clauses(value: str) -> list[tuple[str, str]]:
    """Return the (method, result) clauses of an AR or AAR header value."""
    if value.startswith("i="):
        value = value.partition("; ")[2]
    header = authres.AuthenticationResultsHeader.parse(
        "Authentication-Results: " + " ".join(value.split())
    )
    return [(result.method, result.result) for result in header.results]


def tamper_arc_seal(raw_bytes: bytes) -> bytes:
    """Corrupt the b= signature value of the first ARC-Seal."""
    start = raw_bytes.index(b"b=") + len(b"b=")
    return raw_bytes[:start] + b"A" * 20 + raw_bytes[start + 20 :]


def strip_ams_header_space(raw_bytes: bytes) -> bytes:
    """Drop the space after the colon of the ARC-Message-Signature header."""
    return raw_bytes.replace(b"ARC-Message-Signature: ", b"ARC-Message-Signature:", 1)


def make_garbage_seal_chain(instances: int) -> bytes:
    """Return a message with hand-written ARC-Seal headers with invalid keys."""
    seals = "".join(
        f"ARC-Seal: i={i}; cv=none; a=rsa-sha256; d=example.com; "
        f"s=relay-rsa2048; t=1700000000; b={'A' * 100}\r\n"
        for i in range(1, instances + 1)
    )
    return seals.encode() + make_raw_email()


def make_terminated_chain(org: Organization, dns_resolver: StubResolver) -> bytes:
    """Return a sealed message whose most recent ARC-Seal reports cv=fail."""
    first = Domain.objects.create(name="example.com", org=org)
    second = Domain.objects.create(name="forwarder.example", org=org)
    for domain in (first, second):
        register_dkim_record(dns_resolver, domain)
    sealed = seal_message(make_raw_email(), make_dmarc_evaluation(), first)
    tampered = tamper_arc_seal(sealed)
    return seal_message(tampered, make_dmarc_evaluation(), second)


class TestCreateAuthenticationResults:
    def test_create_authentication_results__renders_full_evaluation(self):
        result = create_authentication_results(
            make_dmarc_evaluation(), AUTHSERV_ID, ChainResult.NONE
        )

        assert result == (
            b"Authentication-Results: mail.relay.example.com; arc=none; "
            b"spf=pass smtp.mailfrom=example.org; "
            b"dkim=pass header.d=example.org; "
            b"dmarc=pass (dis=none) header.from=example.org"
        )

    def test_create_authentication_results__renders_terminated_chain_as_fail(self):
        result = create_authentication_results(
            make_dmarc_evaluation(), AUTHSERV_ID, ChainResult.TERMINATED
        )

        assert b"arc=fail" in result

    def test_create_authentication_results__omits_spf_property_without_domain(self):
        result = create_authentication_results(
            make_dmarc_evaluation(spf_domain=""), AUTHSERV_ID, ChainResult.NONE
        )

        assert b"spf=pass" in result
        assert b"smtp.mailfrom=" not in result

    def test_create_authentication_results__omits_dkim_property_without_domain(self):
        result = create_authentication_results(
            make_dmarc_evaluation(dkim_domain=""), AUTHSERV_ID, ChainResult.NONE
        )

        assert b"dkim=pass" in result
        assert b"header.d=" not in result

    def test_create_authentication_results__omits_dmarc_header_from_property(self):
        result = create_authentication_results(
            make_dmarc_evaluation(header_from=""), AUTHSERV_ID, ChainResult.NONE
        )

        assert b"dmarc=pass" in result
        assert b"header.from=" not in result

    def test_create_authentication_results__dmarc_fails_when_no_alignment_passes(self):
        result = create_authentication_results(
            make_dmarc_evaluation(
                dkim_alignment=Alignment.FAIL, spf_alignment=Alignment.FAIL
            ),
            AUTHSERV_ID,
            ChainResult.NONE,
        )

        assert b"dmarc=fail" in result

    def test_create_authentication_results__dmarc_fails_when_spf_fails_despite_alignment(
        self,
    ):
        result = create_authentication_results(
            make_dmarc_evaluation(
                spf_result=AuthResult.FAIL,
                dkim_result=AuthResult.FAIL,
                dkim_alignment=Alignment.FAIL,
            ),
            AUTHSERV_ID,
            ChainResult.NONE,
        )

        assert b"dmarc=fail" in result

    def test_create_authentication_results__dmarc_passes_when_dkim_passes_and_aligns(
        self,
    ):
        result = create_authentication_results(
            make_dmarc_evaluation(
                spf_result=AuthResult.FAIL, spf_alignment=Alignment.FAIL
            ),
            AUTHSERV_ID,
            ChainResult.NONE,
        )

        assert b"dmarc=pass" in result

    def test_create_authentication_results__dmarc_passes_when_spf_passes_and_aligns(
        self,
    ):
        result = create_authentication_results(
            make_dmarc_evaluation(
                dkim_result=AuthResult.FAIL, dkim_alignment=Alignment.FAIL
            ),
            AUTHSERV_ID,
            ChainResult.NONE,
        )

        assert b"dmarc=pass" in result

    def test_create_authentication_results__dmarc_none_without_published_policy(self):
        result = create_authentication_results(
            make_dmarc_evaluation(dmarc_policy_is_published=False),
            AUTHSERV_ID,
            ChainResult.NONE,
        )

        assert b"dmarc=none" in result
        assert b"dmarc=pass" not in result

    def test_create_authentication_results__dmarc_none_despite_failed_alignment(self):
        result = create_authentication_results(
            make_dmarc_evaluation(
                dkim_alignment=Alignment.FAIL,
                spf_alignment=Alignment.FAIL,
                dmarc_policy_is_published=False,
            ),
            AUTHSERV_ID,
            ChainResult.NONE,
        )

        assert b"dmarc=none" in result
        assert b"dmarc=fail" not in result

    def test_create_authentication_results__dmarc_temperror_when_policy_lookup_failed(
        self,
    ):
        result = create_authentication_results(
            make_dmarc_evaluation(dmarc_policy_temperror=True),
            AUTHSERV_ID,
            ChainResult.NONE,
        )

        assert b"dmarc=temperror" in result
        assert b"dmarc=pass" not in result

    def test_create_authentication_results__spf_temperror_when_spf_lookup_failed(self):
        result = create_authentication_results(
            make_dmarc_evaluation(spf_result=AuthResult.TEMPERROR),
            AUTHSERV_ID,
            ChainResult.NONE,
        )

        assert b"spf=temperror" in result

    def test_create_authentication_results__dmarc_none_round_trips_with_authres(self):
        line = create_authentication_results(
            make_dmarc_evaluation(dmarc_policy_is_published=False),
            AUTHSERV_ID,
            ChainResult.NONE,
        )

        header = authres.AuthenticationResultsHeader.parse(line.decode("utf-8"))

        assert [(res.method, res.result) for res in header.results] == [
            ("arc", "none"),
            ("spf", "pass"),
            ("dkim", "pass"),
            ("dmarc", "none"),
        ]

    def test_create_authentication_results__round_trips_with_authres(self):
        line = create_authentication_results(
            make_dmarc_evaluation(), AUTHSERV_ID, ChainResult.NONE
        )

        header = authres.AuthenticationResultsHeader.parse(line.decode("utf-8"))

        assert header.authserv_id == AUTHSERV_ID
        assert [(res.method, res.result) for res in header.results] == [
            ("arc", "none"),
            ("spf", "pass"),
            ("dkim", "pass"),
            ("dmarc", "pass"),
        ]


class TestIsTrustedAuthenticationResults:
    def test_is_trusted_authentication_results__matches_own_authserv_id(self):
        header = b"Authentication-Results: mail.relay.example.com; spf=pass\r\n"

        assert is_trusted_authentication_results(header, AUTHSERV_ID) is False

    def test_is_trusted_authentication_results__keeps_foreign_authserv_id(self):
        header = b"Authentication-Results: mx.other.example; spf=pass\r\n"

        assert is_trusted_authentication_results(header, AUTHSERV_ID) is True

    def test_is_trusted_authentication_results__keeps_other_headers(self):
        header = b"Subject: mail.relay.example.com\r\n"

        assert is_trusted_authentication_results(header, AUTHSERV_ID) is True

    def test_is_trusted_authentication_results__drops_unparseable_header(self):
        header = b"Authentication-Results: mx.other.example; spf\r\n"

        assert is_trusted_authentication_results(header, AUTHSERV_ID) is False

    def test_is_trusted_authentication_results__drops_non_utf8_header(self):
        header = b"Authentication-Results: mail.relay.example.com; spf=\xffpass\r\n"

        assert is_trusted_authentication_results(header, AUTHSERV_ID) is False


class TestRemoveUntrustedAuthenticationResults:
    def test_remove_untrusted_authentication_results__removes_own_authserv_id(self):
        raw = (
            b"From: external@example.org\r\n"
            b"Authentication-Results: mail.relay.example.com; spf=pass\r\n"
            b"Subject: Test\r\n"
            b"\r\n"
            b"Body\r\n"
        )

        result = remove_untrusted_authentication_results(raw, AUTHSERV_ID)

        assert b"Authentication-Results: mail.relay.example.com" not in result
        assert b"From: external@example.org\r\n" in result
        assert b"Subject: Test\r\n" in result
        assert b"Body\r\n" in result

    def test_remove_untrusted_authentication_results__keeps_foreign_authserv_id(self):
        raw = (
            b"From: external@example.org\r\n"
            b"Authentication-Results: mx.other.example; dkim=pass\r\n"
            b"\r\n"
            b"Body\r\n"
        )

        result = remove_untrusted_authentication_results(raw, AUTHSERV_ID)

        assert result == raw

    def test_remove_untrusted_authentication_results__removes_continuation_lines(self):
        raw = (
            b"From: external@example.org\r\n"
            b"Authentication-Results: mail.relay.example.com;\r\n"
            b" spf=pass\r\n"
            b"Subject: Test\r\n"
            b"\r\n"
            b"Body\r\n"
        )

        result = remove_untrusted_authentication_results(raw, AUTHSERV_ID)

        assert result == (
            b"From: external@example.org\r\nSubject: Test\r\n\r\nBody\r\n"
        )

    def test_remove_untrusted_authentication_results__drops_leading_continuation(
        self,
    ):
        raw = (
            b" ; dmarc=pass header.from=evil.example\r\n"
            b"From: external@example.org\r\n"
            b"Subject: Test\r\n"
            b"\r\n"
            b"Body\r\n"
        )

        result = remove_untrusted_authentication_results(raw, AUTHSERV_ID)

        assert result == (
            b"From: external@example.org\r\nSubject: Test\r\n\r\nBody\r\n"
        )

    def test_remove_untrusted_authentication_results__leaves_body_untouched(self):
        raw = (
            b"From: external@example.org\r\n"
            b"\r\n"
            b"Authentication-Results: mail.relay.example.com; spf=pass\r\n"
            b" continued body line\r\n"
        )

        result = remove_untrusted_authentication_results(raw, AUTHSERV_ID)

        assert result == raw

    def test_remove_untrusted_authentication_results__leaves_other_headers(self):
        raw = (
            b"From: external@example.org\r\n"
            b"X-Custom: first\r\n"
            b" second\r\n"
            b"Subject: Test\r\n"
            b"\r\n"
            b"Body\r\n"
        )

        result = remove_untrusted_authentication_results(raw, AUTHSERV_ID)

        assert result == raw

    def test_remove_untrusted_authentication_results__keeps_body_of_message_without_separator(
        self,
    ):
        raw = (
            b"From: external@example.org\r\n"
            b"Just some body prose\r\n"
            b"Authentication-Results: mail.relay.example.com; spf=pass\r\n"
            b" continued body line\r\n"
        )

        result = remove_untrusted_authentication_results(raw, AUTHSERV_ID)

        assert result == raw

    def test_remove_untrusted_authentication_results__removes_own_authserv_id_without_separator(
        self,
    ):
        raw = (
            b"From: external@example.org\r\n"
            b"Authentication-Results: mail.relay.example.com; spf=pass\r\n"
            b"Just some body prose\r\n"
        )

        result = remove_untrusted_authentication_results(raw, AUTHSERV_ID)

        assert result == b"From: external@example.org\r\nJust some body prose\r\n"

    def test_remove_untrusted_authentication_results__removes_ar_after_unix_from(
        self,
    ):
        raw = (
            b"From nobody@example.com Mon Aug 31 00:00:00 2026\r\n"
            b"Authentication-Results: mail.relay.example.com; spf=pass\r\n"
            b"From: external@example.org\r\n"
            b"\r\n"
            b"Body\r\n"
        )

        result = remove_untrusted_authentication_results(raw, AUTHSERV_ID)

        assert result == (
            b"From nobody@example.com Mon Aug 31 00:00:00 2026\r\n"
            b"From: external@example.org\r\n"
            b"\r\n"
            b"Body\r\n"
        )

    def test_remove_untrusted_authentication_results__removes_ar_after_unix_from_between_headers(
        self,
    ):
        raw = (
            b"From: first@example.org\r\n"
            b"From nobody@example.com Mon Aug 31 00:00:00 2026\r\n"
            b"Authentication-Results: mail.relay.example.com; spf=pass\r\n"
            b"Subject: Test\r\n"
            b"\r\n"
            b"Body\r\n"
        )

        result = remove_untrusted_authentication_results(raw, AUTHSERV_ID)

        assert result == (
            b"From: first@example.org\r\n"
            b"From nobody@example.com Mon Aug 31 00:00:00 2026\r\n"
            b"Subject: Test\r\n"
            b"\r\n"
            b"Body\r\n"
        )


class TestVerifyArcChain:
    def test_verify_arc_chain__none_without_arc_headers(self):
        assert verify_arc_chain(make_raw_email()) == ChainResult.NONE

    def test_verify_arc_chain__fail_for_malformed_message(self):
        assert verify_arc_chain(b"garbage\r\n") == ChainResult.FAIL

    @pytest.mark.django_db
    def test_verify_arc_chain__pass_for_valid_chain(self, org, dns_resolver):
        domain = Domain.objects.create(name="example.com", org=org)
        register_dkim_record(dns_resolver, domain)

        sealed = seal_message(make_raw_email(), make_dmarc_evaluation(), domain)

        assert verify_arc_chain(sealed) == ChainResult.PASS

    @pytest.mark.django_db
    def test_verify_arc_chain__fail_for_tampered_seal(self, org, dns_resolver):
        domain = Domain.objects.create(name="example.com", org=org)
        register_dkim_record(dns_resolver, domain)
        sealed = seal_message(make_raw_email(), make_dmarc_evaluation(), domain)

        assert verify_arc_chain(tamper_arc_seal(sealed)) == ChainResult.FAIL

    @pytest.mark.django_db
    def test_verify_arc_chain__terminated_for_cv_fail_seal(self, org, dns_resolver):
        terminated = make_terminated_chain(org, dns_resolver)

        assert verify_arc_chain(terminated) == ChainResult.TERMINATED

    @pytest.mark.django_db
    def test_verify_arc_chain__fail_for_ams_without_space_after_colon(
        self, org, dns_resolver
    ):
        domain = Domain.objects.create(name="example.com", org=org)
        register_dkim_record(dns_resolver, domain)
        sealed = seal_message(make_raw_email(), make_dmarc_evaluation(), domain)
        crafted = strip_ams_header_space(sealed)

        with pytest.raises(IndexError):
            dkim.arc_verify(crafted, dnsfunc=fetch_dkim_key_record)

        assert verify_arc_chain(crafted) == ChainResult.FAIL

    def test_verify_arc_chain__fail_when_instance_exceeds_limit(
        self, dns_resolver, caplog
    ):
        crafted = make_garbage_seal_chain(ARC_INSTANCE_LIMIT + 1)

        with caplog.at_level(logging.WARNING):
            result = verify_arc_chain(crafted)

        assert result == ChainResult.FAIL
        assert "exceeds the limit" in caplog.text
        assert dns_resolver.lookups == []

    def test_verify_arc_chain__instance_at_limit_proceeds_to_verification(
        self, dns_resolver, caplog
    ):
        crafted = make_garbage_seal_chain(ARC_INSTANCE_LIMIT)

        with caplog.at_level(logging.WARNING):
            result = verify_arc_chain(crafted)

        assert result == ChainResult.FAIL
        assert "exceeds the limit" not in caplog.text

    @pytest.mark.django_db
    def test_verify_arc_chain__fail_for_unpublished_dkim_key_record(
        self, org, dns_resolver
    ):
        domain = Domain.objects.create(name="example.com", org=org)

        sealed = seal_message(make_raw_email(), make_dmarc_evaluation(), domain)

        assert verify_arc_chain(sealed) == ChainResult.FAIL

    @pytest.mark.django_db
    def test_verify_arc_chain__fail_for_non_dkim_key_record(self, org, dns_resolver):
        domain = Domain.objects.create(name="example.com", org=org)
        selector, _ = domain.dkim_ciphers[0]
        dns_resolver.add(f"{selector}._domainkey.{domain.name}", "TXT", '"v=spf1 -all"')

        sealed = seal_message(make_raw_email(), make_dmarc_evaluation(), domain)

        assert verify_arc_chain(sealed) == ChainResult.FAIL

    @pytest.mark.django_db
    def test_verify_arc_chain__fail_when_dns_budget_is_exhausted(
        self, org, dns_resolver, caplog
    ):
        domain = Domain.objects.create(name="example.com", org=org)
        register_dkim_record(dns_resolver, domain)
        sealed = seal_message(make_raw_email(), make_dmarc_evaluation(), domain)
        dns_resolver.lookups.clear()

        with caplog.at_level(logging.WARNING):
            result = verify_arc_chain(sealed, dns_budget=datetime.timedelta())

        assert result == ChainResult.FAIL
        assert dns_resolver.lookups == []
        assert "DNS budget" in caplog.text


class TestSealMessage:
    @pytest.mark.django_db
    def test_seal_message__fresh_message_seals_first_instance(self, org, dns_resolver):
        domain = Domain.objects.create(name="example.com", org=org)
        register_dkim_record(dns_resolver, domain)

        sealed = seal_message(make_raw_email(), make_dmarc_evaluation(), domain)

        seals = parse_arc_seals(sealed)
        assert len(seals) == 1
        assert seals[0]["i"] == "1"
        assert seals[0]["cv"] == "none"
        assert seals[0]["d"] == "example.com"
        assert seals[0]["s"] == "relay-rsa2048"
        assert dkim.arc_verify(sealed)[0] == dkim.CV_Pass

    @pytest.mark.django_db
    def test_seal_message__forwarded_message_continues_chain(self, org, dns_resolver):
        forwarder = Domain.objects.create(name="forwarder.example", org=org)
        receiver = Domain.objects.create(name="example.com", org=org)
        register_dkim_record(dns_resolver, forwarder)
        register_dkim_record(dns_resolver, receiver)
        forwarded = seal_message(make_raw_email(), make_dmarc_evaluation(), forwarder)

        sealed = seal_message(forwarded, make_dmarc_evaluation(), receiver)

        seals = parse_arc_seals(sealed)
        assert len(seals) == 2
        assert seals[0]["i"] == "2"
        assert seals[0]["cv"] == "pass"
        assert seals[0]["d"] == "example.com"
        assert dkim.arc_verify(sealed)[0] == dkim.CV_Pass

    @pytest.mark.django_db
    def test_seal_message__broken_chain_seals_next_instance_with_cv_fail(
        self, org, dns_resolver
    ):
        forwarder = Domain.objects.create(name="example.com", org=org)
        receiver = Domain.objects.create(name="forwarder.example", org=org)
        register_dkim_record(dns_resolver, forwarder)
        register_dkim_record(dns_resolver, receiver)
        sealed = seal_message(make_raw_email(), make_dmarc_evaluation(), forwarder)
        tampered = tamper_arc_seal(sealed)

        assert dkim.arc_verify(tampered)[0] == dkim.CV_Fail

        resealed = seal_message(tampered, make_dmarc_evaluation(), receiver)

        seals = parse_arc_seals(resealed)
        assert len(seals) == 2
        assert seals[0]["i"] == "2"
        assert seals[0]["cv"] == "fail"
        assert seals[0]["d"] == "forwarder.example"
        assert verify_arc_chain(resealed) == ChainResult.TERMINATED

    @pytest.mark.django_db
    def test_seal_message__terminated_chain_prepends_arc_fail_without_new_seal(
        self, org, dns_resolver
    ):
        terminated = make_terminated_chain(org, dns_resolver)
        receiver = Domain.objects.create(name="outbound.example", org=org)
        register_dkim_record(dns_resolver, receiver)

        sealed = seal_message(terminated, make_dmarc_evaluation(), receiver)

        assert sealed.startswith(
            b"Authentication-Results: mail.relay.outbound.example; arc=fail"
        )
        seals = parse_arc_seals(sealed)
        assert len(seals) == 2
        assert seals[0]["i"] == "2"
        assert seals[0]["cv"] == "fail"
        assert verify_arc_chain(sealed) == ChainResult.TERMINATED

    @pytest.mark.django_db
    def test_seal_message__removes_forged_authentication_results(self, org):
        domain = Domain.objects.create(name="example.com", org=org)
        raw = (
            b"From: external@example.org\r\n"
            b"Authentication-Results: mail.relay.example.com; spf=pass\r\n"
            b"Subject: Test\r\n"
            b"\r\n"
            b"Something happened\r\n"
        )
        evaluation = make_dmarc_evaluation(spf_result=AuthResult.FAIL)

        sealed = seal_message(raw, evaluation, domain)

        aar = email.message_from_bytes(sealed).get("ARC-Authentication-Results")
        assert aar.startswith("i=1; mail.relay.example.com;")
        assert aar.count("spf=") == 1
        assert "spf=pass" not in aar
        assert b"Authentication-Results: mail.relay.example.com; spf=pass" not in sealed

    @pytest.mark.django_db
    def test_seal_message__removes_forged_ar_after_unix_from(self, org, dns_resolver):
        domain = Domain.objects.create(name="example.com", org=org)
        register_dkim_record(dns_resolver, domain)
        raw = (
            b"From nobody@example.com Mon Aug 31 00:00:00 2026\r\n"
            b"Authentication-Results: mail.relay.example.com; spf=pass\r\n"
            b"From: external@example.org\r\n"
            b"Subject: Test\r\n"
            b"\r\n"
            b"Something happened\r\n"
        )
        evaluation = make_dmarc_evaluation(spf_result=AuthResult.FAIL)

        sealed = seal_message(raw, evaluation, domain)

        aar = email.message_from_bytes(sealed).get("ARC-Authentication-Results")
        assert aar.startswith("i=1; mail.relay.example.com;")
        assert aar.count("spf=") == 1
        assert "spf=pass" not in aar
        assert b"From nobody@example.com" in sealed
        assert verify_arc_chain(sealed) == ChainResult.PASS

    @pytest.mark.django_db
    def test_seal_message__folded_from_header_cannot_inject_ar_clauses(
        self, org, dns_resolver
    ):
        domain = Domain.objects.create(name="example.com", org=org)
        register_dkim_record(dns_resolver, domain)
        raw = (
            b"From: no-reply\r\n"
            b" ; spf=pass smtp.mailfrom=trusted-bank.example;"
            b" dkim=pass (2048-bit) header.d=trusted-bank.example\r\n"
            b"To: postmaster@example.com\r\n"
            b"Subject: Test\r\n"
            b"\r\n"
            b"Something happened\r\n"
        )
        evaluation = DmarcEvaluation.from_bytes(raw, "external@example.org")

        sealed = seal_message(raw, evaluation, domain)

        aar = email.message_from_bytes(sealed).get("ARC-Authentication-Results")
        assert aar.count("spf=") == 1
        assert aar.count("dkim=") == 1
        assert "header.from=" not in aar
        assert "spf=pass" not in aar
        assert "dkim=pass" not in aar
        assert "trusted-bank.example" not in aar
        assert verify_arc_chain(sealed) == ChainResult.PASS

    @pytest.mark.django_db
    def test_seal_message__folded_dkim_domain_cannot_inject_ar_clauses(
        self, org, dns_resolver
    ):
        domain = Domain.objects.create(name="example.com", org=org)
        register_dkim_record(dns_resolver, domain)
        attacker_key = SigningKey.generate(SigningKey.Algorithm.RSA_2048)
        folded_domain = b"evil.example\r\n spf=pass smtp.mailfrom=trusted-bank.example"
        register_dkim_key_record(
            dns_resolver, "attacker-sel", folded_domain.decode(), attacker_key
        )
        privkey, _ = keys.dkim_key_material(
            attacker_key.encrypted_private_key, attacker_key.algorithm
        )
        raw = (
            dkim.sign(make_raw_email(), b"attacker-sel", folded_domain, privkey)
            + make_raw_email()
        )
        evaluation = DmarcEvaluation.from_bytes(raw, "external@example.org")

        sealed = seal_message(raw, evaluation, domain)

        aar = email.message_from_bytes(sealed).get("ARC-Authentication-Results")
        assert "dkim=pass" in aar
        assert "header.d=" not in aar
        assert aar.count("spf=") == 1
        assert "trusted-bank.example" not in aar
        assert verify_arc_chain(sealed) == ChainResult.PASS

    @pytest.mark.django_db
    def test_seal_message__leading_continuation_cannot_inject_ar_clauses(
        self, org, dns_resolver
    ):
        domain = Domain.objects.create(name="example.com", org=org)
        register_dkim_record(dns_resolver, domain)
        raw = (
            b" ; dmarc=pass header.from=evil.example;"
            b" spf=pass smtp.mailfrom=evil.example\r\n"
        ) + make_garbage_seal_chain(1)
        evaluation = make_dmarc_evaluation(
            spf_result=AuthResult.FAIL, dkim_result=AuthResult.FAIL
        )

        sealed = seal_message(raw, evaluation, domain)

        msg = email.message_from_bytes(sealed)
        aar = msg.get("ARC-Authentication-Results")
        ar = msg.get("Authentication-Results")
        assert parse_ar_clauses(aar) == [
            ("arc", "fail"),
            ("spf", "fail"),
            ("dkim", "fail"),
            ("dmarc", "fail"),
        ]
        assert parse_ar_clauses(ar) == parse_ar_clauses(aar)
        assert b"evil.example" not in sealed
        seals = parse_arc_seals(sealed)
        assert len(seals) == 2
        assert seals[0]["i"] == "2"
        assert seals[0]["cv"] == "fail"

    @pytest.mark.django_db
    def test_seal_message__seals_message_with_leading_continuation(
        self, org, dns_resolver
    ):
        domain = Domain.objects.create(name="example.com", org=org)
        register_dkim_record(dns_resolver, domain)
        raw = b" ; spf=pass smtp.mailfrom=evil.example\r\n" + make_raw_email()

        sealed = seal_message(raw, make_dmarc_evaluation(), domain)

        seals = parse_arc_seals(sealed)
        assert len(seals) == 1
        assert seals[0]["i"] == "1"
        assert seals[0]["cv"] == "none"
        assert verify_arc_chain(sealed) == ChainResult.PASS
        assert b"evil.example" not in sealed
        assert b"From: external@example.org" in sealed
        assert b"Something happened" in sealed

    @pytest.mark.django_db
    def test_seal_message__spoofed_spf_fail_mail_seals_dmarc_fail(
        self, org, dns_resolver
    ):
        domain = Domain.objects.create(name="example.com", org=org)
        register_dkim_record(dns_resolver, domain)
        dns_resolver.add("victim.com", "TXT", '"v=spf1 -all"')
        dns_resolver.add("_dmarc.victim.com", "TXT", '"v=DMARC1; p=reject"')
        raw = (
            b"Received: from mx.attacker.example (mx.attacker.example [192.0.2.1])\r\n"
            b" by mail.relay.example.com with ESMTP\r\n"
            b"From: ceo@victim.com\r\n"
            b"To: postmaster@example.com\r\n"
            b"Subject: Test\r\n"
            b"\r\n"
            b"Something happened\r\n"
        )
        evaluation = DmarcEvaluation.from_bytes(raw, "ceo@victim.com")

        sealed = seal_message(raw, evaluation, domain)

        aar = email.message_from_bytes(sealed).get("ARC-Authentication-Results")
        assert "spf=fail smtp.mailfrom=victim.com" in aar
        assert "dmarc=fail" in aar
        assert "dmarc=pass" not in aar
        assert verify_arc_chain(sealed) == ChainResult.PASS

    def test_seal_message__keeps_body_of_message_without_separator(self):
        domain = Domain(name="example.com")
        raw = (
            b"From: external@example.org\r\n"
            b"Just some body prose\r\n"
            b"Authentication-Results: mail.relay.example.com; spf=pass\r\n"
            b" continued body line\r\n"
        )

        sealed = seal_message(raw, make_dmarc_evaluation(), domain)

        assert sealed.startswith(b"Authentication-Results: mail.relay.example.com")
        assert sealed.endswith(raw)

    def test_seal_message__missing_rsa2048_key_skips_arc_set(self):
        domain = Domain(name="example.com")
        raw = make_raw_email()

        sealed = seal_message(raw, make_dmarc_evaluation(), domain)

        assert sealed.startswith(
            b"Authentication-Results: mail.relay.example.com; arc=none"
        )
        assert b"ARC-" not in sealed
        assert sealed.endswith(raw)

    @pytest.mark.django_db
    def test_seal_message__unsignable_message_skips_arc_set(self, org):
        domain = Domain.objects.create(name="example.com", org=org)
        raw = b"From: external@example.org\r\nBad Header: value\r\n\r\nBody\r\n"

        sealed = seal_message(raw, make_dmarc_evaluation(), domain)

        assert sealed.startswith(b"Authentication-Results: mail.relay.example.com")
        assert b"ARC-" not in sealed
        assert sealed.endswith(raw)

    @pytest.mark.django_db
    def test_seal_message__instance_at_limit_skips_arc_set(
        self, org, dns_resolver, caplog
    ):
        domain = Domain.objects.create(name="example.com", org=org)
        crafted = make_garbage_seal_chain(ARC_INSTANCE_LIMIT)

        with caplog.at_level(logging.WARNING):
            sealed = seal_message(crafted, make_dmarc_evaluation(), domain)

        assert sealed.startswith(
            b"Authentication-Results: mail.relay.example.com; arc=fail"
        )
        assert len(parse_arc_seals(sealed)) == ARC_INSTANCE_LIMIT
        assert b"ARC-Authentication-Results" not in sealed
        assert b"ARC-Message-Signature" not in sealed
        assert sealed.endswith(crafted)
        assert "Skipping ARC seal for example.com" in caplog.text

    @pytest.mark.django_db
    def test_seal_message__removes_non_utf8_ar_header(self, org):
        domain = Domain.objects.create(name="example.com", org=org)
        raw = (
            b"From: external@example.org\r\n"
            b"Authentication-Results: mx.other.example; spf=\xffpass\r\n"
            b"\r\n"
            b"Something happened\r\n"
        )

        sealed = seal_message(raw, make_dmarc_evaluation(), domain)

        assert b"Authentication-Results: mail.relay.example.com" in sealed
        assert b"ARC-Authentication-Results" in sealed
        assert b"spf=\xffpass" not in sealed

    @pytest.mark.django_db
    def test_seal_message__removes_versioned_ar_header(self, org, dns_resolver):
        domain = Domain.objects.create(name="example.com", org=org)
        register_dkim_record(dns_resolver, domain)
        raw = (
            b"From: external@example.org\r\n"
            b"Authentication-Results: some.domain 2; spf=pass\r\n"
            b"Subject: Test\r\n"
            b"\r\n"
            b"Something happened\r\n"
        )

        sealed = seal_message(raw, make_dmarc_evaluation(), domain)

        assert b"Authentication-Results: some.domain 2; spf=pass" not in sealed
        assert b"ARC-Authentication-Results" in sealed
        assert verify_arc_chain(sealed) == ChainResult.PASS
