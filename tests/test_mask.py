"""결함 1: 인코딩된 API 키가 로그·예외에 마스킹되지 않던 문제."""
from __future__ import annotations

from urllib.parse import quote, quote_plus

import pytest

from conftest import FAKE_KEY
from mfds_insight.client import ApiError, MfdsClient


@pytest.mark.parametrize("form", [
    FAKE_KEY,                       # 원문(Decoding 형태)
    quote_plus(FAKE_KEY),           # requests 가 쿼리스트링에 쓰는 형태
    quote(FAKE_KEY, safe=""),
    quote_plus(FAKE_KEY).lower(),   # %2b 처럼 소문자 퍼센트 인코딩
])
def test_mask_covers_all_encodings(settings, form):
    out = settings.mask(f"url?serviceKey={form}&pageNo=1")
    assert "***REDACTED***" in out
    assert "ab" not in out.split("serviceKey=")[1].split("&")[0]


def test_mask_without_key_is_noop(settings):
    from dataclasses import replace
    s = replace(settings, _api_key="")
    assert s.mask("plain text") == "plain text"


def test_connection_error_does_not_leak_key(settings):
    """실제 연결 실패(포트 9 거부)로 requests 예외 메시지를 만들어 확인한다."""
    from dataclasses import replace
    s = replace(settings, api=dict(settings.api, base_url="https://127.0.0.1:9",
                                   endpoint="/getX", max_retries=1, timeout_sec=2))
    with pytest.raises(ApiError) as ei:
        MfdsClient(s)._request({"pageNo": 1})
    msg = str(ei.value)
    assert quote_plus(FAKE_KEY) not in msg
    assert FAKE_KEY not in msg
    assert "***REDACTED***" in msg
    # 원 예외 체인을 끊어 트레이스백으로도 새지 않아야 한다.
    assert ei.value.__cause__ is None and ei.value.__suppress_context__
