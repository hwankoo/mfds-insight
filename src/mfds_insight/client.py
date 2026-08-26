"""공공데이터포털 오픈API 클라이언트.

보안 원칙
  - API 키는 Settings 에서만 조달하며, 로그/예외에 절대 원문으로 남기지 않는다.
  - TLS 검증 강제, 타임아웃 필수, 리다이렉트로 호스트가 바뀌면 차단.
  - 요청 속도 제한(QPS)과 지수 백오프로 기관 API에 부담을 주지 않는다.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Iterator
from urllib.parse import urlsplit

import requests

from .config import Settings

log = logging.getLogger(__name__)

_RETRY_STATUS = {429, 500, 502, 503, 504}

# 공공데이터포털 공통 오류코드 → 사람이 읽을 수 있는 원인·조치
_PORTAL_ERRORS = {
    "1":  "적용 불가 인증키. 마이페이지에서 키를 다시 확인하십시오.",
    "4":  "요청 제한 횟수 초과(HTTP_ERROR).",
    "12": "해당 오픈API 서비스가 없거나 폐기됨 — base_url/endpoint 가 잘못되었습니다. "
          "포털 마이페이지 > 활용신청 상세의 '요청주소'를 그대로 복사해 넣으십시오.",
    "20": "서비스 접근 거부. 활용신청이 승인되었는지 확인하십시오.",
    "22": "일일 트래픽 한도 초과.",
    "30": "등록되지 않은 서비스키. 활용신청 승인 후 최대 1시간 소요될 수 있습니다.",
    "31": "활용기간 만료. 연장 신청이 필요합니다.",
    "32": "등록되지 않은 IP.",
    "99": "기타 오류.",
}


def _explain_portal_error(text: str) -> str | None:
    """포털 오류 본문(JSON/XML)에서 코드와 메시지를 뽑아 사람이 읽을 안내로 바꾼다."""
    import re as _re

    def _field(name: str) -> str | None:
        # JSON:  "errMsg" : "값"      /  XML:  <errMsg>값</errMsg>
        m = _re.search(rf'"{name}"\s*:\s*"([^"]*)"', text)
        if m:
            return m.group(1).strip()
        m = _re.search(rf"<{name}>([^<]*)</{name}>", text)
        return m.group(1).strip() if m else None

    code = _field("returnReasonCode")
    msg = _field("errMsg") or _field("returnAuthMsg")
    if not code and not msg:
        return None

    parts = []
    if msg:
        parts.append(msg)
    if code:
        parts.append(f"[코드 {code}] " + _PORTAL_ERRORS.get(code, "포털 오류코드 표를 확인하십시오."))
    return " / ".join(parts)


class ApiError(RuntimeError):
    pass


def _unwrap(rec: Any, key: str) -> Any:
    """{"item": {...}} 처럼 한 겹 감싸인 레코드를 벗겨낸다."""
    if not isinstance(rec, dict) or not key:
        return rec
    if key == "auto":
        if len(rec) == 1:
            only = next(iter(rec.values()))
            return only if isinstance(only, dict) else rec
        return rec
    inner = rec.get(key)
    return inner if isinstance(inner, dict) else rec


def _dig(obj: Any, path: list[str]) -> Any:
    for key in path:
        if isinstance(obj, dict):
            obj = obj.get(key)
        else:
            return None
    return obj


class MfdsClient:
    def __init__(self, settings: Settings) -> None:
        self.s = settings
        self.api = settings.api
        self._host = urlsplit(self.api["base_url"]).netloc
        self._min_interval = 1.0 / float(self.api.get("rate_limit_qps", 2.0) or 2.0)
        self._last_call = 0.0

        self._session = requests.Session()
        self._session.headers.update(
            {"Accept": "application/json", "User-Agent": "mfds-insight/1.0 (+regulatory research)"}
        )

    # ---------------------------------------------------------------
    def close(self) -> None:
        self._session.close()

    def __enter__(self) -> "MfdsClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ---------------------------------------------------------------
    def _throttle(self) -> None:
        gap = time.monotonic() - self._last_call
        if gap < self._min_interval:
            time.sleep(self._min_interval - gap)
        self._last_call = time.monotonic()

    def full_url(self) -> str:
        """실제 호출에 쓰이는 URL(키 제외). 진단용."""
        return self.api["base_url"].rstrip("/") + self.api["endpoint"]

    def _request(self, params: dict[str, Any]) -> dict:
        url = self.full_url()
        log.debug("요청 URL: %s  params=%s", url, {k: v for k, v in params.items()})
        secure = dict(params)
        secure["serviceKey"] = self.s.api_key  # 키는 여기서만 주입

        last_err: Exception | None = None
        for attempt in range(1, int(self.api.get("max_retries", 4)) + 1):
            self._throttle()
            try:
                resp = self._session.get(
                    url,
                    params=secure,
                    timeout=float(self.api.get("timeout_sec", 20)),
                    verify=True,          # TLS 검증 비활성화 금지
                    allow_redirects=False # 리다이렉트 자동 추종 금지
                )
                if resp.status_code in (301, 302, 307, 308):
                    target = urlsplit(resp.headers.get("Location", "")).netloc
                    raise ApiError(f"예상치 못한 리다이렉트(대상 호스트: {target or '불명'}). 중단합니다.")
                if resp.status_code in _RETRY_STATUS:
                    raise ApiError(f"일시적 오류 HTTP {resp.status_code}")
                if resp.status_code != 200:
                    hint = _explain_portal_error(resp.text)
                    if hint:
                        raise ApiError(f"HTTP {resp.status_code} — {hint}")
                    raise ApiError(f"HTTP {resp.status_code}: {resp.text[:200]}")
                hint = _explain_portal_error(resp.text[:600])
                if hint and "OpenAPI_ServiceResponse" in resp.text[:600]:
                    raise ApiError(hint)   # 200 으로 오는 오류 응답
                try:
                    return resp.json()
                except json.JSONDecodeError:
                    raise ApiError(
                        "JSON 파싱 실패. 인증키 미승인 또는 XML 오류응답일 수 있습니다. "
                        f"응답 앞부분: {resp.text[:200]}"
                    )
            except ApiError as exc:
                if "코드" in str(exc) or "OpenAPI" in str(exc):
                    raise                       # 설정/권한 문제 — 재시도 무의미
                last_err = exc
                wait = float(self.api.get("backoff_base", 1.5)) ** attempt
                log.warning("요청 실패 (%d/%s): %s — %.1f초 후 재시도", attempt,
                            self.api.get("max_retries", 4), self.s.mask(str(exc)), wait)
                if attempt < int(self.api.get("max_retries", 4)):
                    time.sleep(wait)
                continue
            except requests.RequestException as exc:
                last_err = exc
                wait = float(self.api.get("backoff_base", 1.5)) ** attempt
                log.warning(
                    "요청 실패 (%d/%s): %s — %.1f초 후 재시도",
                    attempt, self.api.get("max_retries", 4),
                    self.s.mask(str(exc)), wait,
                )
                if attempt < int(self.api.get("max_retries", 4)):
                    time.sleep(wait)

        raise ApiError(self.s.mask(f"재시도 소진: {last_err}"))

    # ---------------------------------------------------------------
    def probe(self) -> dict:
        """응답 구조 1페이지를 그대로 돌려준다. 필드 매핑을 잡을 때 사용."""
        log.info("호출 대상: %s", self.full_url())
        params = {
            self.api["page_param"]: 1,
            self.api["size_param"]: 3,
            self.api["type_param"]: self.api.get("response_format", "json"),
        }
        return self._request(params)

    def iter_records(self, extra: dict[str, Any] | None = None) -> Iterator[dict]:
        """전 페이지를 순회하며 원본 레코드를 하나씩 내보낸다."""
        page_size = int(self.api.get("page_size", 100))
        max_pages = int(self.api.get("max_pages", 200))
        total: int | None = None
        seen = 0

        for page in range(1, max_pages + 1):
            params = {
                self.api["page_param"]: page,
                self.api["size_param"]: page_size,
                self.api["type_param"]: self.api.get("response_format", "json"),
            }
            if extra:
                params.update(extra)

            payload = self._request(params)

            if total is None:
                raw_total = _dig(payload, list(self.api.get("total_path", [])))
                try:
                    total = int(raw_total) if raw_total is not None else None
                except (TypeError, ValueError):
                    total = None
                log.info("총 레코드 수: %s", total if total is not None else "불명")

            records = _dig(payload, list(self.api.get("records_path", []))) or []
            if isinstance(records, dict):       # 단건 응답 방어
                records = [records]
            if not records:
                log.info("페이지 %d 에서 레코드 없음 — 수집 종료", page)
                break

            for rec in records:
                rec = _unwrap(rec, self.api.get("unwrap_key", "auto"))
                if isinstance(rec, dict):
                    seen += 1
                    yield rec

            log.info("페이지 %d 수집 (누적 %d건)", page, seen)

            if total is not None and seen >= total:
                break
            if len(records) < page_size:
                break
        else:
            log.warning("max_pages(%d) 상한에 도달했습니다. 설정을 확인하십시오.", max_pages)
