"""시인성 개선의 회귀 방지.

- 리포트 차트는 화면 크기별 2종(lg/sm)을 만들고 <picture> 로 고른다.
- 각 변형의 실효 글자 크기가 목표 화면 폭에서 12px 이상이다.
- 품목 상태는 그래프 대신 숫자로 표시한다.
- 팔레트는 흰 배경 대비 3:1 이상(WCAG 2.1 1.4.11).
"""
from __future__ import annotations

import re
from datetime import datetime

import pytest

from conftest import rec
from mfds_insight import cli, pipeline as p, render


def _lum(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def contrast(a: str, b: str = "#ffffff") -> float:
    hi, lo = sorted((_lum(a), _lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


# ── 글자 크기 설계값 ────────────────────────────────────
@pytest.mark.parametrize("key,shown_px", [("lg", 648), ("sm", 330)])
def test_effective_font_at_least_12px(key, shown_px):
    """실효 px = 글자pt × 표시폭 / 원본폭pt. lg 는 690px 이상 화면(표시 648px~), sm 은 360px 화면(약 330px)."""
    v = render.VARIANTS[key]
    assert v["font_pt"] * shown_px / (v["width_in"] * 72) >= 12.0


def test_palette_contrast(settings):
    for c in settings.chart["palette"]:
        assert contrast(c) >= 3.0, c


# ── 빌드 결과 ──────────────────────────────────────────
@pytest.fixture
def built(settings, monkeypatch):
    recs = [rec(i, date=f"{2010 + i % 15}0{1 + i % 9}15") for i in range(300)]
    recs += [dict(rec(900 + i), RTRCN_DSCTN_DIVS_CD="1") for i in range(20)]
    p.save_cache(p.normalize(recs, settings), settings)
    cli._build(settings)
    return settings.output_dir / "dental-implant-fixture"


def test_both_chart_variants_and_picture(built):
    html = (built / "index.html").read_text(encoding="utf-8")
    for name in ("yearly_trend", "top_companies", "domestic_vs_import"):
        assert (built / f"{name}.svg").exists() and (built / f"{name}_sm.svg").exists()
        assert re.search(rf'<source media="\(max-width: {render.CHART_BREAKPOINT_PX - 1}px\)" '
                         rf'srcset="{name}_sm.svg">', html)
    assert html.count("<picture>") == 3


def test_status_is_numbers_not_chart(built):
    html = (built / "index.html").read_text(encoding="utf-8")
    assert not list(built.glob("status_mix*.svg"))
    assert "품목 상태" in html and "300<span" in html and "20<span" in html
    assert "정상 · 93.8%" in html and "취소·취하 · 6.2%" in html


def test_table_dates_formatted_but_exports_raw(built):
    html = (built / "index.html").read_text(encoding="utf-8")
    assert re.search(r"<td class=\"nw\">20\d\d-0\d-15</td>", html)
    csv = (built / "dental-implant-fixture.csv").read_text(encoding="utf-8-sig")
    assert re.search(r",20\d\d0\d15,", csv)          # 내려받기는 원본 형식 유지


def test_generated_stamp_is_kst(built):
    html = (built / "index.html").read_text(encoding="utf-8")
    assert re.search(r"생성 \d{4}-\d\d-\d\d \d\d:\d\d KST", html)


# ── 단위 ───────────────────────────────────────────────
def test_fmt_cell():
    assert render.fmt_cell("허가일자", "20260215") == "2026-02-15"
    assert render.fmt_cell("허가일자", "2026-02-15") == "2026-02-15"
    assert render.fmt_cell("허가번호", "20260215") == "20260215"   # 날짜 열만 변환
    assert render.fmt_cell("허가일자", None) == ""


def test_shorten():
    assert render._shorten("짧은이름", 15, 2) == "짧은이름"
    out = render._shorten("Shinhung Dental Implant Systems Korea Co., Ltd.", 15, 2)
    assert out.count("\n") == 1 and out.endswith("…")


def test_partial_year(settings, monkeypatch):
    df = p.normalize([rec(1, date="20250301"), rec(2, date="20261015")], settings)
    monkeypatch.setattr("mfds_insight.config.now_kst", lambda: datetime(2026, 11, 4))
    assert p.summarize(df, settings)["partial_year"] == {"year": 2026, "through_month": 10}
    monkeypatch.setattr("mfds_insight.config.now_kst", lambda: datetime(2027, 1, 5))
    assert "partial_year" not in p.summarize(df, settings)


def test_hbar_height_grows_with_items(settings, tmp_path):
    """항목이 늘면 글자를 줄이지 않고 차트를 세로로 늘린다."""
    def height(n, key):
        data = {f"업체{i}": 100 - i for i in range(n)}
        path = tmp_path / f"h{n}{key}.svg"
        render._hbar_chart(data, settings, render._variant(settings, key), "#1F3864", path)
        return float(re.search(r'height="([\d.]+)pt"', path.read_text(encoding="utf-8")).group(1))
    for key in ("lg", "sm"):
        assert height(24, key) > height(12, key) * 1.8


# ── 탐색기 수록 범위 ───────────────────────────────────
def test_explorer_scope_reports_only(settings):
    import json
    names = ["치과용임플란트고정체", "치과용임플란트기공재료", "치과용임플란트상부구조물", "개인용온열기"]
    recs = [rec(i, name=names[i % 4]) for i in range(400)]
    p.save_cache(p.normalize(recs, settings), settings)
    cli._build(settings)
    data = json.loads((settings.output_dir / "explore" / "data.json").read_text(encoding="utf-8"))
    enc = data["encoded"]["품목명"]
    shown = set(enc["dict"]) if enc["kind"] == "dict" else set(enc["data"])
    assert shown == {"치과용임플란트고정체", "치과용임플란트상부구조물"}
    assert data["scope"]["kind"] == "reports" and data["scope"]["source_total"] == 400
    assert not data["truncated"]
    html = (settings.output_dir / "explore" / "index.html").read_text(encoding="utf-8")
    assert "수록 범위" in html and "전체 품목허가 400건 중" in html


def test_explorer_scope_all(settings):
    from dataclasses import replace
    from mfds_insight.explorer import scope_frame
    df = p.normalize([rec(i, name="개인용온열기") for i in range(5)], settings)
    s = replace(settings, explorer=dict(settings.explorer, scope="all"))
    out, scope = scope_frame(df, s)
    assert len(out) == 5 and scope["kind"] == "all"


def test_report_page_states_scope(built):
    html = (built / "index.html").read_text(encoding="utf-8")
    assert "집계 기준 · 품목명" in html and "「치과용임플란트고정체」" in html and "정확히 일치" in html


def test_explorer_merge_spacing_flag(settings):
    import json
    recs = [rec(i, name="치과용 임플란트 고정체" if i % 2 else "치과용임플란트고정체") for i in range(20)]
    p.save_cache(p.normalize(recs, settings), settings)
    cli._build(settings)
    data = json.loads((settings.output_dir / "explore" / "data.json").read_text(encoding="utf-8"))
    assert data["merge_spacing"] == ["품목명"]
    js = (settings.output_dir / "explore" / "explorer.js").read_text(encoding="utf-8")
    assert "function fkey" in js
