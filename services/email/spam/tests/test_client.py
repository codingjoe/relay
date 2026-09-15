from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from services.email.spam.client import (
    ScannerUnavailableError,
    SpamAction,
    SpamResult,
    check_message,
)


class TestCheckMessage:
    async def test_check_message__raises_scanner_unavailable_for_failure_symbol(self):
        data = {
            "score": 0.0,
            "action": "soft reject",
            "symbols": {"CLAM_VIRUS_FAIL": {"score": 0.0, "options": []}},
        }
        response = Mock(json=Mock(return_value=data))
        client = MagicMock(post=AsyncMock(return_value=response))
        client.__aenter__.return_value = client
        with (
            patch("services.email.spam.client.httpx.AsyncClient", return_value=client),
            pytest.raises(ScannerUnavailableError),
        ):
            await check_message(b"raw message", client_ip="")

    async def test_check_message__raises_scanner_unavailable_for_failure_symbol_with_reject_action(
        self,
    ):
        data = {
            "score": 15.0,
            "action": "reject",
            "symbols": {"CLAM_VIRUS_FAIL": {"score": 0.0, "options": []}},
        }
        response = Mock(json=Mock(return_value=data))
        client = MagicMock(post=AsyncMock(return_value=response))
        client.__aenter__.return_value = client
        with (
            patch("services.email.spam.client.httpx.AsyncClient", return_value=client),
            pytest.raises(ScannerUnavailableError),
        ):
            await check_message(b"raw message", client_ip="")

    async def test_check_message__returns_soft_reject_for_greylisted_message(self):
        data = {
            "score": 0.0,
            "action": "soft reject",
            "symbols": {"GREYLIST": {"score": 0.0, "options": []}},
        }
        response = Mock(json=Mock(return_value=data))
        client = MagicMock(post=AsyncMock(return_value=response))
        client.__aenter__.return_value = client
        with patch("services.email.spam.client.httpx.AsyncClient", return_value=client):
            result = await check_message(b"raw message", client_ip="")

        assert result == SpamResult(score=0.0, action=SpamAction.SOFT_REJECT)

    async def test_check_message__returns_result(self):
        data = {
            "score": 0.0,
            "action": "no action",
            "symbols": {
                "SPF_ALLOW": {"score": 0.0, "options": []},
                "DKIM_TRACE": {"score": 0.0, "options": []},
            },
        }
        response = Mock(json=Mock(return_value=data))
        client = MagicMock(post=AsyncMock(return_value=response))
        client.__aenter__.return_value = client
        with patch("services.email.spam.client.httpx.AsyncClient", return_value=client):
            result = await check_message(b"raw message", client_ip="")

        assert result == SpamResult(score=0.0, action=SpamAction.NO_ACTION)

    async def test_check_message__sends_client_ip_as_ip_header(self):
        data = {
            "score": 0.0,
            "action": "no action",
            "symbols": {"SPF_ALLOW": {"score": 0.0, "options": []}},
        }
        response = Mock(json=Mock(return_value=data))
        client = MagicMock(post=AsyncMock(return_value=response))
        client.__aenter__.return_value = client
        with patch("services.email.spam.client.httpx.AsyncClient", return_value=client):
            await check_message(b"raw message", client_ip="203.0.113.7")

        assert client.post.call_args.kwargs["headers"]["Ip"] == "203.0.113.7"
