from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from services.email.spam import (
    ScannerUnavailableError,
    SpamAction,
    SpamResult,
    check_message,
)


class TestCheckMessage:
    async def test_check_message__raises_scanner_unavailable_for_soft_reject(self):
        data = {"score": 0.0, "action": "soft reject"}
        response = Mock(json=Mock(return_value=data))
        client = MagicMock(post=AsyncMock(return_value=response))
        client.__aenter__.return_value = client
        with (
            patch("services.email.spam.client.httpx.AsyncClient", return_value=client),
            pytest.raises(ScannerUnavailableError),
        ):
            await check_message(b"raw message", client_ip="")

    async def test_check_message__returns_result(self):
        data = {"score": 0.0, "action": "no action"}
        response = Mock(json=Mock(return_value=data))
        client = MagicMock(post=AsyncMock(return_value=response))
        client.__aenter__.return_value = client
        with patch("services.email.spam.client.httpx.AsyncClient", return_value=client):
            result = await check_message(b"raw message", client_ip="")

        assert result == SpamResult(score=0.0, action=SpamAction.NO_ACTION)
