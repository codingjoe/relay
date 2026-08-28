from services.email.mta.mta_sts import MtaStsPolicy


class TestMtaStsPolicyAllows:
    def test_allows__returns_true_when_not_loaded(self):
        policy = MtaStsPolicy()
        allowed, _reason = policy.allows("mail.example.com")
        assert allowed is True

    def test_allows__returns_true_when_mx_matches_pattern(self):
        policy = MtaStsPolicy(
            mode="enforce", mx_patterns=["*.example.com"], loaded=True
        )
        allowed, _reason = policy.allows("mail.example.com")
        assert allowed is True

    def test_allows__returns_false_when_enforce_and_no_match(self):
        policy = MtaStsPolicy(mode="enforce", mx_patterns=["*.good.com"], loaded=True)
        allowed, reason = policy.allows("mail.evil.com")
        assert allowed is False
        assert "enforce" in reason

    def test_allows__returns_true_when_testing_and_no_match(self):
        policy = MtaStsPolicy(mode="testing", mx_patterns=["*.good.com"], loaded=True)
        allowed, reason = policy.allows("mail.evil.com")
        assert allowed is True
        assert "testing" in reason

    def test_allows__returns_true_when_mode_none(self):
        policy = MtaStsPolicy(mode="none", mx_patterns=[], loaded=True)
        allowed, _reason = policy.allows("mail.anything.com")
        assert allowed is True
