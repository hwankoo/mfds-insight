"""공통 픽스처. 실제 API·네트워크 없이 동작한다."""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mfds_insight import config as cfgmod  # noqa: E402

# 인코딩하면 형태가 달라지는 문자(+ / =)를 일부러 포함한 가짜 키
FAKE_KEY = "ab+cd/ef=="


@pytest.fixture
def settings(tmp_path, monkeypatch):
    """저장소 settings.toml 기반 + 임시 루트(cache/output 격리) + 빠른 재시도."""
    for var in ("MFDS_API_KEY", "MFDS_BASE_URL", "MFDS_ENDPOINT"):
        monkeypatch.delenv(var, raising=False)
    s = cfgmod.load(ROOT)
    (tmp_path / "templates").symlink_to(ROOT / "templates")
    (tmp_path / "static").symlink_to(ROOT / "static")
    api = dict(s.api, backoff_base=0.0, rate_limit_qps=1000.0, max_retries=3)
    return replace(s, root=tmp_path, api=api, _api_key=FAKE_KEY)


class FakeResponse:
    def __init__(self, payload=None, status=200, text=None, headers=None):
        import json as _json
        self.status_code = status
        self._payload = payload
        self.text = text if text is not None else _json.dumps(payload, ensure_ascii=False)
        self.headers = headers or {}

    def json(self):
        import json as _json
        return _json.loads(self.text)


def page(items, total=None, code="00"):
    """MFDS 형식 응답 본문."""
    body = {"items": [{"item": it} for it in items]}
    if total is not None:
        body["totalCount"] = total
    return {"header": {"resultCode": code, "resultMsg": "NORMAL SERVICE"}, "body": body}


def rec(i, name="치과용임플란트고정체", date="20200101"):
    return {"PRDUCT": name, "ENTRPS": f"업체{i % 7}", "PRDUCT_PRMISN_NO": f"제허 {i:05d} 호",
            "PRMISN_DT": date, "RTRCN_DSCTN_DIVS_CD": ""}
