"""결함 4: 불완전한 수집 결과가 게시되던 문제."""
from __future__ import annotations

import json

import pytest

from conftest import FakeResponse, page, rec
from mfds_insight import cli
from mfds_insight.client import FatalApiError, MfdsClient


def make_server(pages_by_no, statuses=None):
    """pageNo → 응답 본문. statuses 에 (pageNo, 시도번호) → HTTP 코드를 주면 그 응답을 낸다."""
    calls = []

    def fake_get(self, url, params=None, **kw):
        no = int(params["pageNo"])
        calls.append(no)
        attempt = calls.count(no)
        st = (statuses or {}).get((no, attempt))
        if st:
            return FakeResponse(status=st, text="err")
        return FakeResponse(pages_by_no.get(no, page([], total=None, code="03")))
    return fake_get, calls


def capped_pages(total, cap):
    """포털이 numOfRows 를 cap 으로 제한하는 상황을 흉내 낸다."""
    out, n = {}, 1
    for start in range(0, total, cap):
        out[n] = page([rec(i) for i in range(start, min(start + cap, total))], total=total)
        n += 1
    return out


def collect(settings, monkeypatch, pages_by_no, statuses=None, **api):
    from dataclasses import replace
    s = replace(settings, api=dict(settings.api, **api))
    fake_get, calls = make_server(pages_by_no, statuses)
    monkeypatch.setattr("requests.Session.get", fake_get)
    with MfdsClient(s) as c:
        got = list(c.iter_records())
        return got, c.last_run, calls


# ── 페이징 종료 조건 ───────────────────────────────────
def test_short_page_does_not_stop_when_total_known(settings, monkeypatch):
    got, run, _ = collect(settings, monkeypatch, capped_pages(250, 100), page_size=500)
    assert len(got) == 250
    assert run["complete"] and run["stop_reason"] == "total_reached"


def test_short_page_stops_when_total_unknown(settings, monkeypatch):
    pages = {1: page([rec(i) for i in range(30)])}
    got, run, calls = collect(settings, monkeypatch, pages, page_size=100,
                              total_path=["body", "없음"])
    assert len(got) == 30 and calls == [1]
    assert run["complete"] and run["total_count"] is None


def test_max_pages_marks_incomplete(settings, monkeypatch):
    got, run, _ = collect(settings, monkeypatch, capped_pages(500, 100),
                          page_size=100, max_pages=2)
    assert len(got) == 200
    assert not run["complete"] and run["stop_reason"] == "max_pages"


def test_nodata_code_ends_collection(settings, monkeypatch):
    # totalCount 가 실제보다 크게 오면 NODATA 로 끝나고 불완전으로 표시돼야 한다.
    pages = {1: page([rec(i) for i in range(100)], total=150)}
    got, run, _ = collect(settings, monkeypatch, pages, page_size=100)
    assert len(got) == 100 and not run["complete"]


# ── resultCode / 재시도 ────────────────────────────────
def test_error_result_code_is_fatal_without_retry(settings, monkeypatch):
    pages = {1: page([], total=0, code="30")}
    with pytest.raises(FatalApiError, match="resultCode 30"):
        collect(settings, monkeypatch, pages)


def test_fatal_http_error_is_not_retried(settings, monkeypatch):
    fake_get, calls = make_server({}, {(1, 1): 404, (1, 2): 404, (1, 3): 404})
    monkeypatch.setattr("requests.Session.get", fake_get)
    with pytest.raises(FatalApiError):
        MfdsClient(settings)._request({"pageNo": 1})
    assert calls == [1]


def test_redirect_is_fatal(settings, monkeypatch):
    monkeypatch.setattr("requests.Session.get", lambda self, url, **kw: FakeResponse(
        status=302, text="", headers={"Location": "https://evil.example/x"}))
    with pytest.raises(FatalApiError, match="evil.example"):
        MfdsClient(settings)._request({"pageNo": 1})


def test_transient_error_is_retried(settings, monkeypatch):
    pages = {1: page([rec(1)], total=1)}
    got, run, calls = collect(settings, monkeypatch, pages, statuses={(1, 1): 503})
    assert len(got) == 1 and calls == [1, 1] and run["complete"]


# ── 게시 전 무결성 게이트 ──────────────────────────────
def test_check_completeness_rules(settings):
    ok = {"total_count": 100, "fetched": 100, "stop_reason": "total_reached", "complete": True}
    assert cli.check_completeness(ok, {}, settings) == []
    short = dict(ok, fetched=90, complete=False)
    assert "10건 누락" in cli.check_completeness(short, {}, settings)[0]
    # 직전 대비 5% 초과 감소
    assert any("감소" in m for m in cli.check_completeness(ok, {"fetched": 200}, settings))
    # 허용 범위 이내 감소는 통과
    assert cli.check_completeness(ok, {"fetched": 104}, settings) == []
    # 직전이 시험 수집이면 비교하지 않는다
    assert cli.check_completeness(ok, {"fetched": 200, "sample": True}, settings) == []


def _fake_fetch(monkeypatch, pages_by_no):
    fake_get, _ = make_server(pages_by_no)
    monkeypatch.setattr("requests.Session.get", fake_get)


def test_incomplete_fetch_keeps_previous_cache(settings, monkeypatch):
    _fake_fetch(monkeypatch, capped_pages(50, 50))
    assert cli._fetch(settings) == "raw"
    before = (settings.cache_dir / "raw.meta.json").read_text(encoding="utf-8")

    # 두 번째 수집은 totalCount 50 중 20건만 오고 끊김
    _fake_fetch(monkeypatch, {1: page([rec(i) for i in range(20)], total=50)})
    with pytest.raises(cli.IntegrityError):
        cli._fetch(settings)
    assert (settings.cache_dir / "raw.meta.json").read_text(encoding="utf-8") == before


def test_allow_incomplete_records_override(settings, monkeypatch):
    _fake_fetch(monkeypatch, {1: page([rec(i) for i in range(20)], total=50)})
    cli._fetch(settings, allow_incomplete=True)
    meta = json.loads((settings.cache_dir / "raw.meta.json").read_text(encoding="utf-8"))
    assert meta["integrity_override"] and meta["fetched"] == 20 and meta["total_count"] == 50


def test_sample_fetch_does_not_touch_raw(settings, monkeypatch):
    _fake_fetch(monkeypatch, capped_pages(300, 100))
    assert cli._fetch(settings, sample=10) == "sample"
    assert not (settings.cache_dir / "raw.meta.json").exists()
    meta = json.loads((settings.cache_dir / "sample.meta.json").read_text(encoding="utf-8"))
    assert meta["sample"] is True and meta["fetched"] == 10
    assert "serviceKey" not in meta["source_url"]


def test_sample_build_shows_preview_notice(settings, monkeypatch):
    _fake_fetch(monkeypatch, capped_pages(30, 30))
    cli._fetch(settings, sample=30)
    cli._build(settings, cache="sample")
    html = (settings.output_dir / "dental-implant-fixture" / "index.html").read_text(encoding="utf-8")
    assert "미리보기" in html
    assert "미리보기" in (settings.output_dir / "index.html").read_text(encoding="utf-8")


def test_cli_returns_nonzero_on_integrity_failure(settings, monkeypatch):
    """Actions 가 실패로 멈추도록 종료코드 1 을 내야 한다."""
    monkeypatch.setattr(cli.cfgmod, "load", lambda root=None: settings)
    _fake_fetch(monkeypatch, {1: page([rec(i) for i in range(20)], total=50)})
    assert cli.main(["fetch"]) == 1
